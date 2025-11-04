# Task Queue System - Resource Management

## 🚦 Problem Solved

With **8GB RAM and multiple users**, concurrent transcription jobs would exhaust system resources and crash the VPS. The task queue system prevents this by:

✅ **Limiting concurrent transcriptions** (default: 2 for 8GB RAM)
✅ **Queuing additional jobs** (processed in order)
✅ **Returning immediately** to users (no blocking)
✅ **Tracking queue position** (users see their place in line)
✅ **Automatic processing** (background workers)

## How It Works

### Architecture

```
User uploads audio → Queue system → Worker threads → Whisper/Ollama → Database
                        ↓
                  Max 2 concurrent
                  (configurable)
```

1. User uploads audio file
2. File saved, database record created with status "queued"
3. Job added to queue
4. **Returns immediately** with queue position
5. Background worker picks up job when slot available
6. Processes audio (Whisper + Ollama)
7. Updates database with results

### Benefits

- **No RAM overload**: Max 2 jobs process simultaneously (each uses ~2-3GB)
- **Fair queuing**: First-come, first-served
- **No blocking**: Users don't wait, can upload multiple files
- **Visibility**: Users see queue position and estimated wait
- **Scalable**: Increase workers for servers with more RAM

## Configuration

### Environment Variable

```bash
# .env file
MAX_CONCURRENT_JOBS=2    # For 8GB RAM
# MAX_CONCURRENT_JOBS=4  # For 16GB RAM
# MAX_CONCURRENT_JOBS=8  # For 32GB+ RAM
```

Each job uses approximately **2-3GB RAM** during processing:
- Whisper transcription: ~1-2GB
- Ollama analysis: ~1-2GB

### Recommended Settings

| VPS RAM | MAX_CONCURRENT_JOBS | Notes |
|---------|---------------------|-------|
| 4GB | 1 | Minimum, may be slow |
| 8GB | 2 | ✅ Recommended |
| 16GB | 4 | Faster processing |
| 32GB+ | 8 | Maximum throughput |

## API Endpoints

### 1. Upload Audio (Returns Immediately)

```bash
POST /upload
Authorization: Bearer <token>
Content-Type: multipart/form-data

Response (202 Accepted):
{
  "success": true,
  "meeting_id": 123,
  "message": "Meeting uploaded and queued for processing",
  "queue_info": {
    "job_id": "job_123_1699999999",
    "queue_position": 3,
    "active_jobs": 2,
    "estimated_wait_seconds": 120
  }
}
```

**Status Code: 202 Accepted** - Job queued, will process asynchronously

### 2. Check Queue Status

```bash
GET /api/queue/status
Authorization: Bearer <token>

Response:
{
  "queue": {
    "size": 5,                    # Jobs waiting in queue
    "active_jobs": 2,             # Currently processing
    "max_concurrent": 2,          # Max simultaneous jobs
    "available_workers": 0        # Free worker slots
  },
  "user_jobs": [
    {
      "job_id": "job_123_1699999999",
      "meeting_id": 123,
      "status": "processing",
      "started_at": 1699999999.123,
      "processing_time": 45.5     # seconds
    }
  ]
}
```

### 3. Check Meeting Status

```bash
GET /meeting/123
Authorization: Bearer <token>

Response:
meeting.status values:
- "queued" - In queue, waiting
- "queued (position N)" - In queue at position N
- "processing" - Currently transcribing/analyzing
- "completed" - Done!
- "error" - Failed
```

## Frontend Integration (Loading Bars & Queue UI)

### Option 1: Simple Polling (Recommended)

```html
<div id="upload-status" style="display:none;">
  <h3>Processing Your Meeting...</h3>
  <div class="progress-bar-container">
    <div id="progress-bar" class="progress-bar"></div>
  </div>
  <p id="status-message">Uploading...</p>
  <p id="queue-info"></p>
</div>

<script>
async function uploadAudio(formData) {
  const token = localStorage.getItem('access_token');

  // Show loading UI
  document.getElementById('upload-status').style.display = 'block';

  // Upload file
  const response = await fetch('/upload', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`
    },
    body: formData
  });

  const data = await response.json();

  if (data.success) {
    const meetingId = data.meeting_id;
    const queueInfo = data.queue_info;

    // Show queue position
    document.getElementById('queue-info').textContent =
      `Queue position: ${queueInfo.queue_position} | ` +
      `Estimated wait: ${Math.ceil(queueInfo.estimated_wait_seconds / 60)} minutes`;

    // Start polling for status
    pollMeetingStatus(meetingId);
  }
}

