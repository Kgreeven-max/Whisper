from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
import requests
import os
import json
import datetime
import sqlite3
from werkzeug.utils import secure_filename
import time

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/app/uploads'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['DATABASE'] = '/app/data/meetings.db'

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('/app/data', exist_ok=True)

# Store active live recording sessions
live_sessions = {}

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            status TEXT DEFAULT 'processing'
        )
    ''')
    conn.commit()
    conn.close()

@app.route('/')
def index():
    """Main dashboard showing all meetings"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM meetings ORDER BY date DESC LIMIT 50')
    meetings = c.fetchall()
    conn.close()
    return render_template('dashboard.html', meetings=meetings)

@app.route('/upload', methods=['GET', 'POST'])
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

        # Save uploaded file
        filename = secure_filename(file.filename)
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Create initial database entry
        conn = get_db()
        c = conn.cursor()
        c.execute('''
            INSERT INTO meetings (title, audio_file, attendees, tags, status)
            VALUES (?, ?, ?, ?, 'processing')
        ''', (title, filename, attendees, tags))
        meeting_id = c.lastrowid
        conn.commit()
        conn.close()

        # Process the meeting asynchronously
        try:
            process_meeting_audio(filepath, meeting_id, title)
        except Exception as e:
            # Update status to error
            conn = get_db()
            c = conn.cursor()
            c.execute('UPDATE meetings SET status = ? WHERE id = ?', ('error', meeting_id))
            conn.commit()
            conn.close()
            return jsonify({'error': str(e)}), 500

        return redirect(url_for('view_meeting', meeting_id=meeting_id))

    return render_template('upload.html')

def process_meeting_audio(audio_path, meeting_id, title):
    """Process audio through Whisper and Ollama"""

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
        c = conn.cursor()
        c.execute('UPDATE meetings SET status = ?, transcript = ? WHERE id = ?',
                  ('error', f'Transcription failed: {str(e)}', meeting_id))
        conn.commit()
        conn.close()
        return

    # Step 2: Generate summary with Ollama (local LLM)
    print(f"Analyzing transcript for meeting {meeting_id}...")
    try:
        summary_prompt = f"""Analyze this meeting transcript and provide a structured response.

Transcript:
{transcript}

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
                'model': 'llama2',
                'prompt': summary_prompt,
                'stream': False
            },
            timeout=300  # 5 minutes timeout
        )

        if ollama_response.status_code != 200:
            raise Exception(f"Ollama API error: {ollama_response.status_code}")

        analysis_text = ollama_response.json().get('response', '')

        # Parse the structured response
        summary, key_points, action_items, decisions = parse_analysis(analysis_text)

    except Exception as e:
        print(f"Analysis error: {e}")
        summary = "Analysis failed"
        key_points = []
        action_items = []
        decisions = []

    # Step 3: Update database with results
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        UPDATE meetings
        SET transcript = ?, summary = ?, key_points = ?, action_items = ?, decisions = ?, status = 'completed'
        WHERE id = ?
    ''', (transcript, summary, json.dumps(key_points), json.dumps(action_items),
          json.dumps(decisions), meeting_id))
    conn.commit()
    conn.close()

    print(f"Meeting {meeting_id} processed successfully")

def parse_analysis(text):
    """Parse the structured analysis response"""
    summary = ""
    key_points = []
    action_items = []
    decisions = []

    current_section = None
    lines = text.split('\n')

    for line in lines:
        line = line.strip()

        if 'SUMMARY:' in line.upper():
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

        if current_section == 'summary' and line:
            summary += line + " "
        elif current_section == 'key_points' and line.startswith('-'):
            key_points.append(line[1:].strip())
        elif current_section == 'action_items' and line.startswith('-'):
            action_items.append(line[1:].strip())
        elif current_section == 'decisions' and line.startswith('-'):
            decisions.append(line[1:].strip())

    return summary.strip(), key_points, action_items, decisions

