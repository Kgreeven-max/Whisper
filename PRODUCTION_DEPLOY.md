# Production Deployment Guide

This system is 100% production-ready with no placeholders. Follow these simple steps to deploy to your VPS.

## 🚀 Quick Deploy (5 Minutes)

### Prerequisites
- VPS with 8GB RAM minimum (Raspberry Pi 5 or equivalent)
- Docker and Docker Compose installed
- Git installed

### Step 1: Clone & Setup

```bash
git clone <your-repo-url>
cd Whisper
chmod +x setup.sh
./setup.sh
```

The `setup.sh` script will automatically:
- Generate secure SECRET_KEY and JWT_SECRET
- Create .env file with all required configuration
- Pull and start all Docker containers
- Initialize PostgreSQL database with all tables
- Start Whisper AI and Ollama services

### Step 2: Verify Deployment

```bash
docker-compose ps
```

You should see 4 services running:
- `flask` - Main application (port 5001)
- `whisper` - Audio transcription AI
- `ollama` - Analysis AI (Phi model)
- `postgres` - Database

### Step 3: Access Your Application

Open your browser and navigate to:
```
http://your-vps-ip:5001
```

You'll be redirected to the login page. Create your first account!

## 🔐 Security Features

### JWT Authentication
- **Access Tokens**: 1-hour expiry
- **Refresh Tokens**: 30-day expiry (revocable)
- **Auto-Refresh**: Tokens refresh automatically before expiry
- **Secure Storage**: Tokens stored in localStorage with HTTPS recommended

### Password Security
- **Bcrypt Hashing**: Industry-standard password encryption
- **Security Questions**: Password reset without email
- **Minimum 8 Characters**: Enforced password strength

### User Isolation
- **Complete Data Separation**: Users can only see their own meetings
- **Database-Level Security**: Foreign key constraints with CASCADE DELETE
- **Query-Level Protection**: user_id filter on all queries
- **Session Validation**: JWT verified on every request

## 🎯 Core Features

### 1. Meeting Type Auto-Detection
- **11 Meeting Types**: Standup, Retrospective, Planning, One-on-One, Team Sync, Brainstorming, Review, Client Call, Interview, Training, General
- **AI-Powered**: Ollama automatically classifies meetings from transcripts
- **Manual Override**: Users can select type during upload
- **Smart Display**: Types shown with emoji icons on dashboard

### 2. Task Queue System
- **Resource Management**: Prevents RAM overload
- **Configurable Concurrency**: MAX_CONCURRENT_JOBS (default: 2 for 8GB RAM)
- **Fair Processing**: FIFO queue ensures fair processing order
- **Real-time Status**: Users see queue position and estimated wait time
- **Background Processing**: Non-blocking uploads with immediate feedback

### 3. Complete User Flow
- **Registration** → Security question setup → Auto-login → Dashboard
- **Login** → JWT tokens stored → Full access
- **Upload** → Type selection → Queue → Processing → View results
- **Forgot Password** → Security question → Reset → Login
- **Logout** → Tokens revoked → Redirect to login

### 4. Real-time Updates
- **Auto-Refresh**: Processing meetings update every 5 seconds
- **Queue Status**: Live queue position and wait time
- **Progress Indicators**: Upload progress bars
- **Status Badges**: Clear visual status (Queued, Processing, Completed, Error)

## 📊 Meeting Processing Flow

1. **Upload** (202 Accepted)
   - File saved to persistent volume
   - Database entry created with user_id
   - Job added to queue
   - Queue info returned immediately

2. **Queue** (Background)
   - Worker threads process max 2 jobs simultaneously
   - Status updates in database
   - Queue position tracked

3. **Transcription** (Whisper AI)
   - Audio transcribed to text
   - Language detection
   - High accuracy with small model

4. **Analysis** (Ollama Phi)
   - Meeting type classification
   - Summary generation
   - Key points extraction
   - Action items identification
   - Decisions recorded

5. **Completion**
   - Status updated to 'completed'
   - Full transcript available
   - Download as Markdown
   - Action item checklist

## 🗄️ Database Schema

### Users Table
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    security_question TEXT NOT NULL,
    security_answer_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);
```

### Meetings Table
```sql
CREATE TABLE meetings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    audio_file TEXT,
    transcript TEXT,
    summary TEXT,
    action_items TEXT,  -- JSON array
    key_points TEXT,    -- JSON array
    decisions TEXT,     -- JSON array
    attendees TEXT,
    duration INTEGER,
    tags TEXT,
    status TEXT DEFAULT 'processing',
    meeting_type TEXT DEFAULT 'general'
);
```

### Refresh Tokens Table
```sql
CREATE TABLE refresh_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 🔧 Configuration

### Environment Variables (.env)

```bash
# Flask Configuration
FLASK_ENV=production
SECRET_KEY=<auto-generated-64-chars>
JWT_SECRET=<auto-generated-64-chars>

# Database Configuration
POSTGRES_USER=meeting_user
POSTGRES_PASSWORD=<auto-generated-32-chars>
POSTGRES_DB=meetings

# AI Configuration
OLLAMA_MODEL=phi
WHISPER_MODEL=small

# Resource Management
MAX_CONCURRENT_JOBS=2  # Adjust based on RAM (2 for 8GB, 4 for 16GB+)
```

### Scaling Guidelines

