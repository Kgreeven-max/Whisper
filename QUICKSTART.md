# Quick Start Guide

## What is this?

This is a **self-hosted meeting transcriber** similar to Notion's meeting transcriber that runs entirely on your VPS. It:

1. Accepts audio/video uploads (meetings, calls, recordings)
2. Transcribes them using AI (Whisper)
3. Analyzes the content using a local LLM (Ollama)
4. Provides a beautiful web interface to view and search all your meetings

## One-Command Installation

On your VPS, run:

```bash
./deploy.sh
```

This will:
- Install Docker (if needed)
- Set up all services
- Pull the AI model
- Configure auto-start (optional)
- Set up Nginx & SSL (optional)

## What You Get

After deployment, you'll have a web application with:

- **Dashboard**: View all your meetings
- **Upload Page**: Drag & drop audio files
- **Meeting View**: See transcripts with:
  - AI-generated summary
  - Key discussion points
  - Action items with checkboxes
  - Important decisions
  - Full searchable transcript

## How to Use

### 1. Upload a Meeting

1. Go to http://your-server-ip:8080 (or your domain)
2. Click "Upload Meeting"
3. Fill in:
   - Title: "Weekly Team Standup"
   - Attendees: "John, Sarah, Mike"
   - Tags: "standup, weekly"
4. Drag & drop your audio file (MP3, WAV, M4A, etc.)
5. Click "Upload & Process"

### 2. Processing

The system will:
- Transcribe the audio (takes ~30% of audio length)
- Analyze with AI to extract insights
- Generate summary, key points, and action items

You can navigate away and come back later - the dashboard shows processing status.

### 3. View Results

Click on any meeting to see:
- **Summary**: AI-generated overview
- **Key Points**: Main topics discussed
- **Action Items**: To-dos with checkboxes
- **Decisions**: Important decisions made
- **Transcript**: Full text with timestamps

### 4. Search & Export

- Use the search bar to find specific meetings
- Click "Download as Markdown" to export
- Check action items as you complete them

## System Requirements

**Minimum** (2GB RAM):
- Handles 5-10 meetings per day
- Uses smaller AI models
- Processing is slower

**Recommended** (4GB RAM):
- Handles 20-30 meetings per day
- Better AI quality
- Faster processing

**Optimal** (8GB+ RAM):
- Unlimited meetings
- Best AI models
- Very fast processing

## Supported Formats

- **Audio**: MP3, WAV, M4A, FLAC, OGG
- **Video**: MP4, AVI, MOV, MKV (extracts audio)
- **Max Size**: 500MB per file

## Example Use Cases

1. **Team Meetings**: Record standups, planning meetings
2. **Interviews**: Transcribe job interviews, user research
3. **Podcasts**: Convert podcast episodes to text
4. **Lectures**: Transcribe educational content
5. **Legal/Medical**: Record consultations (with consent)

## Costs

Running on VPS:
- **$10-15/month**: Basic VPS (2GB RAM)
- **$20-30/month**: Better performance (4GB RAM)
- **$40-60/month**: Best performance (8GB RAM)

Compare to cloud services charging $0.024/minute = $1.44/hour.
**Break even at ~10-15 hours of transcription per month.**

## Privacy

Everything runs on YOUR server:
- No data sent to third parties
- Audio stays on your VPS
- Transcripts stored locally
- Complete control over your data

## Quick Troubleshooting

**Upload fails?**
```bash
docker-compose logs web
```

**Processing stuck?**
```bash
docker-compose restart
```

**AI model not working?**
```bash
docker exec meeting-ollama ollama pull llama2
```

**Check everything is running:**
```bash
docker-compose ps
```

All services should show "Up" status.

## Daily Workflow

1. **Record your meeting** (on your phone, Zoom, Teams, etc.)
2. **Export the audio file**
3. **Upload to the web interface**
4. **Wait 5-15 minutes** (depending on length)
5. **Review the AI-generated insights**
6. **Share the markdown export** with your team

## Advanced Features

- **Search**: Find meetings by keywords across all transcripts
- **Tags**: Organize meetings by project, team, or topic
- **Batch Processing**: Upload multiple meetings at once
- **Markdown Export**: Share formatted notes
- **Action Tracking**: Check off action items as you complete them

## Getting Help

1. Check the logs: `docker-compose logs`
2. Restart services: `docker-compose restart`
3. View full documentation: Read README.md
4. Check service status: `docker-compose ps`

## Next Steps After Installation

1. **Test with a short recording** (1-2 minutes) to verify everything works
2. **Adjust AI model** if needed (see README.md for options)
3. **Set up SSL** for secure access (optional but recommended)
4. **Configure backups** for your meetings database
5. **Add authentication** if sharing with others (see README.md)

---

**Ready to deploy?** Run `./deploy.sh` on your VPS!

**Questions?** Check the full README.md for detailed documentation.
