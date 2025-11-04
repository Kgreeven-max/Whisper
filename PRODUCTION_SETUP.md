# Production Deployment Guide

This guide will help you deploy the Meeting Transcriber system in a production environment with proper security and configuration.

## 🔒 Security First

### Step 1: Create Environment File

Copy the example and customize it:

```bash
cp .env.example .env
nano .env  # or vim, code, etc.
```

### Step 2: Generate Secure Passwords

**Generate strong PostgreSQL password:**

```bash
# On Linux/Mac
openssl rand -base64 32

# Or use this Python one-liner
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Generate SECRET_KEY for Flask:**

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Step 3: Update .env File

Edit your `.env` file:

```bash
# PostgreSQL Database Configuration
POSTGRES_DB=meetings
POSTGRES_USER=meeting_user
POSTGRES_PASSWORD=YOUR_GENERATED_PASSWORD_HERE

# Flask Configuration
FLASK_ENV=production
SECRET_KEY=YOUR_GENERATED_SECRET_KEY_HERE

# Whisper Model (tiny, base, small, medium, large)
WHISPER_MODEL=small

# Ollama Model (phi, mistral, llama2)
OLLAMA_MODEL=phi
```

**IMPORTANT:**
- Never commit `.env` to git (it's in `.gitignore`)
- Use different passwords for different environments
- Store passwords securely (password manager, vault, etc.)

---

## 📦 Deployment on VPS

### Quick Deployment

```bash
# 1. Clone repository
git clone https://github.com/Kgreeven-max/Whisper.git meeting-transcriber
cd meeting-transcriber
git checkout claude/notion-meeting-transcriber-vps-011CUnFKEU8KLtfhEMdsKMdG

# 2. Create .env file
cp .env.example .env

# 3. Edit .env with secure passwords
nano .env

# 4. Deploy
docker-compose up -d

# 5. Wait for services to start (2-3 minutes)
docker-compose ps

# 6. Pull AI model
docker exec meeting-ollama ollama pull phi

# 7. Test
curl http://localhost:8080/health
```

---

## 🗄️ PostgreSQL Configuration

### Database Details

- **Image:** PostgreSQL 16 Alpine (lightweight)
- **Database:** `meetings`
- **Default User:** `meeting_user`
- **Port:** 5432 (internal only, not exposed)
- **Volume:** `postgres-data` (persisted)
- **Memory Limit:** 512MB

### Access Database

```bash
# Enter PostgreSQL container
docker exec -it meeting-postgres psql -U meeting_user -d meetings

# Common queries:
\dt                    # List tables
\d meetings            # Describe meetings table
SELECT * FROM meetings LIMIT 5;
\q                     # Exit
```

### Backup Database

```bash
# Backup
docker exec meeting-postgres pg_dump -U meeting_user meetings > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20250101.sql | docker exec -i meeting-postgres psql -U meeting_user meetings
```

### Automated Backups

Create a backup script `backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/opt/meeting-transcriber/backups"
mkdir -p $BACKUP_DIR

# Backup database
docker exec meeting-postgres pg_dump -U meeting_user meetings | \
    gzip > $BACKUP_DIR/meetings_$(date +%Y%m%d_%H%M%S).sql.gz

# Keep only last 30 days
find $BACKUP_DIR -name "meetings_*.sql.gz" -mtime +30 -delete

echo "Backup completed: $(date)"
```

Add to crontab:

```bash
# Daily backup at 2 AM
crontab -e

# Add this line:
0 2 * * * /opt/meeting-transcriber/backup.sh >> /var/log/meeting-backup.log 2>&1
```

---

## 🔐 Security Hardening

### 1. Firewall Configuration

```bash
# UFW (Ubuntu/Debian)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# IMPORTANT: Do NOT expose ports 5432 (postgres), 9000 (whisper), 11434 (ollama)
# These should only be accessible internally via Docker network
```

### 2. SSL/TLS with Let's Encrypt

**Install Certbot:**

```bash
sudo apt update
sudo apt install certbot python3-certbot-nginx
```

**Setup Nginx** (if not already):

```bash
sudo cp nginx.conf /etc/nginx/sites-available/meeting-transcriber

