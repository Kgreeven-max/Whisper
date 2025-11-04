# Meeting Transcriber - Notion-Style VPS Solution

A complete meeting transcription and analysis system that runs on your VPS, similar to Notion's meeting transcriber. This system uses Whisper for transcription and Ollama (local LLM) for intelligent analysis.

## Features

- **Audio Upload**: Support for multiple audio/video formats (MP3, WAV, M4A, MP4, FLAC, OGG)
- **Automatic Transcription**: Uses OpenAI Whisper for accurate speech-to-text
- **AI Analysis**: Extracts summaries, key points, action items, and decisions using local LLM
- **Beautiful UI**: Clean, modern interface inspired by Notion
- **Search**: Full-text search across all meeting transcripts
- **Export**: Download meetings as formatted Markdown files
- **Persistent Storage**: SQLite database and file storage

## Architecture

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌──────────────┐
│  Flask Web  │────▶│   Whisper    │
│     App     │     │  (Port 9000) │
│ (Port 8080) │     └──────────────┘
└──────┬──────┘
       │            ┌──────────────┐
       └───────────▶│    Ollama    │
                    │ (Port 11434) │
                    └──────────────┘
```

## Quick Start

### Prerequisites

- Ubuntu/Debian VPS with at least 8GB RAM (4GB minimum)
- Docker and Docker Compose installed
- At least 20GB free disk space

### Installation

1. **Clone the repository:**

```bash
cd /opt
git clone https://github.com/Kgreeven-max/Whisper.git meeting-transcriber
cd meeting-transcriber
git checkout claude/notion-meeting-transcriber-vps-011CUnFKEU8KLtfhEMdsKMdG
```

2. **⚠️ REQUIRED: Create .env file with secure passwords:**

```bash
# Copy example file
cp .env.example .env

# Generate secure password
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate secret key
python3 -c "import secrets; print(secrets.token_hex(32))"

# Edit .env and replace POSTGRES_PASSWORD and SECRET_KEY with generated values
nano .env
```

**CRITICAL:** Replace `REPLACE_WITH_SECURE_PASSWORD` and `REPLACE_WITH_SECURE_SECRET_KEY` with the generated values!

3. **Deploy (automated):**

```bash
./deploy.sh
```

The deployment script will:
- Check your .env file (will error if not configured)
- Install Docker if needed
- Start all services
- Pull AI model
- Verify everything is running

**OR Manual deployment:**

```bash
# Start services
docker-compose up -d

# Pull LLM model (recommended for 8GB RAM)
docker exec meeting-ollama ollama pull phi
```

Other models:
- `phi` (2.7B parameters, very fast) ← **Recommended for 8GB RAM**
- `mistral` (7B parameters, balanced)
- `llama2` (7B parameters, good quality)

6. **Access the application:**

Open your browser and navigate to:
```
http://your-vps-ip:8080
```

## Configuration

### Change Whisper Model

Edit `docker-compose.yml` and modify the Whisper environment:

```yaml
environment:
  - ASR_MODEL=base  # Options: tiny, base, small, medium, large
```

Models comparison:
- `tiny`: Fastest, least accurate (~1GB RAM)
- `base`: Good balance (~1GB RAM)
- `small`: Better accuracy (~2GB RAM)
- `medium`: High accuracy (~5GB RAM)
- `large`: Best accuracy (~10GB RAM)

### Change LLM Model

The default is `llama2`. To use a different model:

1. Edit `app.py` line ~150:
```python
'model': 'mistral',  # Change from 'llama2'
```

2. Pull the new model:
```bash
docker exec -it meeting-ollama ollama pull mistral
```

## Production Deployment

### 1. Set up Nginx Reverse Proxy

Create `/etc/nginx/sites-available/meeting-transcriber`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 500M;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
    }
}
```

Enable the site:
```bash
ln -s /etc/nginx/sites-available/meeting-transcriber /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

### 2. Set up SSL with Let's Encrypt

```bash
apt install certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

### 3. Set up Systemd Service (Auto-start on boot)

Create `/etc/systemd/system/meeting-transcriber.service`:

