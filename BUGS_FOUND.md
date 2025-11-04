# Comprehensive Bug Analysis

## CRITICAL BUGS (Must Fix Immediately)

### 1. **SQL Syntax Error** (Lines 374, 377)
**Bug:** Using double quotes for string literals instead of single quotes
```python
c.execute('SELECT COUNT(*) as completed FROM meetings WHERE status = "completed"')
```
**Impact:** Query will fail in PostgreSQL
**Fix:** Change to single quotes: `WHERE status = 'completed'`

### 2. **Hard-coded Model Name** (Lines 196, 595)
**Bug:** Using `'llama2'` instead of environment variable
```python
'model': 'llama2',
```
**Impact:** 8GB RAM VPS will crash trying to load llama2 (needs 16GB). Should use 'phi' model.
**Fix:** Use `os.getenv('OLLAMA_MODEL', 'phi')`

### 3. **Live Sessions Lost on Restart** (Line 475)
**Bug:** `live_sessions = {}` is in-memory dictionary
```python
live_sessions[session_id] = {...}
```
**Impact:** Active recordings lost on crash/restart
**Fix:** Store session state in database, not memory

### 4. **Blocking Audio Processing** (Line 114)
**Bug:** Synchronous processing blocks Gunicorn worker
```python
process_meeting_audio(filepath, meeting_id, title)
```
**Impact:** With 2 workers, only 2 files can be processed simultaneously. 3rd request hangs.
**Fix:** Use background task queue (Celery) or thread pool

### 5. **Using /tmp in Docker** (Line 434)
**Bug:** Saving downloads to `/tmp` which might not exist or have space
```python
temp_path = os.path.join('/tmp', filename)
```
**Impact:** Download fails if /tmp is full or read-only
**Fix:** Use `/app/uploads/temp/` directory

### 6. **No Database Connection Pooling**
**Bug:** Creating new connection for every request
```python
def get_db():
    conn = psycopg2.connect(app.config['DATABASE_URL'])
```
**Impact:** Connection exhaustion under load (PostgreSQL default: 100 connections)
**Fix:** Use connection pooling (psycopg2.pool or Flask-SQLAlchemy)

### 7. **No Authentication**
**Bug:** All endpoints publicly accessible
**Impact:** Anyone can:
- Upload files (abuse storage/compute)
- Delete meetings
- View all transcripts
- Start expensive transcription jobs
**Fix:** Add API key authentication or OAuth

### 8. **No Error Handling on DB Operations**
**Bug:** Many database operations lack try/except
```python
conn = get_db()
c = conn.cursor()
c.execute(...)  # Could fail
conn.commit()   # Could fail
```
**Impact:** Crashes leave database in inconsistent state, connections leak
**Fix:** Wrap all DB operations in try/finally, ensure conn.close()

## HIGH PRIORITY BUGS

### 9. **No Rate Limiting**
**Impact:** Abuse of expensive Whisper/Ollama operations
**Fix:** Add Flask-Limiter

### 10. **No Orphaned File Cleanup**
**Bug:** Audio files remain when transcription fails
**Impact:** Disk space leak
**Fix:** Add cleanup task for files with status='error' older than 7 days

### 11. **Search Query SQL Injection Risk** (Line 355)
**Bug:** LIKE query with user input
```python
WHERE transcript LIKE %s
```
**Impact:** Could cause ReDoS with malicious patterns like `%%%%%`
**Fix:** Use full-text search (PostgreSQL tsvector) or limit query length

### 12. **No Pagination**
**Bug:** Dashboard loads 50 meetings every time (line 57)
**Impact:** Slow page loads as data grows
**Fix:** Add pagination with offset/limit

## MEDIUM PRIORITY

### 13. **Minimal Logging**
Using `print()` instead of proper logging
**Fix:** Configure Python logging with log levels

### 14. **Hard-coded English** (Line 136)
`language=en` hard-coded
**Fix:** Allow user to select language

### 15. **No Metrics/Monitoring**
Only basic health check
**Fix:** Add Prometheus metrics endpoint

### 16. **No CORS Configuration**
Could block frontend if hosted separately
**Fix:** Add Flask-CORS

## LOW PRIORITY

### 17. **No API Versioning**
Endpoints like `/api/search` not versioned
**Fix:** Use `/api/v1/search`

### 18. **No Request Validation**
Many endpoints don't validate input
**Fix:** Add JSON schema validation

### 19. **No Audio Format Validation**
Accepts any file upload
**Fix:** Check file extension and MIME type

### 20. **Session Security**
SECRET_KEY from environment but no session configuration
**Fix:** Configure session timeout, secure cookies

## Summary

**Critical bugs that will cause production failures:**
- SQL syntax errors (will crash queries)
- Wrong model name (will OOM the VPS)
- Blocking operations (will hang under load)
- No connection pooling (will exhaust connections)
- No authentication (security nightmare)

**Estimated time to fix critical bugs:** 2-3 hours
**Recommended:** Fix criticals before any production deployment
