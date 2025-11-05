from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, make_response
import requests
import os
import json
import datetime
import psycopg2
import psycopg2.extras
import psycopg2.pool
from werkzeug.utils import secure_filename
import time
import jwt
import bcrypt
from functools import wraps
import threading
import queue
import zipfile
import io

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/app/uploads'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['DATABASE_URL'] = os.getenv('DATABASE_URL', 'postgresql://meeting_user:meeting_pass_change_in_production@postgres:5432/meetings')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-change-in-production')  # Required for sessions
app.config['JWT_SECRET'] = os.getenv('JWT_SECRET', os.getenv('SECRET_KEY', 'dev-jwt-secret-change-in-production'))  # JWT signing key
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = 3600  # 1 hour
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = 2592000  # 30 days
app.config['MAX_CONCURRENT_JOBS'] = int(os.getenv('MAX_CONCURRENT_JOBS', '4'))  # Max concurrent transcription jobs (for 8GB RAM)

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Store active live recording sessions
live_sessions = {}

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def no_cache_response(template_name, **context):
    """Render template with no-cache headers to prevent stale content"""
    response = make_response(render_template(template_name, **context))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# ============================================================
# TASK QUEUE SYSTEM (for resource management)
# ============================================================

# Job queue for audio processing
processing_queue = queue.Queue()
active_jobs = {}  # Track currently processing jobs
queue_lock = threading.Lock()

def audio_processing_worker():
    """Background worker that processes audio jobs from queue"""
    while True:
        try:
            job = processing_queue.get()

            if job is None:  # Poison pill to stop worker
                break

            job_id = job['job_id']
            meeting_id = job['meeting_id']
            audio_path = job['audio_path']
            title = job['title']

            # Mark job as processing
            with queue_lock:
                active_jobs[job_id] = {
                    'meeting_id': meeting_id,
                    'status': 'processing',
                    'started_at': time.time()
                }

            # Update database status
            conn = get_db()
            try:
                c = conn.cursor()
                c.execute("UPDATE meetings SET status = 'processing' WHERE id = %s", (meeting_id,))
                conn.commit()
            finally:
                conn.close()

            # Process the audio
            try:
                process_meeting_audio(audio_path, meeting_id, title)

                # Mark job as completed
                with queue_lock:
                    if job_id in active_jobs:
                        active_jobs[job_id]['status'] = 'completed'
                        active_jobs[job_id]['completed_at'] = time.time()

            except Exception as e:
                print(f"Error processing job {job_id}: {e}")

                # Mark job as failed
                with queue_lock:
                    if job_id in active_jobs:
                        active_jobs[job_id]['status'] = 'failed'
                        active_jobs[job_id]['error'] = str(e)

                # Update database
                conn = get_db()
                try:
                    c = conn.cursor()
                    c.execute("UPDATE meetings SET status = 'error' WHERE id = %s", (meeting_id,))
                    conn.commit()
                finally:
                    conn.close()

            finally:
                # Remove from active jobs after a delay (so status can be checked)
                threading.Timer(60.0, lambda: active_jobs.pop(job_id, None)).start()
                processing_queue.task_done()

        except Exception as e:
            print(f"Worker error: {e}")

# Start worker threads (limit concurrent jobs based on RAM)
num_workers = app.config['MAX_CONCURRENT_JOBS']
worker_threads = []

for i in range(num_workers):
    t = threading.Thread(target=audio_processing_worker, daemon=True, name=f"AudioWorker-{i+1}")
    t.start()
    worker_threads.append(t)

print(f"Started {num_workers} audio processing workers (MAX_CONCURRENT_JOBS={num_workers})")

def enqueue_audio_job(meeting_id, audio_path, title):
    """Add audio processing job to queue"""
    job_id = f"job_{meeting_id}_{int(time.time())}"

    job = {
        'job_id': job_id,
        'meeting_id': meeting_id,
        'audio_path': audio_path,
        'title': title,
        'queued_at': time.time()
    }

    # Get current queue size
    queue_size = processing_queue.qsize()
    active_count = len([j for j in active_jobs.values() if j['status'] == 'processing'])

    # Update database with queue position
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("UPDATE meetings SET status = %s WHERE id = %s", (f'queued (position {queue_size + 1})', meeting_id))
        conn.commit()
    finally:
        conn.close()

    # Add to queue
    processing_queue.put(job)

    return {
        'job_id': job_id,
        'queue_position': queue_size + 1,
        'active_jobs': active_count,
        'estimated_wait_seconds': queue_size * 60  # Rough estimate: 1 min per job ahead
    }

# Create database connection pool (prevents connection exhaustion)
db_pool = None

def init_db_pool():
    """Initialize database connection pool"""
    global db_pool
    if db_pool is None:
        db_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=30,  # Increased for 4 concurrent users (PostgreSQL max is 50)
            dsn=app.config['DATABASE_URL']
        )

class PooledConnection:
    """Wrapper for database connection that returns to pool on close"""
    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn
        self._conn.cursor_factory = psycopg2.extras.DictCursor

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        """Return connection to pool instead of closing"""
        if self._pool and self._conn:
            self._pool.putconn(self._conn)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        self.close()

def get_db():
    """Get database connection from pool
    Note: conn.close() will return connection to pool, not actually close it
    """
    global db_pool
    if db_pool is None:
        init_db_pool()

    # Get connection from pool
    raw_conn = db_pool.getconn()

    # Wrap in pooled connection
    return PooledConnection(db_pool, raw_conn)

def init_db():
    """Initialize database with retry logic"""
    max_retries = 5
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            conn = get_db()
            c = conn.cursor()

            # Create users table
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    security_question TEXT NOT NULL,
                    security_answer_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            ''')

            # Create meetings table with user_id foreign key
            c.execute('''
                CREATE TABLE IF NOT EXISTS meetings (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    audio_file TEXT,
                    transcript TEXT,
                    summary TEXT,
                    action_items TEXT,
                    key_points TEXT,
                    decisions TEXT,
                    attendees TEXT,
                    duration INTEGER,
                    tags TEXT,
                    status TEXT DEFAULT 'processing',
                    meeting_type TEXT DEFAULT 'general',
                    notes TEXT,
                    display_order INTEGER DEFAULT 0
                )
            ''')

            # Create index on user_id for faster queries
            c.execute('''
                CREATE INDEX IF NOT EXISTS idx_meetings_user_id ON meetings(user_id)
            ''')

            # Create refresh tokens table
            c.execute('''
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token TEXT UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Create calendar tokens table for Google Calendar integration
            c.execute('''
                CREATE TABLE IF NOT EXISTS calendar_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    token_expiry TIMESTAMP,
                    calendar_id TEXT DEFAULT 'primary',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Create calendar events tracking table (to avoid duplicate prompts)
            c.execute('''
                CREATE TABLE IF NOT EXISTS calendar_events_prompted (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    event_id TEXT NOT NULL,
                    event_start TIMESTAMP NOT NULL,
                    prompted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    recording_started BOOLEAN DEFAULT FALSE,
                    meeting_id INTEGER REFERENCES meetings(id) ON DELETE SET NULL,
                    UNIQUE(user_id, event_id)
                )
            ''')

            # Migrations: Add new columns if they don't exist
            try:
                c.execute('''
                    ALTER TABLE meetings
                    ADD COLUMN IF NOT EXISTS meeting_type TEXT DEFAULT 'general'
                ''')
                c.execute('''
                    ALTER TABLE meetings
                    ADD COLUMN IF NOT EXISTS notes TEXT
                ''')
                c.execute('''
                    ALTER TABLE meetings
                    ADD COLUMN IF NOT EXISTS display_order INTEGER DEFAULT 0
                ''')
            except Exception as e:
                print(f"Migration note: {e}")

            conn.commit()
            conn.close()
            print("Database initialized successfully!")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Database connection attempt {attempt + 1} failed: {e}. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                print(f"Failed to initialize database after {max_retries} attempts: {e}")
                raise

# ============================================================
# AUTHENTICATION FUNCTIONS
# ============================================================

def hash_password(password):
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, password_hash):
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

def generate_access_token(user_id):
    """Generate JWT access token"""
    payload = {
        'user_id': user_id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(seconds=app.config['JWT_ACCESS_TOKEN_EXPIRES']),
        'iat': datetime.datetime.utcnow(),
        'type': 'access'
    }
    return jwt.encode(payload, app.config['JWT_SECRET'], algorithm='HS256')

def generate_refresh_token(user_id):
    """Generate JWT refresh token and store in database"""
    payload = {
        'user_id': user_id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(seconds=app.config['JWT_REFRESH_TOKEN_EXPIRES']),
        'iat': datetime.datetime.utcnow(),
        'type': 'refresh'
    }
    token = jwt.encode(payload, app.config['JWT_SECRET'], algorithm='HS256')

    # Store in database
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            INSERT INTO refresh_tokens (user_id, token, expires_at)
            VALUES (%s, %s, %s)
        ''', (user_id, token, datetime.datetime.utcnow() + datetime.timedelta(seconds=app.config['JWT_REFRESH_TOKEN_EXPIRES'])))
        conn.commit()
    finally:
        conn.close()

    return token