# Edit and replace 'your-domain.com' with your actual domain
sudo nano /etc/nginx/sites-available/meeting-transcriber

# Enable site
sudo ln -s /etc/nginx/sites-available/meeting-transcriber /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload
sudo systemctl reload nginx
```

**Get SSL Certificate:**

```bash
sudo certbot --nginx -d your-domain.com

# Auto-renewal (certbot usually sets this up automatically)
sudo certbot renew --dry-run
```

### 3. Change Default Ports (Optional)

Edit `docker-compose.yml`:

```yaml
web:
  ports:
    - "8081:8080"  # Change external port to 8081
```

Then update Nginx proxy_pass accordingly.

### 4. Enable Docker Security

```bash
# Run Docker in rootless mode (advanced)
# Or use AppArmor/SELinux profiles
```

### 5. Regular Updates

```bash
# Update Docker images
docker-compose pull

# Restart with new images
docker-compose up -d

# Remove old images
docker image prune -a
```

---

## 📊 Monitoring

### Resource Monitoring

```bash
# Real-time stats
docker stats

# Check logs
docker-compose logs -f --tail=100

# Check specific service
docker-compose logs web
docker-compose logs whisper
docker-compose logs postgres
```

### Health Checks

```bash
# Web app
curl http://localhost:8080/health

# Whisper
curl http://localhost:9000/

# Ollama
curl http://localhost:11434/

# PostgreSQL
docker exec meeting-postgres pg_isready -U meeting_user
```

### Setup Monitoring (Optional)

**Prometheus + Grafana:**

Add to `docker-compose.yml`:

```yaml
  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    volumes:
      - grafana-data:/var/lib/grafana
```

---

## 🚀 Performance Tuning

### For 8GB RAM VPS

**Already optimized in `docker-compose.yml`:**
- Whisper: 3GB limit
- Ollama: 4GB limit
- Web: 1GB limit
- PostgreSQL: 512MB limit

### PostgreSQL Performance

Edit PostgreSQL settings (optional):

```bash
# Create custom postgres config
cat > postgres.conf << 'EOF'
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
max_connections = 100
EOF

# Update docker-compose.yml
services:
  postgres:
    command: postgres -c config_file=/etc/postgresql/postgresql.conf
    volumes:
      - ./postgres.conf:/etc/postgresql/postgresql.conf
```

### Whisper Optimization

```bash
# Use smaller model for faster processing
WHISPER_MODEL=base

# Or use larger model for better quality (if you have RAM)
WHISPER_MODEL=medium
```

### Ollama Optimization

```bash
# Fast model (recommended for 8GB)
docker exec meeting-ollama ollama pull phi

# Better quality (uses more RAM)
docker exec meeting-ollama ollama pull mistral
```

---

## 🔄 Scaling

### Vertical Scaling (More Resources)

If you upgrade your VPS:

```yaml
# docker-compose.yml - increase limits
whisper:
  environment:
    - ASR_MODEL=medium  # Use better model
  deploy:
    resources:
      limits:
        memory: 6G  # More RAM

ollama:
  deploy:
    resources:
      limits:
        memory: 8G
```

Then pull better model:

```bash
docker exec meeting-ollama ollama pull mistral
```

### Horizontal Scaling (Multiple Instances)

For high traffic:

1. **Load Balancer** (Nginx):
   - Multiple web containers
   - Load balance between them

2. **Separate Services:**
   - Run Whisper on dedicated server
   - Run Ollama on dedicated server
   - Update URLs in docker-compose

3. **Database Replication:**
   - PostgreSQL primary/replica setup
   - Read replicas for search

---

## 📈 Maintenance Schedule

### Daily
- ✅ Check `docker stats` for resource usage
- ✅ Monitor disk space: `df -h`
- ✅ Check logs for errors: `docker-compose logs --tail=50`

### Weekly
- ✅ Review completed meetings count
- ✅ Clean old uploads: `find uploads/ -mtime +30 -delete`
- ✅ Check backup sizes

### Monthly
- ✅ Update Docker images: `docker-compose pull && docker-compose up -d`
- ✅ Review and rotate logs
- ✅ Test backup restoration
- ✅ Review security updates: `apt update && apt upgrade`

### Quarterly
- ✅ Review database size and optimize
- ✅ Update SSL certificates (auto with certbot)
- ✅ Review and update passwords
- ✅ Performance audit

---

## 🐛 Troubleshooting Production Issues

### Out of Memory

```bash
# Check memory usage
free -h

