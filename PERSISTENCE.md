# Data Persistence & Crash Recovery

## Overview

This system is designed to **survive crashes, restarts, and VPS reboots** without losing data or requiring reconfiguration.

## What Persists Across Restarts

### 1. **Docker Volumes** (All Data Persists)

```yaml
volumes:
  whisper-cache:     # Whisper AI models (~1GB)
  ollama-data:       # Ollama LLM models (~2-4GB)
  postgres-data:     # All meeting records & transcripts
  uploads-data:      # All uploaded audio files
```

**Location on Host:** `/var/lib/docker/volumes/`

These volumes persist even if containers are removed (`docker-compose down`). Only `docker-compose down -v` removes them.

### 2. **Automatic Container Restart**

All services have `restart: unless-stopped`:
- Containers auto-restart after crashes
- Containers auto-start after VPS reboot
- Containers stay stopped only if you explicitly stop them

### 3. **Database Auto-Initialization**

The Flask app automatically:
- Creates the database schema on first run
- Retries connection 5 times if PostgreSQL isn't ready yet
- Works with both Gunicorn (production) and Flask dev server

## After VPS Restart - What Happens?

1. **Docker daemon starts automatically** (if installed via setup.sh)
2. **All 4 containers restart automatically**:
   - PostgreSQL loads data from `postgres-data` volume
   - Whisper loads cached models from `whisper-cache` volume
   - Ollama loads models from `ollama-data` volume
   - Flask web app connects to PostgreSQL (with retries)
3. **All previous data is available**:
   - Meeting transcripts
   - Audio files
   - Analysis results
   - User uploads

## Testing Crash Recovery

### Simulate VPS Restart:
```bash
docker-compose restart
```

### Simulate Hard Crash:
```bash
docker-compose down
docker-compose up -d
```

### Verify Data Persists:
```bash
# Check volumes still exist
docker volume ls | grep meeting

# Check database has data
docker exec meeting-postgres psql -U meeting_user -d meetings -c "SELECT COUNT(*) FROM meetings;"

# Check uploaded files
docker exec meeting-web ls -lh /app/uploads/
```

## What Does NOT Persist

- **.env file**: Always stays on host filesystem (never in containers)
- **Docker images**: Persist on host, no need to re-pull
- **Container logs**: Can be lost on crash (use log aggregation if needed)

## Backup Strategy (Recommended)

### Backup Everything:
```bash
# Backup all Docker volumes
docker run --rm \
  -v meeting-postgres-data:/data/postgres \
  -v meeting-uploads-data:/data/uploads \
  -v meeting-ollama-data:/data/ollama \
  -v meeting-whisper-cache:/data/whisper \
  -v $(pwd)/backup:/backup \
  alpine tar czf /backup/meeting-backup-$(date +%Y%m%d).tar.gz /data
```

### Restore from Backup:
```bash
# Stop containers first
docker-compose down

# Extract backup
tar xzf backup/meeting-backup-YYYYMMDD.tar.gz -C /var/lib/docker/volumes/

# Restart
docker-compose up -d
```

## Monitoring After Restart

Check service health:
```bash
# All services should show "Up" and "healthy"
docker-compose ps

# View logs for any issues
docker-compose logs -f --tail=50
```

## Common Issues

### Issue: "Database connection failed"
**Solution:** PostgreSQL takes 5-10 seconds to start. Flask retries automatically.

### Issue: "Port 8080 already in use"
**Solution:** Check for zombie processes: `sudo lsof -i :8080`

### Issue: "Out of disk space"
**Solution:** Prune old Docker data: `docker system prune -a --volumes`

## Volume Management

### View volume disk usage:
```bash
docker system df -v
```

### Inspect a specific volume:
```bash
docker volume inspect meeting_postgres-data
```

### Backup single volume:
```bash
docker run --rm \
  -v meeting_postgres-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/postgres-backup.tar.gz /data
```

## Production Checklist

- [x] All services have `restart: unless-stopped`
- [x] All data stored in named Docker volumes
- [x] Database initialization has retry logic
- [x] Health checks configured for all services
- [x] Resource limits prevent OOM crashes
- [x] PostgreSQL data persists across restarts
- [x] Uploaded files persist across restarts
- [x] AI models cached (no re-download needed)

## Result

**Your VPS can crash, restart, or reboot at any time. When it comes back up, everything will work exactly as before.**