def jwt_required(f):
    """Decorator to require JWT authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None

        # Get token from Authorization header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(' ')[1]  # Bearer <token>
            except IndexError:
                return jsonify({'error': 'Invalid authorization header format'}), 401

        # Get token from cookie (for browser requests)
        elif 'access_token' in request.cookies:
            token = request.cookies.get('access_token')

        if not token:
            # For browser requests (HTML), redirect to login
            if request.accept_mimetypes.accept_html:
                return redirect(url_for('login'))
            # For API requests (JSON), return error
            return jsonify({'error': 'Authorization token required'}), 401

        try:
            # Decode token
            payload = jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])

            # Verify token type
            if payload.get('type') != 'access':
                return jsonify({'error': 'Invalid token type'}), 401

            # Get user from database to ensure they still exist
            conn = get_db()
            try:
                c = conn.cursor()
                c.execute('SELECT id, username, email FROM users WHERE id = %s', (payload['user_id'],))
                user = c.fetchone()

                if not user:
                    return jsonify({'error': 'User not found'}), 401

                # Add user info to request context
                request.current_user = {
                    'user_id': user['id'],
                    'username': user['username'],
                    'email': user['email']
                }
            finally:
                conn.close()

        except jwt.ExpiredSignatureError:
            if request.accept_mimetypes.accept_html:
                return redirect(url_for('login'))
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            if request.accept_mimetypes.accept_html:
                return redirect(url_for('login'))
            return jsonify({'error': 'Invalid token'}), 401
        except Exception as e:
            print(f"JWT verification error: {e}")
            if request.accept_mimetypes.accept_html:
                return redirect(url_for('login'))
            return jsonify({'error': 'Token verification failed'}), 401

        return f(*args, **kwargs)

    return decorated_function

# ============================================================
# AUTHENTICATION ROUTES
# ============================================================

@app.route('/auth/login', methods=['GET'])
def login_page():
    """Serve login page"""
    return no_cache_response('login.html')

@app.route('/auth/register', methods=['GET'])
def register_page():
    """Serve registration page"""
    return no_cache_response('register.html')

@app.route('/auth/forgot-password', methods=['GET'])
def forgot_password_page():
    """Serve forgot password page"""
    return no_cache_response('forgot-password.html')

@app.route('/auth/register', methods=['POST'])
def register():
    """Register new user"""
    data = request.json

    if not data or not data.get('username') or not data.get('email') or not data.get('password') or not data.get('security_question') or not data.get('security_answer'):
        return jsonify({'error': 'Username, email, password, security question, and security answer required'}), 400

    username = data['username'].strip()
    email = data['email'].strip().lower()
    password = data['password']
    security_question = data['security_question'].strip()
    security_answer = data['security_answer'].strip()

    # Validation
    if len(username) < 3:
        return jsonify({'error': 'Username must be at least 3 characters'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
    if '@' not in email:
        return jsonify({'error': 'Invalid email address'}), 400
    if len(security_question) < 5:
        return jsonify({'error': 'Security question must be at least 5 characters'}), 400
    if len(security_answer) < 3:
        return jsonify({'error': 'Security answer must be at least 3 characters'}), 400

    # Hash password and security answer
    password_hash = hash_password(password)
    security_answer_hash = hash_password(security_answer.lower())  # Lowercase for case-insensitive comparison

    # Create user
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            INSERT INTO users (username, email, password_hash, security_question, security_answer_hash)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (username, email, password_hash, security_question, security_answer_hash))
        user_id = c.fetchone()[0]
        conn.commit()

        # Generate tokens
        access_token = generate_access_token(user_id)
        refresh_token = generate_refresh_token(user_id)

        # Create response with tokens in cookies
        response = make_response(jsonify({
            'message': 'User registered successfully',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': {
                'id': user_id,
                'username': username,
                'email': email
            }
        }), 201)

        # Set httpOnly cookies for security
        # Detect if request came via HTTPS (from X-Forwarded-Proto header set by nginx/Cloudflare)
        is_secure = request.headers.get('X-Forwarded-Proto', 'http') == 'https'

        response.set_cookie(
            'access_token',
            access_token,
            max_age=app.config['JWT_ACCESS_TOKEN_EXPIRES'],
            httponly=True,
            secure=is_secure,
            samesite='Lax'
        )
        response.set_cookie(
            'refresh_token',
            refresh_token,
            max_age=app.config['JWT_REFRESH_TOKEN_EXPIRES'],
            httponly=True,
            secure=is_secure,
            samesite='Lax'
        )

        return response

    except psycopg2.errors.UniqueViolation:
        return jsonify({'error': 'Username or email already exists'}), 409
    except Exception as e:
        print(f"Registration error: {e}")
        return jsonify({'error': 'Registration failed'}), 500
    finally:
        conn.close()

@app.route('/auth/login', methods=['POST'])
def login():
    """Login user"""
    data = request.json

    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Username and password required'}), 400

    username = data['username'].strip()
    password = data['password']

    # Get user from database
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT id, username, email, password_hash FROM users WHERE username = %s', (username,))
        user = c.fetchone()

        if not user:
            return jsonify({'error': 'Invalid username or password'}), 401

        # Verify password
        if not verify_password(password, user['password_hash']):
            return jsonify({'error': 'Invalid username or password'}), 401

        # Update last login
        c.execute('UPDATE users SET last_login = %s WHERE id = %s', (datetime.datetime.utcnow(), user['id']))
        conn.commit()

        # Generate tokens
        access_token = generate_access_token(user['id'])
        refresh_token = generate_refresh_token(user['id'])

        # Create response with tokens in cookies
        response = make_response(jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'email': user['email']
            }
        }), 200)

        # Set httpOnly cookies for security
        # Detect if request came via HTTPS (from X-Forwarded-Proto header set by nginx/Cloudflare)
        is_secure = request.headers.get('X-Forwarded-Proto', 'http') == 'https'

        response.set_cookie(
            'access_token',
            access_token,
            max_age=app.config['JWT_ACCESS_TOKEN_EXPIRES'],
            httponly=True,
            secure=is_secure,
            samesite='Lax'
        )
        response.set_cookie(
            'refresh_token',
            refresh_token,
            max_age=app.config['JWT_REFRESH_TOKEN_EXPIRES'],
            httponly=True,
            secure=is_secure,
            samesite='Lax'
        )

        return response

    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500
    finally:
        conn.close()

@app.route('/auth/refresh', methods=['POST'])
def refresh():
    """Refresh access token using refresh token"""
    data = request.json

    if not data or not data.get('refresh_token'):
        return jsonify({'error': 'Refresh token required'}), 400

    refresh_token = data['refresh_token']

    try:
        # Decode refresh token
        payload = jwt.decode(refresh_token, app.config['JWT_SECRET'], algorithms=['HS256'])

        # Verify token type
        if payload.get('type') != 'refresh':
            return jsonify({'error': 'Invalid token type'}), 401

        # Verify token exists in database and not revoked
        conn = get_db()
        try:
            c = conn.cursor()
            c.execute('''
                SELECT user_id FROM refresh_tokens
                WHERE token = %s AND expires_at > %s
            ''', (refresh_token, datetime.datetime.utcnow()))
            token_data = c.fetchone()

            if not token_data:
                return jsonify({'error': 'Invalid or expired refresh token'}), 401

            # Generate new access token
            access_token = generate_access_token(token_data['user_id'])

            return jsonify({
                'access_token': access_token
            }), 200

        finally:
            conn.close()

    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Refresh token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid refresh token'}), 401
    except Exception as e:
        print(f"Token refresh error: {e}")
        return jsonify({'error': 'Token refresh failed'}), 500

@app.route('/auth/logout', methods=['POST'])
@jwt_required
def logout():
    """Logout user and revoke refresh tokens"""
    # Get refresh token from cookie
    refresh_token = request.cookies.get('refresh_token')

    if refresh_token:
        # Revoke specific refresh token
        conn = get_db()
        try:
            c = conn.cursor()
            c.execute('DELETE FROM refresh_tokens WHERE token = %s', (refresh_token,))
            conn.commit()
        finally:
            conn.close()
    else:
        # Revoke all refresh tokens for user
        conn = get_db()
        try:
            c = conn.cursor()
            c.execute('DELETE FROM refresh_tokens WHERE user_id = %s', (request.current_user['user_id'],))
            conn.commit()
        finally:
            conn.close()

    # Create response and clear cookies
    # Detect if request came via HTTPS
    is_secure = request.headers.get('X-Forwarded-Proto', 'http') == 'https'

    response = make_response(jsonify({'message': 'Logged out successfully'}), 200)
    response.set_cookie('access_token', '', max_age=0, secure=is_secure, samesite='Lax')
    response.set_cookie('refresh_token', '', max_age=0, secure=is_secure, samesite='Lax')

    return response

@app.route('/auth/me', methods=['GET'])
@jwt_required
def get_current_user():
    """Get current user info"""
    return jsonify({
        'user': request.current_user
    }), 200

@app.route('/auth/forgot-password/question', methods=['POST'])
def get_security_question():
    """Get security question for username"""
    data = request.json

    if not data or not data.get('username'):
        return jsonify({'error': 'Username required'}), 400

    username = data['username'].strip()

    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT security_question FROM users WHERE username = %s', (username,))
        user = c.fetchone()

        if not user:
            return jsonify({'error': 'Username not found'}), 404

        return jsonify({
            'security_question': user['security_question']
        }), 200

    except Exception as e:
        print(f"Error fetching security question: {e}")
        return jsonify({'error': 'Failed to retrieve security question'}), 500
    finally:
        conn.close()

@app.route('/auth/reset-password', methods=['POST'])
def reset_password():
    """Reset password using security answer"""
    data = request.json

    if not data or not data.get('username') or not data.get('security_answer') or not data.get('new_password'):
        return jsonify({'error': 'Username, security answer, and new password required'}), 400

    username = data['username'].strip()
    security_answer = data['security_answer'].strip().lower()  # Lowercase for case-insensitive comparison
    new_password = data['new_password']

    # Validate new password
    if len(new_password) < 8:
        return jsonify({'error': 'New password must be at least 8 characters'}), 400

    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT id, security_answer_hash FROM users WHERE username = %s', (username,))
        user = c.fetchone()

        if not user:
            return jsonify({'error': 'Invalid username or security answer'}), 401

        # Verify security answer
        if not verify_password(security_answer, user['security_answer_hash']):
            return jsonify({'error': 'Invalid username or security answer'}), 401

        # Hash new password
        new_password_hash = hash_password(new_password)

        # Update password
        c.execute('UPDATE users SET password_hash = %s WHERE id = %s', (new_password_hash, user['id']))
        conn.commit()

        # Revoke all existing refresh tokens for security
        c.execute('DELETE FROM refresh_tokens WHERE user_id = %s', (user['id'],))
        conn.commit()

        return jsonify({'message': 'Password reset successfully'}), 200

    except Exception as e:
        print(f"Password reset error: {e}")
        return jsonify({'error': 'Password reset failed'}), 500
    finally:
        conn.close()

# ============================================================
# MEETING ROUTES (Protected)
# ============================================================

@app.route('/')
def index():
    """Main dashboard showing all meetings for current user"""
    # Check if user is authenticated
    token = request.cookies.get('access_token')

    if not token:
        # Not authenticated - redirect to login
        return redirect(url_for('login_page'))

    try:
        # Verify token
        payload = jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])

        if payload.get('type') != 'access':
            return redirect(url_for('login'))

        # Get user from database
        conn = get_db()
        try:
            c = conn.cursor()
            c.execute('SELECT id, username, email FROM users WHERE id = %s', (payload['user_id'],))
            user = c.fetchone()

            if not user:
                return redirect(url_for('login'))

            # Get meetings
            c.execute('SELECT * FROM meetings WHERE user_id = %s ORDER BY display_order, date DESC LIMIT 50', (user['id'],))
            meetings = c.fetchall()

            return no_cache_response('notion_dashboard.html', meetings=meetings, user={
                'user_id': user['id'],
                'username': user['username'],
                'email': user['email']
            })
        finally:
            conn.close()

    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Exception):
        # Token invalid or expired - redirect to login
        return redirect(url_for('login'))

@app.route('/calendar')
@jwt_required
def calendar_view():
    """Calendar view of meetings"""
    import calendar as cal
    from datetime import datetime, timedelta

    # Get year and month from query params, default to current
    year = request.args.get('year', type=int) or datetime.now().year
    month = request.args.get('month', type=int) or datetime.now().month

    # Get first and last day of the month
    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(days=1)

    # Get all meetings for this user in this month (plus surrounding days)
    conn = get_db()
    try:
        c = conn.cursor()

        # Get meetings from a week before to a week after to cover all visible days
        start_date = first_day - timedelta(days=7)
        end_date = last_day + timedelta(days=7)

        c.execute('''
            SELECT id, title, date, meeting_type
            FROM meetings
            WHERE user_id = %s AND date >= %s AND date <= %s
            ORDER BY date
        ''', (request.current_user['user_id'], start_date, end_date))

        all_meetings = c.fetchall()

        # Organize meetings by date
        meetings_by_date = {}
        for meeting in all_meetings:
            if meeting['date']:
                date_key = meeting['date'].strftime('%Y-%m-%d')
                if date_key not in meetings_by_date:
                    meetings_by_date[date_key] = []
                meetings_by_date[date_key].append(meeting)

        # Build calendar days structure
        calendar_days = []

        # Get first day of week offset
        first_weekday = first_day.weekday()
        # Python's weekday: Monday=0, Sunday=6. Calendar grid: Sunday=0
        first_weekday = (first_weekday + 1) % 7

        # Add days from previous month
        if first_weekday > 0:
            prev_month_last_day = first_day - timedelta(days=1)
            for i in range(first_weekday):
                day_date = prev_month_last_day - timedelta(days=first_weekday - 1 - i)
                date_key = day_date.strftime('%Y-%m-%d')
                calendar_days.append({
                    'date': day_date,
                    'in_month': False,
                    'meetings': meetings_by_date.get(date_key, [])
                })

        # Add days of current month
        current_day = first_day
        while current_day <= last_day:
            date_key = current_day.strftime('%Y-%m-%d')
            calendar_days.append({
                'date': current_day,
                'in_month': True,
                'meetings': meetings_by_date.get(date_key, [])
            })
            current_day += timedelta(days=1)

        # Add days from next month to complete the grid (42 cells = 6 weeks)
        while len(calendar_days) < 42:
            date_key = current_day.strftime('%Y-%m-%d')
            calendar_days.append({
                'date': current_day,
                'in_month': False,
                'meetings': meetings_by_date.get(date_key, [])
            })
            current_day += timedelta(days=1)

        # Get month name
        month_name = first_day.strftime('%B')

        return no_cache_response('notion_calendar.html',
                             calendar_days=calendar_days,
                             current_month=month_name,
                             current_year=year,
                             user=request.current_user)
    finally:
        conn.close()

@app.route('/table')
@jwt_required
def table_view():
    """Table view of meetings"""
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM meetings WHERE user_id = %s ORDER BY date DESC', (request.current_user['user_id'],))
        meetings = c.fetchall()
        return no_cache_response('notion_table.html', meetings=meetings, user=request.current_user)
    finally:
        conn.close()

@app.route('/settings')
@jwt_required
def settings():
    """User settings page"""
    return no_cache_response('notion_settings.html', user=request.current_user)

# ============================================================
# Google Calendar Integration (Notion-style auto-record)
# ============================================================

@app.route('/api/calendar/connect', methods=['POST'])
@jwt_required
def calendar_connect():
    """Initiate Google Calendar OAuth flow"""
    from google_auth_oauthlib.flow import Flow
    import json

    # Google OAuth credentials (you'll need to create these in Google Cloud Console)
    client_config = {
        "web": {
            "client_id": os.getenv('GOOGLE_CLIENT_ID'),
            "client_secret": os.getenv('GOOGLE_CLIENT_SECRET'),
            "redirect_uris": [f"{os.getenv('APP_URL', 'http://localhost:8080')}/api/calendar/callback"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }

    if not client_config["web"]["client_id"]:
        return jsonify({'error': 'Google Calendar not configured. Set GOOGLE_CLIENT_ID in .env'}), 500

    flow = Flow.from_client_config(
        client_config,
        scopes=['https://www.googleapis.com/auth/calendar.readonly'],
        redirect_uri=client_config["web"]["redirect_uris"][0]
    )

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )

    # Store state in session or database for verification
    return jsonify({'authorization_url': authorization_url, 'state': state})

@app.route('/api/calendar/callback')
def calendar_callback():
    """Handle Google Calendar OAuth callback"""
    from google_auth_oauthlib.flow import Flow
    from google.oauth2.credentials import Credentials
    import datetime

    # Get authorization code from query params
    code = request.args.get('code')
    if not code:
        return "Error: No authorization code received", 400

    client_config = {
        "web": {
            "client_id": os.getenv('GOOGLE_CLIENT_ID'),
            "client_secret": os.getenv('GOOGLE_CLIENT_SECRET'),
            "redirect_uris": [f"{os.getenv('APP_URL', 'http://localhost:8080')}/api/calendar/callback"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=['https://www.googleapis.com/auth/calendar.readonly'],
        redirect_uri=client_config["web"]["redirect_uris"][0]
    )

    flow.fetch_token(code=code)
    credentials = flow.credentials

    # Get user from JWT (if available in cookies/headers)
    # For now, redirect to a page that will store the token with JWT
    return redirect(f'/settings?calendar=success&token={credentials.token}&refresh={credentials.refresh_token}&expiry={credentials.expiry.isoformat()}')

@app.route('/api/calendar/save-token', methods=['POST'])
@jwt_required
def calendar_save_token():
    """Save calendar token after OAuth callback"""
    from datetime import datetime

    data = request.get_json()
    access_token = data.get('access_token')
    refresh_token = data.get('refresh_token')
    expiry = data.get('expiry')

    if not access_token:
        return jsonify({'error': 'No access token provided'}), 400

    conn = get_db()
    try:
        c = conn.cursor()

        # Upsert calendar token
        c.execute('''
            INSERT INTO calendar_tokens (user_id, access_token, refresh_token, token_expiry)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                token_expiry = EXCLUDED.token_expiry,
                updated_at = CURRENT_TIMESTAMP
        ''', (request.current_user['user_id'], access_token, refresh_token, expiry))

        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()

@app.route('/api/calendar/disconnect', methods=['POST'])
@jwt_required
def calendar_disconnect():
    """Disconnect Google Calendar"""
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('DELETE FROM calendar_tokens WHERE user_id = %s',
                 (request.current_user['user_id'],))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()

@app.route('/api/calendar/status')
@jwt_required
def calendar_status():
    """Check if user has calendar connected"""
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT token_expiry FROM calendar_tokens WHERE user_id = %s',
                 (request.current_user['user_id'],))
        result = c.fetchone()

        if result:
            return jsonify({'connected': True, 'expiry': result['token_expiry'].isoformat() if result['token_expiry'] else None})
        else:
            return jsonify({'connected': False})
    finally:
        conn.close()

@app.route('/api/calendar/upcoming')
@jwt_required
def calendar_upcoming():
    """Get upcoming meetings from Google Calendar"""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from datetime import datetime, timedelta

    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT access_token, refresh_token, token_expiry FROM calendar_tokens WHERE user_id = %s',
                 (request.current_user['user_id'],))
        token_data = c.fetchone()

        if not token_data:
            return jsonify({'error': 'Calendar not connected'}), 401

        # Create credentials
        creds = Credentials(
            token=token_data['access_token'],
            refresh_token=token_data['refresh_token'],
            token_uri='https://oauth2.googleapis.com/token',
            client_id=os.getenv('GOOGLE_CLIENT_ID'),
            client_secret=os.getenv('GOOGLE_CLIENT_SECRET')
        )

        # Build calendar service
        service = build('calendar', 'v3', credentials=creds)

        # Get events for next 24 hours
        now = datetime.utcnow()
        time_max = now + timedelta(hours=24)

        events_result = service.events().list(
            calendarId='primary',
            timeMin=now.isoformat() + 'Z',
            timeMax=time_max.isoformat() + 'Z',
            maxResults=20,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        # Format events
        formatted_events = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            formatted_events.append({
                'id': event['id'],
                'summary': event.get('summary', 'No Title'),
                'start': start,
                'end': event['end'].get('dateTime', event['end'].get('date')),
                'location': event.get('location'),
                'attendees': [a.get('email') for a in event.get('attendees', [])]
            })

        return jsonify({'events': formatted_events})
    except Exception as e:
        print(f"Calendar error: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/calendar/check-meetings')
@jwt_required
def calendar_check_meetings():
    """Check if any meetings are starting soon (called by frontend every minute)"""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from datetime import datetime, timedelta

    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT access_token, refresh_token FROM calendar_tokens WHERE user_id = %s',
                 (request.current_user['user_id'],))
        token_data = c.fetchone()

        if not token_data:
            return jsonify({'meetings_starting': []})

        # Create credentials
        creds = Credentials(
            token=token_data['access_token'],
            refresh_token=token_data['refresh_token'],
            token_uri='https://oauth2.googleapis.com/token',
            client_id=os.getenv('GOOGLE_CLIENT_ID'),
            client_secret=os.getenv('GOOGLE_CLIENT_SECRET')
        )

        # Build calendar service
        service = build('calendar', 'v3', credentials=creds)

        # Get events starting in the next 5 minutes
        now = datetime.utcnow()
        time_min = now
        time_max = now + timedelta(minutes=5)

        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min.isoformat() + 'Z',
            timeMax=time_max.isoformat() + 'Z',
            maxResults=10,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        # Filter out events we've already prompted for
        meetings_to_prompt = []
        for event in events:
            # Check if we've already prompted for this event
            c.execute('SELECT id FROM calendar_events_prompted WHERE user_id = %s AND event_id = %s',
                     (request.current_user['user_id'], event['id']))

            if not c.fetchone():
                # Haven't prompted yet - add to list
                start = event['start'].get('dateTime', event['start'].get('date'))
                meetings_to_prompt.append({
                    'id': event['id'],
                    'summary': event.get('summary', 'No Title'),
                    'start': start,
                    'attendees': [a.get('email') for a in event.get('attendees', [])]
                })

                # Mark as prompted
                c.execute('''
                    INSERT INTO calendar_events_prompted (user_id, event_id, event_start)
                    VALUES (%s, %s, %s)
                ''', (request.current_user['user_id'], event['id'], start))

        conn.commit()
        return jsonify({'meetings_starting': meetings_to_prompt})
    except Exception as e:
        print(f"Calendar check error: {e}")
        return jsonify({'meetings_starting': []})
    finally:
        conn.close()

@app.route('/api/change-password', methods=['POST'])
@jwt_required
def change_password():
    """Change user password"""
    data = request.get_json()
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_password or not new_password:
        return jsonify({'error': 'Current password and new password are required'}), 400

    if len(new_password) < 8:
        return jsonify({'error': 'New password must be at least 8 characters'}), 400

    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT password_hash FROM users WHERE id = %s', (request.current_user['user_id'],))
        user = c.fetchone()

        if not user or not bcrypt.checkpw(current_password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            return jsonify({'error': 'Current password is incorrect'}), 401

        # Hash new password
        new_password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # Update password
        c.execute('UPDATE users SET password_hash = %s WHERE id = %s',
                 (new_password_hash, request.current_user['user_id']))
        conn.commit()

        return jsonify({'success': True})
    finally:
        conn.close()

@app.route('/api/export')
@jwt_required
def export_data():
    """Export all user data as JSON"""
    conn = get_db()
    try:
        c = conn.cursor()

        # Get user info
        c.execute('SELECT username, email, created_at FROM users WHERE id = %s',
                 (request.current_user['user_id'],))
        user_info = c.fetchone()

        # Get all meetings
        c.execute('SELECT * FROM meetings WHERE user_id = %s ORDER BY date DESC',
                 (request.current_user['user_id'],))
        meetings = c.fetchall()

        # Format data
        export_data = {
            'user': {
                'username': user_info['username'],
                'email': user_info['email'],
                'created_at': user_info['created_at'].isoformat() if user_info['created_at'] else None
            },
            'meetings': []
        }

        for meeting in meetings:
            meeting_data = {
                'id': meeting['id'],
                'title': meeting['title'],
                'date': meeting['date'].isoformat() if meeting['date'] else None,
                'attendees': meeting['attendees'],
                'tags': meeting['tags'],
                'meeting_type': meeting['meeting_type'],
                'transcript': meeting['transcript'],
                'summary': meeting['summary'],
                'key_points': meeting['key_points'],
                'action_items': meeting['action_items'],
                'decisions': meeting['decisions'],
                'duration': meeting['duration'],
                'notes': meeting['notes'] if 'notes' in meeting.keys() else None
            }
            export_data['meetings'].append(meeting_data)

        return jsonify(export_data)
    finally:
        conn.close()

@app.route('/api/delete-account', methods=['DELETE'])
@jwt_required
def delete_account():
    """Delete user account and all associated data"""
    conn = get_db()
    try:
        c = conn.cursor()

        # Get all meeting audio files
        c.execute('SELECT audio_file FROM meetings WHERE user_id = %s',
                 (request.current_user['user_id'],))
        meetings = c.fetchall()

        # Delete audio files from filesystem
        for meeting in meetings:
            if meeting['audio_file']:
                audio_path = os.path.join(app.config['UPLOAD_FOLDER'], meeting['audio_file'])
                if os.path.exists(audio_path):
                    try:
                        os.remove(audio_path)
                    except Exception as e:
                        print(f"Error deleting file {audio_path}: {e}")

        # Delete user (CASCADE will delete meetings and refresh tokens)
        c.execute('DELETE FROM users WHERE id = %s', (request.current_user['user_id'],))
        conn.commit()

        return jsonify({'success': True})
    finally:
        conn.close()

@app.route('/upload', methods=['GET', 'POST'])
@jwt_required
def upload_meeting():
    """Upload and process meeting audio"""
    if request.method == 'POST':
        # Check if file is present
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400

        file = request.files['audio']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Get form data
        title = request.form.get('title', 'Untitled Meeting')
        attendees = request.form.get('attendees', '')
        tags = request.form.get('tags', '')
        meeting_type = request.form.get('meeting_type', 'auto-detect')  # User can select or auto-detect

        # Validate meeting_type
        valid_types = ['auto-detect', 'standup', 'retrospective', 'planning', 'one-on-one',
                      'team-sync', 'brainstorming', 'review', 'client-call', 'interview',
                      'training', 'general']
        if meeting_type not in valid_types:
            meeting_type = 'auto-detect'

        # Validate file extension
        ALLOWED_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.webm', '.ogg', '.flac', '.aac', '.mp4'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if not file_ext or file_ext not in ALLOWED_EXTENSIONS:
            return jsonify({'error': f'Invalid file type. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'}), 400

        # Save uploaded file
        filename = secure_filename(file.filename)
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Create initial database entry with user_id
        # If user selected a specific type, use it; otherwise it will be auto-detected during processing
        initial_meeting_type = meeting_type if meeting_type != 'auto-detect' else 'general'

        conn = get_db()
        try:
            c = conn.cursor()
            c.execute('''
                INSERT INTO meetings (user_id, title, audio_file, attendees, tags, meeting_type, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'queued')
                RETURNING id
            ''', (request.current_user['user_id'], title, filename, attendees, tags, initial_meeting_type))
            meeting_id = c.fetchone()[0]
            conn.commit()
        finally:
            conn.close()

        # Add to processing queue (instead of blocking)
        queue_info = enqueue_audio_job(meeting_id, filepath, title)

        # Return immediately with queue info
        return jsonify({
            'success': True,
            'meeting_id': meeting_id,
            'message': 'Meeting uploaded and queued for processing',
            'queue_info': queue_info
        }), 202  # 202 Accepted - processing will happen asynchronously

    return no_cache_response('upload.html', user=request.current_user)

def process_meeting_audio(audio_path, meeting_id, title):
    """Process audio through Whisper and Ollama"""

    # Check if user manually set meeting type
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT meeting_type FROM meetings WHERE id = %s', (meeting_id,))
        result = c.fetchone()
        user_specified_type = result['meeting_type'] if result else 'general'
    finally:
        conn.close()

    # Step 1: Transcribe with Whisper
    print(f"Transcribing audio for meeting {meeting_id}...")
    try:
        with open(audio_path, 'rb') as f:
            response = requests.post(
                'http://whisper:9000/asr?task=transcribe&language=en&output=json',
                files={'audio_file': f},
                timeout=600  # 10 minutes timeout for large files
            )

        if response.status_code != 200:
            raise Exception(f"Whisper API error: {response.status_code}")

        transcript_data = response.json()
        transcript = transcript_data.get('text', '')

        if not transcript:
            raise Exception("No transcript generated")

    except Exception as e:
        print(f"Transcription error: {e}")
        conn = get_db()
        try:
            c = conn.cursor()
            c.execute('UPDATE meetings SET status = %s, transcript = %s WHERE id = %s',
                      ('error', f'Transcription failed: {str(e)}', meeting_id))
            conn.commit()
        finally:
            conn.close()
        return

    # Step 2: Generate summary with Ollama (local LLM)
    print(f"Analyzing transcript for meeting {meeting_id}...")
    try:
        summary_prompt = f"""Analyze this meeting transcript and provide a structured response.