async function pollMeetingStatus(meetingId) {
  const token = localStorage.getItem('access_token');

  const interval = setInterval(async () => {
    try {
      // Check meeting status
      const response = await fetch(`/meeting/${meetingId}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      const meeting = await response.json();
      const status = meeting.status;

      // Update UI based on status
      if (status.startsWith('queued')) {
        document.getElementById('status-message').textContent =
          `In queue... ${status}`;
        updateProgressBar(10); // 10% - queued
      }
      else if (status === 'processing') {
        document.getElementById('status-message').textContent =
          'Transcribing and analyzing...';
        updateProgressBar(50); // 50% - processing
      }
      else if (status === 'completed') {
        document.getElementById('status-message').textContent =
          'Complete!';
        updateProgressBar(100); // 100% - done

        clearInterval(interval);

        // Redirect to meeting page after 1 second
        setTimeout(() => {
          window.location.href = `/meeting/${meetingId}`;
        }, 1000);
      }
      else if (status === 'error') {
        document.getElementById('status-message').textContent =
          'Processing failed. Please try again.';
        updateProgressBar(0);
        clearInterval(interval);
      }

    } catch (error) {
      console.error('Error polling status:', error);
    }
  }, 3000); // Poll every 3 seconds
}

function updateProgressBar(percentage) {
  document.getElementById('progress-bar').style.width = percentage + '%';
}
</script>

<style>
.progress-bar-container {
  width: 100%;
  height: 30px;
  background-color: #f0f0f0;
  border-radius: 15px;
  overflow: hidden;
  margin: 20px 0;
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #4CAF50, #8BC34A);
  transition: width 0.3s ease;
  width: 0%;
}

#status-message {
  font-size: 18px;
  font-weight: bold;
  color: #333;
}

#queue-info {
  font-size: 14px;
  color: #666;
}
</style>
```

### Option 2: WebSocket (Real-time, Advanced)

For real-time updates without polling, you can implement WebSockets:

```python
# Would require flask-socketio
# Out of scope for now, but polling works great for this use case
```

### Option 3: Check Queue Status Before Upload

```javascript
async function showQueueStatus() {
  const token = localStorage.getItem('access_token');

  const response = await fetch('/api/queue/status', {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  const data = await response.json();

  // Show user queue info before they upload
  const queueHTML = `
    <div class="queue-status">
      <h4>Current Queue Status</h4>
      <p>Active jobs: ${data.queue.active_jobs} / ${data.queue.max_concurrent}</p>
      <p>Jobs in queue: ${data.queue.size}</p>
      <p>Available workers: ${data.queue.available_workers}</p>
      ${data.queue.available_workers > 0 ?
        '<span class="badge-green">Your job will start immediately!</span>' :
        `<span class="badge-yellow">Estimated wait: ~${data.queue.size} minutes</span>`
      }
    </div>
  `;

  document.getElementById('queue-info-container').innerHTML = queueHTML;
}

// Call this when user visits upload page
showQueueStatus();
```

## Testing the Queue

### Test with Multiple Uploads

```bash
# Terminal 1: Upload file 1
curl -X POST http://localhost:8080/upload \
  -H "Authorization: Bearer <token>" \
  -F "audio=@meeting1.mp3" \
  -F "title=Meeting 1"

# Terminal 2: Upload file 2 (immediately)
curl -X POST http://localhost:8080/upload \
  -H "Authorization: Bearer <token>" \
  -F "audio=@meeting2.mp3" \
  -F "title=Meeting 2"

# Terminal 3: Upload file 3 (immediately)
curl -X POST http://localhost:8080/upload \
  -H "Authorization: Bearer <token>" \
  -F "audio=@meeting3.mp3" \
  -F "title=Meeting 3"

# Check queue status
curl http://localhost:8080/api/queue/status \
  -H "Authorization: Bearer <token>"

# Response will show:
# - 2 jobs processing (MAX_CONCURRENT_JOBS=2)
# - 1 job queued (waiting for slot)
```

### Monitor Docker Logs

```bash
docker logs -f meeting-web

# You'll see:
# Started 2 audio processing workers (MAX_CONCURRENT_JOBS=2)
# Transcribing audio for meeting 1...
# Transcribing audio for meeting 2...
# [Meeting 3 waits in queue]
# [When meeting 1 completes, meeting 3 starts]
```

### Monitor RAM Usage

```bash
docker stats meeting-web

# With MAX_CONCURRENT_JOBS=2:
# MEM USAGE: ~5-6GB peak (2 jobs × ~2.5GB each + base)
#
# If you set MAX_CONCURRENT_JOBS=4 on 8GB RAM:
# MEM USAGE: ~8GB+ → CRASH! ⚠️
```

## Queue Behavior

### Scenario 1: Free Workers Available
```
Queue: []
Active: [Job A, Job B]     (MAX=2)

→ User uploads Job C
→ Job C starts IMMEDIATELY (no wait)
```

### Scenario 2: All Workers Busy
```
Queue: [Job D, Job E]
Active: [Job A, Job B]     (MAX=2)

→ User uploads Job F
→ Job F goes to queue position 3
→ When Job A completes, Job D starts
→ When Job B completes, Job E starts
→ When Job D completes, Job F starts
```

### Scenario 3: Multiple Users
```
User Alice uploads → Job A (starts processing)
User Bob uploads   → Job B (starts processing)
User Charlie uploads → Job C (queued, position 1)
User Alice uploads → Job D (queued, position 2)

All users see their queue position
All jobs process fairly (FIFO)
```

## Advantages Over Celery

This implementation uses Python's built-in `threading` and `queue` modules instead of Celery:

### Pros:
- ✅ No external dependencies (Redis/RabbitMQ)
- ✅ Simpler deployment
- ✅ Lower resource usage
- ✅ Sufficient for small-medium deployments
- ✅ Easy to understand and debug

### Cons:
- ⚠️ Queue lost on restart (not persistent)
- ⚠️ Can't distribute across multiple servers

For most VPS deployments, this is **perfect**!

## Future Enhancements (Optional)

If you need more advanced features:

1. **Persistent Queue** - Store queue in PostgreSQL
2. **Priority Queue** - VIP users process faster
3. **Celery Integration** - For multi-server setups
4. **Email Notifications** - Alert users when done
5. **WebSocket Updates** - Real-time progress

But for 95% of use cases, **the current system is production-ready!**

## Summary

✅ **Prevents RAM overload** with concurrent job limits
✅ **Fair queuing** for multiple users
✅ **Instant response** to uploads (no blocking)
✅ **Queue visibility** for great UX
✅ **Simple implementation** (no Celery/Redis needed)
✅ **Production-ready** for VPS deployment

Your system can now handle **multiple concurrent users without crashing!** 🎉