@app.route('/meeting/<int:meeting_id>')
def view_meeting(meeting_id):
    """View individual meeting details"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM meetings WHERE id = ?', (meeting_id,))
    meeting = c.fetchone()
    conn.close()

    if not meeting:
        return "Meeting not found", 404

    # Parse JSON fields
    meeting_data = dict(meeting)
    meeting_data['key_points'] = json.loads(meeting['key_points'] or '[]')
    meeting_data['action_items'] = json.loads(meeting['action_items'] or '[]')
    meeting_data['decisions'] = json.loads(meeting['decisions'] or '[]')

    return render_template('meeting.html', meeting=meeting_data)

@app.route('/meeting/<int:meeting_id>/edit', methods=['POST'])
def edit_meeting(meeting_id):
    """Edit meeting details"""
    data = request.json

    conn = get_db()
    c = conn.cursor()

    # Update fields
    fields = []
    values = []

    if 'title' in data:
        fields.append('title = ?')
        values.append(data['title'])
    if 'summary' in data:
        fields.append('summary = ?')
        values.append(data['summary'])
    if 'attendees' in data:
        fields.append('attendees = ?')
        values.append(data['attendees'])
    if 'tags' in data:
        fields.append('tags = ?')
        values.append(data['tags'])

    if fields:
        values.append(meeting_id)
        query = f"UPDATE meetings SET {', '.join(fields)} WHERE id = ?"
        c.execute(query, values)
        conn.commit()

    conn.close()
    return jsonify({'success': True})

@app.route('/meeting/<int:meeting_id>/delete', methods=['POST'])
def delete_meeting(meeting_id):
    """Delete a meeting"""
    conn = get_db()
    c = conn.cursor()

    # Get audio file path
    c.execute('SELECT audio_file FROM meetings WHERE id = ?', (meeting_id,))
    result = c.fetchone()

    if result and result['audio_file']:
        # Delete audio file
        audio_path = os.path.join(app.config['UPLOAD_FOLDER'], result['audio_file'])
        if os.path.exists(audio_path):
            os.remove(audio_path)

    # Delete database entry
    c.execute('DELETE FROM meetings WHERE id = ?', (meeting_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('index'))

@app.route('/api/search', methods=['POST'])
def search_meetings():
    """Search through meeting transcripts"""
    query = request.json.get('query', '')

    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT id, title, date, summary
        FROM meetings
        WHERE transcript LIKE ? OR summary LIKE ? OR title LIKE ?
        ORDER BY date DESC
        LIMIT 20
    ''', (f'%{query}%', f'%{query}%', f'%{query}%'))

    results = [dict(row) for row in c.fetchall()]
    conn.close()

    return jsonify(results)

@app.route('/api/stats')
def get_stats():
    """Get statistics about meetings"""
    conn = get_db()
    c = conn.cursor()

    c.execute('SELECT COUNT(*) as total FROM meetings')
    total = c.fetchone()['total']

    c.execute('SELECT COUNT(*) as completed FROM meetings WHERE status = "completed"')
    completed = c.fetchone()['completed']

    c.execute('SELECT COUNT(*) as processing FROM meetings WHERE status = "processing"')
    processing = c.fetchone()['processing']

    conn.close()

    return jsonify({
        'total': total,
        'completed': completed,
        'processing': processing
    })

@app.route('/download/<int:meeting_id>')
def download_transcript(meeting_id):
    """Download meeting transcript as markdown"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM meetings WHERE id = ?', (meeting_id,))
    meeting = c.fetchone()
    conn.close()

    if not meeting:
        return "Meeting not found", 404

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

    # Save to temp file and send
    filename = f"{meeting['title'].replace(' ', '_')}_{meeting_id}.md"
    temp_path = os.path.join('/tmp', filename)
    with open(temp_path, 'w') as f:
        f.write(content)

    return send_from_directory('/tmp', filename, as_attachment=True)

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
def start_live_session():
    """Start a new live recording session"""
    data = request.json
    title = data.get('title', 'Live Meeting')
    timestamp = data.get('timestamp', datetime.datetime.now().isoformat())

    # Generate session ID
    session_id = f"live_{int(time.time())}_{os.urandom(4).hex()}"

    # Create meeting entry in database
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO meetings (title, status)
        VALUES (?, 'recording')
    ''', (title,))
    meeting_id = c.lastrowid
    conn.commit()
    conn.close()

    # Store session info
    live_sessions[session_id] = {
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
def receive_live_chunk():
    """Receive and process audio chunk from live session"""
    session_id = request.form.get('session_id')

    if not session_id or session_id not in live_sessions:
        return jsonify({'error': 'Invalid session'}), 400

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
                c = conn.cursor()
                c.execute('UPDATE meetings SET transcript = ? WHERE id = ?',
                          (full_transcript, meeting_id))
                conn.commit()
                conn.close()

                return jsonify({'success': True, 'text': text})

        return jsonify({'success': True, 'text': ''})

    except Exception as e:
        print(f"Error transcribing chunk: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/live/stop', methods=['POST'])
def stop_live_session():
    """Stop live recording session and finalize"""
    data = request.json
    session_id = data.get('session_id')

    if not session_id or session_id not in live_sessions:
        return jsonify({'error': 'Invalid session'}), 400

    session = live_sessions[session_id]
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
                'model': 'llama2',
                'prompt': summary_prompt,
                'stream': False
            },
            timeout=300
        )

        if ollama_response.status_code == 200:
            analysis_text = ollama_response.json().get('response', '')
            summary, key_points, action_items, decisions = parse_analysis(analysis_text)
        else:
            summary = "Analysis unavailable"
            key_points = []
            action_items = []
            decisions = []

    except Exception as e:
        print(f"Analysis error: {e}")
        summary = "Analysis failed"
        key_points = []
        action_items = []
        decisions = []

    # Update database with final results
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        UPDATE meetings
        SET transcript = ?, summary = ?, key_points = ?, action_items = ?, decisions = ?, status = 'completed'
        WHERE id = ?
    ''', (full_transcript, summary, json.dumps(key_points), json.dumps(action_items),
          json.dumps(decisions), meeting_id))
    conn.commit()
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
def live_recording_page():
    """Live recording interface"""
    return render_template('live.html')

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.datetime.now().isoformat()})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080, debug=False)