Transcript:
{transcript}

Please provide:
1. Meeting type classification (choose ONE from: standup, retrospective, planning, one-on-one, team-sync, brainstorming, review, client-call, interview, training, general)
2. A brief summary (2-3 paragraphs)
3. Key discussion points (as a list)
4. Action items with assignees if mentioned (as a list)
5. Important decisions made (as a list)

Format your response as follows:

MEETING TYPE:
[meeting type here - must be one of: standup, retrospective, planning, one-on-one, team-sync, brainstorming, review, client-call, interview, training, general]

SUMMARY:
[Your summary here]

KEY POINTS:
- Point 1
- Point 2

ACTION ITEMS:
- Action 1
- Action 2

DECISIONS:
- Decision 1
- Decision 2
"""

        ollama_response = requests.post(
            'http://ollama:11434/api/generate',
            json={
                'model': os.getenv('OLLAMA_MODEL', 'phi'),
                'prompt': summary_prompt,
                'stream': False
            },
            timeout=300  # 5 minutes timeout
        )

        if ollama_response.status_code != 200:
            raise Exception(f"Ollama API error: {ollama_response.status_code}")

        analysis_text = ollama_response.json().get('response', '')

        # Parse the structured response
        meeting_type, summary, key_points, action_items, decisions = parse_analysis(analysis_text)

    except Exception as e:
        print(f"Analysis error: {e}")
        meeting_type = "general"
        summary = "Analysis failed"
        key_points = []
        action_items = []
        decisions = []

    # Step 3: Update database with results
    # Use auto-detected type only if user didn't specify one
    final_meeting_type = meeting_type if user_specified_type == 'general' else user_specified_type

    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            UPDATE meetings
            SET transcript = %s, summary = %s, key_points = %s, action_items = %s, decisions = %s, meeting_type = %s, status = 'completed'
            WHERE id = %s
        ''', (transcript, summary, json.dumps(key_points), json.dumps(action_items),
              json.dumps(decisions), final_meeting_type, meeting_id))
        conn.commit()
    finally:
        conn.close()

    print(f"Meeting {meeting_id} processed successfully")

def parse_analysis(text):
    """Parse the structured analysis response"""
    meeting_type = "general"
    summary = ""
    key_points = []
    action_items = []
    decisions = []

    current_section = None
    lines = text.split('\n')

    # Valid meeting types
    valid_types = ['standup', 'retrospective', 'planning', 'one-on-one', 'team-sync',
                   'brainstorming', 'review', 'client-call', 'interview', 'training', 'general']

    for line in lines:
        line = line.strip()

        if 'MEETING TYPE:' in line.upper():
            current_section = 'meeting_type'
            continue
        elif 'SUMMARY:' in line.upper():
            current_section = 'summary'
            continue
        elif 'KEY POINTS:' in line.upper() or 'KEY DISCUSSION POINTS:' in line.upper():
            current_section = 'key_points'
            continue
        elif 'ACTION ITEMS:' in line.upper():
            current_section = 'action_items'
            continue
        elif 'DECISIONS:' in line.upper():
            current_section = 'decisions'
            continue

        if current_section == 'meeting_type' and line:
            # Extract meeting type from line
            for valid_type in valid_types:
                if valid_type.lower() in line.lower():
                    meeting_type = valid_type
                    break
            current_section = None
        elif current_section == 'summary' and line:
            summary += line + " "
        elif current_section == 'key_points' and line.startswith('-'):
            key_points.append(line[1:].strip())
        elif current_section == 'action_items' and line.startswith('-'):
            action_items.append(line[1:].strip())
        elif current_section == 'decisions' and line.startswith('-'):
            decisions.append(line[1:].strip())

    return meeting_type, summary.strip(), key_points, action_items, decisions

@app.route('/meeting/<int:meeting_id>')
@jwt_required
def view_meeting(meeting_id):
    """View individual meeting details"""
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM meetings WHERE id = %s AND user_id = %s', (meeting_id, request.current_user['user_id']))
        meeting = c.fetchone()

        if not meeting:
            return "Meeting not found or access denied", 404

        # Parse JSON fields
        meeting_data = dict(meeting)
        meeting_data['key_points'] = json.loads(meeting['key_points'] or '[]')
        meeting_data['action_items'] = json.loads(meeting['action_items'] or '[]')
        meeting_data['decisions'] = json.loads(meeting['decisions'] or '[]')

        return no_cache_response('notion_meeting.html', meeting=meeting_data, user=request.current_user)
    finally:
        conn.close()

@app.route('/meeting/<int:meeting_id>/edit', methods=['POST'])
@jwt_required
def edit_meeting(meeting_id):
    """Edit meeting details"""
    data = request.json

    conn = get_db()
    try:
        c = conn.cursor()

        # Update fields
        fields = []
        values = []

        if 'title' in data:
            fields.append('title = %s')
            values.append(data['title'])
        if 'summary' in data:
            fields.append('summary = %s')
            values.append(data['summary'])
        if 'attendees' in data:
            fields.append('attendees = %s')
            values.append(data['attendees'])
        if 'tags' in data:
            fields.append('tags = %s')
            values.append(data['tags'])

        if fields:
            values.append(meeting_id)
            values.append(request.current_user['user_id'])
            query = f"UPDATE meetings SET {', '.join(fields)} WHERE id = %s AND user_id = %s"
            c.execute(query, values)
            conn.commit()

        return jsonify({'success': True})
    finally:
        conn.close()

@app.route('/meeting/<int:meeting_id>/delete', methods=['POST'])
@jwt_required
def delete_meeting(meeting_id):
    """Delete a meeting"""
    conn = get_db()
    try:
        c = conn.cursor()

        # Get audio file path (verify user owns this meeting)
        c.execute('SELECT audio_file FROM meetings WHERE id = %s AND user_id = %s', (meeting_id, request.current_user['user_id']))
        result = c.fetchone()

        if not result:
            return jsonify({'error': 'Meeting not found or access denied'}), 404

        if result['audio_file']:
            # Delete audio file
            audio_path = os.path.join(app.config['UPLOAD_FOLDER'], result['audio_file'])
            if os.path.exists(audio_path):
                os.remove(audio_path)

        # Delete database entry (user_id already verified above)
        c.execute('DELETE FROM meetings WHERE id = %s AND user_id = %s', (meeting_id, request.current_user['user_id']))
        conn.commit()

        return redirect(url_for('index'))
    finally:
        conn.close()

@app.route('/api/meeting/<int:meeting_id>/delete', methods=['DELETE'])
@jwt_required
def delete_meeting_api(meeting_id):
    """Delete a meeting (API endpoint)"""
    conn = get_db()
    try:
        c = conn.cursor()

        # Get audio file path (verify user owns this meeting)
        c.execute('SELECT audio_file FROM meetings WHERE id = %s AND user_id = %s', (meeting_id, request.current_user['user_id']))
        result = c.fetchone()

        if not result:
            return jsonify({'error': 'Meeting not found or access denied'}), 404

        if result['audio_file']:
            # Delete audio file
            audio_path = os.path.join(app.config['UPLOAD_FOLDER'], result['audio_file'])
            if os.path.exists(audio_path):
                os.remove(audio_path)

        # Delete database entry (user_id already verified above)
        c.execute('DELETE FROM meetings WHERE id = %s AND user_id = %s', (meeting_id, request.current_user['user_id']))
        conn.commit()

        return jsonify({'success': True})
    finally:
        conn.close()

@app.route('/api/meeting/<int:meeting_id>/title', methods=['PUT'])
@jwt_required
def update_meeting_title(meeting_id):
    """Update meeting title (inline editing)"""
    new_title = request.json.get('title', '').strip()

    if not new_title:
        return jsonify({'error': 'Title cannot be empty'}), 400

    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            UPDATE meetings SET title = %s
            WHERE id = %s AND user_id = %s
        ''', (new_title, meeting_id, request.current_user['user_id']))

        if c.rowcount == 0:
            return jsonify({'error': 'Meeting not found or access denied'}), 404

        conn.commit()
        return jsonify({'success': True, 'title': new_title})
    finally:
        conn.close()

@app.route('/api/meeting/<int:meeting_id>/notes', methods=['PUT'])
@jwt_required
def update_meeting_notes(meeting_id):
    """Update meeting notes (inline editing)"""
    new_notes = request.json.get('notes', '')

    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            UPDATE meetings SET notes = %s
            WHERE id = %s AND user_id = %s
        ''', (new_notes, meeting_id, request.current_user['user_id']))

        if c.rowcount == 0:
            return jsonify({'error': 'Meeting not found or access denied'}), 404

        conn.commit()
        return jsonify({'success': True, 'notes': new_notes})
    finally:
        conn.close()

@app.route('/api/meetings/reorder', methods=['POST'])
@jwt_required
def reorder_meetings():
    """Update display order for meetings (drag and drop)"""
    order_data = request.json.get('order', [])

    if not order_data:
        return jsonify({'error': 'No order data provided'}), 400

    conn = get_db()
    try:
        c = conn.cursor()

        # Update display order for each meeting
        for item in order_data:
            meeting_id = item.get('id')
            display_order = item.get('order')

            if meeting_id is not None and display_order is not None:
                c.execute('''
                    UPDATE meetings
                    SET display_order = %s
                    WHERE id = %s AND user_id = %s
                ''', (display_order, meeting_id, request.current_user['user_id']))

        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()

@app.route('/api/meeting/<int:meeting_id>/regenerate', methods=['POST'])
@jwt_required
def regenerate_meeting_analysis(meeting_id):
    """Regenerate meeting analysis with new meeting type"""
    new_type = request.json.get('meeting_type', 'general')

    valid_types = ['standup', 'retrospective', 'planning', 'one-on-one', 'team-sync',
                   'brainstorming', 'review', 'client-call', 'interview', 'training', 'general']

    if new_type not in valid_types:
        return jsonify({'error': 'Invalid meeting type'}), 400

    conn = get_db()
    try:
        c = conn.cursor()

        # Get meeting and verify ownership
        c.execute('''
            SELECT transcript, audio_file, title
            FROM meetings
            WHERE id = %s AND user_id = %s
        ''', (meeting_id, request.current_user['user_id']))

        meeting = c.fetchone()
        if not meeting:
            return jsonify({'error': 'Meeting not found or access denied'}), 404

        if not meeting['transcript']:
            return jsonify({'error': 'No transcript available for regeneration'}), 400

        # Update meeting type and set status to processing
        c.execute('''
            UPDATE meetings
            SET meeting_type = %s, status = 'processing'
            WHERE id = %s AND user_id = %s
        ''', (new_type, meeting_id, request.current_user['user_id']))
        conn.commit()

        # Re-analyze in background
        def reanalyze():
            try:
                summary_prompt = f"""Analyze this meeting transcript as a {new_type.replace('-', ' ')} meeting.