# Check which service is using memory
docker stats --no-stream

# Solutions:
# 1. Use smaller models (phi, tiny)
# 2. Add swap space
# 3. Upgrade RAM
# 4. Process meetings one at a time
```

### Database Connection Errors

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check logs
docker-compose logs postgres

# Test connection
docker exec meeting-postgres psql -U meeting_user -d meetings -c "SELECT 1"

# Restart if needed
docker-compose restart postgres
```

### Slow Processing

```bash
# Check CPU usage
top

# Check if models are loaded
docker-compose logs whisper
docker-compose logs ollama

# Solutions:
# 1. Use faster models (tiny, base, phi)
# 2. Limit concurrent uploads
# 3. Upgrade CPU
```

### Disk Full

```bash
# Check disk usage
df -h

# Find large files
du -sh uploads/* | sort -h

# Clean up:
# - Old audio files
find uploads/ -name "*.wav" -mtime +30 -delete

# - Old backups
find backups/ -mtime +90 -delete

# - Docker cleanup
docker system prune -a
```

---

## 📝 Production Checklist

Before going live:

- [ ] Strong passwords set in `.env`
- [ ] `.env` file permissions: `chmod 600 .env`
- [ ] Firewall configured (ports 80, 443, 22 only)
- [ ] SSL certificate installed
- [ ] Backup script configured and tested
- [ ] Monitoring set up
- [ ] Health checks passing
- [ ] Tested with sample meeting
- [ ] Documented for team
- [ ] Emergency contacts list
- [ ] Rollback plan ready

---

## 🆘 Emergency Procedures

### Complete System Failure

```bash
# Stop everything
docker-compose down

# Check logs
docker-compose logs > emergency_$(date +%Y%m%d).log

# Start fresh
docker-compose up -d

# Restore database if needed
cat backup.sql | docker exec -i meeting-postgres psql -U meeting_user meetings
```

### Data Corruption

```bash
# Stop services
docker-compose stop

# Backup current state
docker exec meeting-postgres pg_dump -U meeting_user meetings > corrupted_$(date +%Y%m%d).sql

# Restore from last good backup
cat backup_good.sql | docker exec -i meeting-postgres psql -U meeting_user meetings

# Restart
docker-compose start
```

### Security Breach

```bash
# 1. Immediately stop services
docker-compose down

# 2. Change all passwords
# Edit .env with new passwords

# 3. Review logs
docker-compose logs > security_audit_$(date +%Y%m%d).log

# 4. Check for unauthorized access
docker exec meeting-postgres psql -U meeting_user -d meetings -c "SELECT * FROM meetings ORDER BY date DESC LIMIT 100"

# 5. Restart with new passwords
docker-compose up -d
```

---

## 📞 Support

**Logs to collect when asking for help:**

```bash
# System info
uname -a
docker --version
docker-compose --version
free -h
df -h

# Service status
docker-compose ps

# Recent logs
docker-compose logs --tail=200 > logs.txt

# Database status
docker exec meeting-postgres psql -U meeting_user -d meetings -c "\d meetings"
```

---

## ✅ You're Production Ready!

Your system is now configured for production use with:
- ✅ Secure PostgreSQL database
- ✅ Environment-based configuration
- ✅ Resource limits for stability
- ✅ Health checks and monitoring
- ✅ Backup procedures
- ✅ Security hardening

**Start transcribing meetings securely!** 🎉