```ini
[Unit]
Description=Meeting Transcriber Docker Compose
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/meeting-transcriber
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Enable the service:
```bash
systemctl daemon-reload
systemctl enable meeting-transcriber
systemctl start meeting-transcriber
```

## Usage

### Uploading a Meeting

1. Click "Upload Meeting" in the navigation
2. Fill in the meeting details:
   - **Title**: Name of the meeting
   - **Attendees**: Comma-separated list of participants
   - **Tags**: Keywords for categorization
3. Drag & drop or select your audio file
4. Click "Upload & Process"

Processing time depends on:
- Audio length (roughly 1:2 ratio - 30min audio = ~15min processing)
- Selected Whisper model
- VPS performance

### Viewing Meetings

- **Dashboard**: Shows all meetings with search functionality
- **Meeting View**: Displays full analysis with:
  - Summary
  - Key discussion points
  - Action items (with checkboxes)
  - Decisions
  - Full transcript

### Searching

Use the search bar on the dashboard to find meetings by:
- Title
- Transcript content
- Summary text
- Tags

### Exporting

Click "Download as Markdown" on any meeting to get a formatted `.md` file.

## Troubleshooting

### Services won't start

Check logs:
```bash
docker-compose logs
```

Check individual services:
```bash
docker-compose ps
docker-compose logs whisper
docker-compose logs ollama
docker-compose logs web
```

### Whisper transcription fails

1. Check Whisper service is running:
```bash
curl http://localhost:9000/
```

2. Check logs:
```bash
docker-compose logs whisper
```

3. Try restarting:
```bash
docker-compose restart whisper
```

### Ollama analysis fails

1. Verify model is installed:
```bash
docker exec -it meeting-ollama ollama list
```

2. Pull the model if missing:
```bash
docker exec -it meeting-ollama ollama pull llama2
```

3. Check Ollama is responding:
```bash
curl http://localhost:11434/
```

### Upload fails

1. Check file size (max 500MB)
2. Check disk space:
```bash
df -h
```

3. Verify upload directory permissions:
```bash
ls -la uploads/
```

### Processing stuck

1. Check if services are healthy:
```bash
docker-compose ps
```

2. Look for errors in meeting table:
```bash
sqlite3 data/meetings.db "SELECT id, title, status FROM meetings WHERE status='error';"
```

## Maintenance

### Backup Database

```bash
cp data/meetings.db data/meetings.db.backup-$(date +%Y%m%d)
```

### Clean Old Audio Files

```bash
# List files older than 30 days
find uploads/ -name "*.mp3" -mtime +30

# Delete files older than 30 days
find uploads/ -name "*.mp3" -mtime +30 -delete
```

### Update Services

```bash
docker-compose pull
docker-compose up -d
```

### View Resource Usage

```bash
docker stats
```

## Performance Optimization

### For Limited Resources (2GB RAM VPS)

1. Use smaller models:
```yaml
# Whisper: tiny or base
# Ollama: phi or tinyllama
```

2. Reduce workers in `Dockerfile`:
```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "600", "app:app"]
```

### For Better Performance (8GB+ RAM VPS)

1. Use larger models:
```yaml
# Whisper: medium or large
# Ollama: mistral or mixtral
```

2. Increase workers in `Dockerfile`:
```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "8", "--timeout", "600", "app:app"]
```

## Security Considerations

1. **Add Authentication**: The current version has no authentication. Consider adding:
   - Basic HTTP authentication via Nginx
   - Flask-Login for user management
   - OAuth integration

2. **Firewall**: Restrict access to ports:
```bash
ufw allow 22    # SSH
ufw allow 80    # HTTP
ufw allow 443   # HTTPS
ufw enable
```

3. **File Validation**: The app validates file types, but consider additional scanning for production use

4. **HTTPS**: Always use SSL in production (see Let's Encrypt setup above)

## Costs

Running on a VPS:
- **Small VPS** (2GB RAM): $10-15/month - Handles ~5-10 meetings/day
- **Medium VPS** (4GB RAM): $20-30/month - Handles ~20-30 meetings/day
- **Large VPS** (8GB RAM): $40-60/month - Handles unlimited meetings

Compare to cloud services:
- Google Meet transcription: ~$0.024/minute
- AWS Transcribe: ~$0.024/minute
- Azure Speech: ~$1/hour

Break-even at ~100 hours/month of transcription.

## License

MIT License - Feel free to modify and use for your needs.

## Support

For issues, please check:
1. Docker logs: `docker-compose logs`
2. Application logs: `docker-compose logs web`
3. Service health: `docker-compose ps`

## Credits

- OpenAI Whisper for transcription
- Ollama for local LLM inference
- Flask for web framework