Transcript:
{meeting['transcript']}

Please provide:
1. Meeting type confirmation: {new_type}
2. A brief summary (2-3 paragraphs)
3. Key discussion points (as a list)
4. Action items with assignees if mentioned (as a list)
5. Important decisions made (as a list)

Format your response as follows:

MEETING TYPE:
{new_type}

SUMMARY:
[Your summary here]

KEY POINTS:
- Point 1
- Point 2

ACTION ITEMS:
- Action 1
- Action 2

DECISIONS:
- Decision 1
- Decision 2
"""

                ollama_response = requests.post(
                    'http://ollama:11434/api/generate',
                    json={
                        'model': os.getenv('OLLAMA_MODEL', 'phi'),
                        'prompt': summary_prompt,
                        'stream': False
                    },
                    timeout=300
                )

                if ollama_response.status_code == 200:
                    analysis_text = ollama_response.json().get('response', '')
                    meeting_type_detected, summary, key_points, action_items, decisions = parse_analysis(analysis_text)

                    # Use the user-specified type
                    final_type = new_type
                else:
                    summary = "Analysis unavailable"
                    key_points = []
                    action_items = []
                    decisions = []
                    final_type = new_type

                # Update database
                conn2 = get_db()
                try:
                    c2 = conn2.cursor()
                    c2.execute('''
                        UPDATE meetings
                        SET summary = %s, key_points = %s, action_items = %s, decisions = %s, meeting_type = %s, status = 'completed'
                        WHERE id = %s
                    ''', (summary, json.dumps(key_points), json.dumps(action_items),
                          json.dumps(decisions), final_type, meeting_id))
                    conn2.commit()
                finally:
                    conn2.close()

            except Exception as e:
                print(f"Regeneration error: {e}")
                conn2 = get_db()
                try:
                    c2 = conn2.cursor()
                    c2.execute("UPDATE meetings SET status = 'completed' WHERE id = %s", (meeting_id,))
                    conn2.commit()
                finally:
                    conn2.close()

        # Start background thread
        thread = threading.Thread(target=reanalyze, daemon=True)
        thread.start()

        return jsonify({
            'success': True,
            'message': 'Regenerating analysis with new meeting type...',
            'meeting_type': new_type
        })

    finally:
        conn.close()

@app.route('/api/search', methods=['POST'])
@jwt_required
def search_meetings():
    """Search through meeting transcripts"""
    query = request.json.get('query', '')

    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT id, title, date, summary
            FROM meetings
            WHERE user_id = %s AND (transcript LIKE %s OR summary LIKE %s OR title LIKE %s)
            ORDER BY date DESC
            LIMIT 20
        ''', (request.current_user['user_id'], f'%{query}%', f'%{query}%', f'%{query}%'))

        results = [dict(row) for row in c.fetchall()]
        return jsonify(results)
    finally:
        conn.close()

@app.route('/api/stats')
@jwt_required
def get_stats():
    """Get statistics about meetings for current user"""
    conn = get_db()
    try:
        c = conn.cursor()

        c.execute('SELECT COUNT(*) as total FROM meetings WHERE user_id = %s', (request.current_user['user_id'],))
        total = c.fetchone()['total']

        c.execute("SELECT COUNT(*) as completed FROM meetings WHERE user_id = %s AND status = 'completed'", (request.current_user['user_id'],))
        completed = c.fetchone()['completed']

        c.execute("SELECT COUNT(*) as processing FROM meetings WHERE user_id = %s AND status = 'processing'", (request.current_user['user_id'],))
        processing = c.fetchone()['processing']

        return jsonify({
            'total': total,
            'completed': completed,
            'processing': processing
        })
    finally:
        conn.close()

@app.route('/download/<int:meeting_id>')
@jwt_required
def download_transcript(meeting_id):
    """Download meeting transcript as markdown"""
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM meetings WHERE id = %s AND user_id = %s', (meeting_id, request.current_user['user_id']))
        meeting = c.fetchone()

        if not meeting:
            return "Meeting not found or access denied", 404
    finally:
        conn.close()

    # Generate markdown content
    key_points = json.loads(meeting['key_points'] or '[]')
    action_items = json.loads(meeting['action_items'] or '[]')
    decisions = json.loads(meeting['decisions'] or '[]')

    content = f"""# {meeting['title']}