**8GB RAM VPS:**
- MAX_CONCURRENT_JOBS=2
- Each job uses ~2-3GB during processing
- Can handle 4-6 concurrent users comfortably

**16GB+ RAM VPS:**
- MAX_CONCURRENT_JOBS=4
- Can handle 8-12 concurrent users

## 🌐 API Endpoints

### Authentication
- `GET /auth/login` - Login page
- `POST /auth/login` - Login API (returns JWT tokens)
- `GET /auth/register` - Registration page
- `POST /auth/register` - Registration API
- `GET /auth/forgot-password` - Password reset page
- `POST /auth/forgot-password/question` - Get security question
- `POST /auth/reset-password` - Reset password
- `POST /auth/refresh` - Refresh access token
- `POST /auth/logout` - Logout (revoke refresh token)

### Meetings
- `GET /` - Dashboard (requires JWT)
- `GET /upload` - Upload page (requires JWT)
- `POST /upload` - Upload meeting (returns 202 with queue info)
- `GET /meeting/<id>` - View meeting details
- `POST /meeting/<id>/delete` - Delete meeting
- `GET /download/<id>` - Download transcript as Markdown

### Queue Management
- `GET /api/queue/status` - Get queue status and user jobs
- `GET /api/stats` - Get user statistics

### Search
- `POST /api/search` - Search meetings by title, content, tags

### Live Recording
- `GET /live` - Live recording page
- `POST /api/live/start` - Start live session
- `POST /api/live/chunk` - Send audio chunk
- `POST /api/live/stop` - Stop live session

## 🧪 Testing Checklist

### Registration Flow
- [ ] Navigate to `/auth/register`
- [ ] Fill in username, email, password
- [ ] Select security question and answer
- [ ] Submit → Should auto-login and redirect to dashboard

### Login Flow
- [ ] Navigate to `/auth/login`
- [ ] Enter credentials
- [ ] Submit → Should redirect to dashboard
- [ ] Check that username appears in header
- [ ] Verify logout button works

### Password Reset Flow
- [ ] Click "Forgot password?" on login page
- [ ] Enter username → Should show security question
- [ ] Answer question → Enter new password
- [ ] Submit → Should redirect to login
- [ ] Login with new password

### Upload Flow
- [ ] Click "Upload Meeting" button
- [ ] Fill in meeting details
- [ ] Select meeting type (or use auto-detect)
- [ ] Drag & drop or select audio file
- [ ] Submit → Should show progress bar
- [ ] After upload → Redirects to meeting page
- [ ] Meeting should show "Queued" or "Processing" status
- [ ] Page auto-refreshes every 5 seconds
- [ ] After processing → Full transcript and analysis shown

### Meeting View
- [ ] Click on meeting from dashboard
- [ ] Verify meeting type is displayed
- [ ] Verify status is shown correctly
- [ ] Check action items have checkboxes
- [ ] Checkbox state persists in localStorage
- [ ] Download transcript as Markdown works
- [ ] Delete meeting works (with confirmation)

### Dashboard
- [ ] Verify all meetings shown are user's own
- [ ] Search functionality works
- [ ] Meeting type badges display correctly
- [ ] Queue status shown for processing meetings
- [ ] Statistics cards update correctly

### Security
- [ ] Logout works and redirects to login
- [ ] After logout, accessing `/` redirects to login
- [ ] Token refresh works automatically
- [ ] Cannot access other users' meetings
- [ ] Session expires after token expiry

## 📝 Maintenance

### Logs
```bash
# View application logs
docker-compose logs -f flask

# View Whisper logs
docker-compose logs -f whisper

# View Ollama logs
docker-compose logs -f ollama

# View PostgreSQL logs
docker-compose logs -f postgres
```

### Database Backup
```bash
# Backup database
docker-compose exec postgres pg_dump -U meeting_user meetings > backup.sql

# Restore database
docker-compose exec -T postgres psql -U meeting_user meetings < backup.sql
```

### Restart Services
```bash
# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart flask
```

### Update Application
```bash
git pull
docker-compose build flask
docker-compose up -d
```

## 🚨 Troubleshooting

### Issue: Containers won't start
```bash
# Check logs
docker-compose logs

# Rebuild containers
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Issue: Database connection errors
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check database logs
docker-compose logs postgres

# Restart PostgreSQL
docker-compose restart postgres
```

### Issue: Upload fails
```bash
# Check disk space
df -h

# Check uploads directory permissions
ls -la uploads/

# Check Flask logs
docker-compose logs flask
```

### Issue: Processing stuck
```bash
# Check Whisper service
docker-compose logs whisper

# Check Ollama service
docker-compose logs ollama

# Check queue status via API
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:5001/api/queue/status
```

## 🎉 Success Indicators

Your deployment is successful when:
1. ✅ All 4 Docker containers are running
2. ✅ You can access the login page
3. ✅ You can register a new account
4. ✅ You can upload and process a meeting
5. ✅ You see full transcript and analysis
6. ✅ Dashboard shows your meetings correctly
7. ✅ Security features work (logout, password reset)
8. ✅ Multiple users can use the system simultaneously

## 📧 Support

For issues or questions:
1. Check this documentation
2. Review application logs
3. Check GitHub issues
4. Verify all environment variables are set correctly

---

**Deployment Time**: ~5 minutes
**First Meeting Processed**: ~2-5 minutes (depending on audio length)
**System Ready**: Immediate after setup
**Zero Configuration**: Everything auto-configured by setup.sh