**Date:** {meeting['date']}
**Attendees:** {meeting['attendees'] or 'N/A'}
**Tags:** {meeting['tags'] or 'N/A'}

## Summary
{meeting['summary'] or 'No summary available'}

## Key Discussion Points
{format_list(key_points)}

## Action Items
{format_action_items(action_items)}

## Decisions
{format_list(decisions)}

---

## Full Transcript
{meeting['transcript'] or 'No transcript available'}

---
*Meeting ID: {meeting_id}*
"""

    # Save to temp file and send (using uploads folder, not /tmp which may not exist in Docker)
    temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
    os.makedirs(temp_dir, exist_ok=True)

    filename = f"{meeting['title'].replace(' ', '_')}_{meeting_id}.md"
    temp_path = os.path.join(temp_dir, filename)
    with open(temp_path, 'w') as f:
        f.write(content)

    return send_from_directory(temp_dir, filename, as_attachment=True)

def format_list(items):
    """Format list items as markdown"""
    if not items:
        return "- None recorded"
    return "\n".join([f"- {item}" for item in items])

def format_action_items(items):
    """Format action items with checkboxes"""
    if not items:
        return "- [ ] No action items"
    return "\n".join([f"- [ ] {item}" for item in items])

@app.route('/api/live/start', methods=['POST'])
@jwt_required
def start_live_session():
    """Start a new live recording session"""
    data = request.json
    title = data.get('title', 'Live Meeting')
    timestamp = data.get('timestamp', datetime.datetime.now().isoformat())

    # Generate session ID
    session_id = f"live_{int(time.time())}_{os.urandom(4).hex()}"

    # Create meeting entry in database with user_id
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            INSERT INTO meetings (user_id, title, status)
            VALUES (%s, %s, 'recording')
            RETURNING id
        ''', (request.current_user['user_id'], title))
        meeting_id = c.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    # Store session info with user_id for verification
    live_sessions[session_id] = {
        'user_id': request.current_user['user_id'],
        'meeting_id': meeting_id,
        'title': title,
        'start_time': time.time(),
        'chunks': [],
        'transcript_parts': []
    }

    return jsonify({
        'success': True,
        'session_id': session_id,
        'meeting_id': meeting_id
    })

@app.route('/api/live/chunk', methods=['POST'])
@jwt_required
def receive_live_chunk():
    """Receive and process audio chunk from live session"""
    session_id = request.form.get('session_id')

    if not session_id or session_id not in live_sessions:
        return jsonify({'error': 'Invalid session'}), 400

    # Verify session belongs to current user
    if live_sessions[session_id]['user_id'] != request.current_user['user_id']:
        return jsonify({'error': 'Access denied'}), 403

    # Get audio chunk
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio data'}), 400

    audio_file = request.files['audio']

    # Save chunk temporarily
    chunk_filename = f"chunk_{session_id}_{len(live_sessions[session_id]['chunks'])}.wav"
    chunk_path = os.path.join(app.config['UPLOAD_FOLDER'], chunk_filename)
    audio_file.save(chunk_path)

    # Store chunk reference
    live_sessions[session_id]['chunks'].append(chunk_path)

    # Transcribe chunk with Whisper
    try:
        with open(chunk_path, 'rb') as f:
            response = requests.post(
                'http://whisper:9000/asr?task=transcribe&language=en&output=json',
                files={'audio_file': f},
                timeout=60
            )

        if response.status_code == 200:
            transcript_data = response.json()
            text = transcript_data.get('text', '').strip()

            if text:
                live_sessions[session_id]['transcript_parts'].append(text)

                # Update database with current transcript
                meeting_id = live_sessions[session_id]['meeting_id']
                full_transcript = ' '.join(live_sessions[session_id]['transcript_parts'])

                conn = get_db()
                try:
                    c = conn.cursor()
                    c.execute('UPDATE meetings SET transcript = %s WHERE id = %s',
                              (full_transcript, meeting_id))
                    conn.commit()
                finally:
                    conn.close()

                return jsonify({'success': True, 'text': text})

        return jsonify({'success': True, 'text': ''})

    except Exception as e:
        print(f"Error transcribing chunk: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/live/stop', methods=['POST'])
@jwt_required
def stop_live_session():
    """Stop live recording session and finalize"""
    data = request.json
    session_id = data.get('session_id')

    if not session_id or session_id not in live_sessions:
        return jsonify({'error': 'Invalid session'}), 400

    session = live_sessions[session_id]

    # Verify session belongs to current user
    if session['user_id'] != request.current_user['user_id']:
        return jsonify({'error': 'Access denied'}), 403

    meeting_id = session['meeting_id']

    # Combine all transcript parts
    full_transcript = ' '.join(session['transcript_parts'])

    # Run AI analysis on full transcript
    try:
        summary_prompt = f"""Analyze this meeting transcript and provide a structured response.

Transcript:
{full_transcript}

Please provide:
1. A brief summary (2-3 paragraphs)
2. Key discussion points (as a list)
3. Action items with assignees if mentioned (as a list)
4. Important decisions made (as a list)

Format your response as follows:

SUMMARY:
[Your summary here]

KEY POINTS:
- Point 1
- Point 2

ACTION ITEMS:
- Action 1
- Action 2

DECISIONS:
- Decision 1
- Decision 2
"""

        ollama_response = requests.post(
            'http://ollama:11434/api/generate',
            json={
                'model': os.getenv('OLLAMA_MODEL', 'phi'),
                'prompt': summary_prompt,
                'stream': False
            },
            timeout=300
        )

        if ollama_response.status_code == 200:
            analysis_text = ollama_response.json().get('response', '')
            meeting_type, summary, key_points, action_items, decisions = parse_analysis(analysis_text)
        else:
            meeting_type = "general"
            summary = "Analysis unavailable"
            key_points = []
            action_items = []
            decisions = []

    except Exception as e:
        print(f"Analysis error: {e}")
        meeting_type = "general"
        summary = "Analysis failed"
        key_points = []
        action_items = []
        decisions = []

    # Update database with final results
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            UPDATE meetings
            SET transcript = %s, summary = %s, key_points = %s, action_items = %s, decisions = %s, meeting_type = %s, status = 'completed'
            WHERE id = %s
        ''', (full_transcript, summary, json.dumps(key_points), json.dumps(action_items),
              json.dumps(decisions), meeting_type, meeting_id))
        conn.commit()
    finally:
        conn.close()

    # Clean up chunk files
    for chunk_path in session['chunks']:
        try:
            if os.path.exists(chunk_path):
                os.remove(chunk_path)
        except Exception as e:
            print(f"Error deleting chunk: {e}")

    # Remove session from memory
    del live_sessions[session_id]

    return jsonify({
        'success': True,
        'meeting_id': meeting_id
    })

@app.route('/live')
@jwt_required
def live_recording_page():
    """Live recording interface"""
    return no_cache_response('live.html', user=request.current_user)

@app.route('/api/queue/status', methods=['GET'])
@jwt_required
def queue_status():
    """Get queue status and user's jobs"""
    with queue_lock:
        # Get active jobs for current user
        user_active_jobs = [
            {
                'job_id': job_id,
                'meeting_id': job['meeting_id'],
                'status': job['status'],
                'started_at': job.get('started_at'),
                'processing_time': time.time() - job.get('started_at', time.time()) if 'started_at' in job else 0
            }
            for job_id, job in active_jobs.items()
        ]

        # Get queue size and active count
        queue_size = processing_queue.qsize()
        active_count = len([j for j in active_jobs.values() if j['status'] == 'processing'])
        max_concurrent = app.config['MAX_CONCURRENT_JOBS']

    return jsonify({
        'queue': {
            'size': queue_size,
            'active_jobs': active_count,
            'max_concurrent': max_concurrent,
            'available_workers': max_concurrent - active_count
        },
        'user_jobs': user_active_jobs
    }), 200

@app.route('/downloads/<path:filename>')
def download_client_file(filename):
    """Download client files"""
    client_dir = os.path.join(os.path.dirname(__file__), 'client')

    # Security: only allow specific files
    allowed_files = [
        'audio_capture.py',
        'requirements.txt',
        'install_linux.sh',
        'install_macos.sh',
        'install_windows.bat',
        'meeting_monitor.py',
        'calendar_integration.py'
    ]

    if filename not in allowed_files:
        return jsonify({'error': 'File not found'}), 404

    try:
        return send_from_directory(client_dir, filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404

@app.route('/downloads/all')
def download_all_files():
    """Download all client files as a zip archive"""
    client_dir = os.path.join(os.path.dirname(__file__), 'client')

    # Create a zip file in memory
    memory_file = io.BytesIO()

    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add all client files
        client_files = [
            'audio_capture.py',
            'requirements.txt',
            'install_linux.sh',
            'install_macos.sh',
            'install_windows.bat',
            'meeting_monitor.py',
            'calendar_integration.py'
        ]

        for filename in client_files:
            file_path = os.path.join(client_dir, filename)
            if os.path.exists(file_path):
                zf.write(file_path, filename)

    # Seek to the beginning of the BytesIO object
    memory_file.seek(0)

    # Send the zip file
    return send_from_directory(
        directory=os.path.dirname(__file__),
        path='',
        as_attachment=True,
        download_name='meeting-transcriber-client.zip',
        mimetype='application/zip'
    ) if False else (memory_file.getvalue(), 200, {
        'Content-Type': 'application/zip',
        'Content-Disposition': 'attachment; filename=meeting-transcriber-client.zip'
    })

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.datetime.now().isoformat()})

# Initialize database on startup (works with both Flask dev server and Gunicorn)
init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
