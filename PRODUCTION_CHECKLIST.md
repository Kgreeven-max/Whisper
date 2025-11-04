# Production Deployment Checklist

Before deploying to production, complete this checklist to ensure security and reliability.

## 🔒 Security Configuration

### 1. Environment Variables
- [ ] Created `.env` file from `.env.example`
- [ ] Generated strong POSTGRES_PASSWORD (32+ characters)
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(32))"
  ```
- [ ] Generated strong SECRET_KEY (64+ characters)
  ```bash
  python3 -c "import secrets; print(secrets.token_hex(32))"
  ```
- [ ] Replaced ALL placeholder values in `.env`
- [ ] Set `.env` file permissions to 600
  ```bash
  chmod 600 .env
  ```
- [ ] Verified `.env` is in `.gitignore` (it is by default)

### 2. Database Security
- [ ] Strong PostgreSQL password set
- [ ] Database not exposed externally (only accessible via Docker network)
- [ ] Backup strategy configured
- [ ] Backup script tested

### 3. Network Security
- [ ] Firewall configured to allow only necessary ports:
  - 22 (SSH)
  - 80 (HTTP)
  - 443 (HTTPS)
- [ ] Ports 5432, 9000, 11434 NOT exposed externally
- [ ] SSL/TLS certificate installed (if using domain)
- [ ] HTTPS redirect configured (if using domain)

### 4. Access Control
- [ ] SSH key-based authentication enabled
- [ ] Password authentication disabled for SSH
- [ ] Root login disabled
- [ ] Sudo user with limited privileges created
- [ ] Consider adding HTTP basic auth or OAuth (see PRODUCTION_SETUP.md)

## 🚀 Deployment Steps

### Pre-Deployment
- [ ] VPS meets minimum requirements (8GB RAM recommended)
- [ ] Docker and Docker Compose installed
- [ ] Git installed
- [ ] Required ports available

### Deployment
- [ ] Repository cloned
- [ ] Correct branch checked out
- [ ] `.env` file created and configured
- [ ] Run `./deploy.sh` successfully
- [ ] All containers started without errors
- [ ] Health checks passing

### Post-Deployment
- [ ] Ollama model pulled
  ```bash
  docker exec meeting-ollama ollama pull phi
  ```
- [ ] Test upload with sample audio file
- [ ] Verify transcription works
- [ ] Verify AI analysis works
- [ ] Check logs for errors
  ```bash
  docker-compose logs
  ```

## 🔍 Verification

### Container Status
```bash
docker-compose ps
```
All services should show "Up" and "healthy"

### Service Health Checks
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

### Database Connection
```bash
docker exec meeting-postgres psql -U meeting_user -d meetings -c "SELECT 1"
```

### Test Upload
1. Navigate to http://your-vps-ip:8080
2. Upload a short test audio file (1-2 minutes)
3. Verify processing completes
4. Check transcript quality
5. Verify AI analysis appears

## 📊 Monitoring Setup

### Resource Monitoring
- [ ] Set up monitoring for:
  - CPU usage
  - Memory usage
  - Disk space
  - Container status
- [ ] Configure alerts for:
  - High memory usage (>90%)
  - High disk usage (>85%)
  - Container restarts
  - Service failures

### Log Management
- [ ] Log rotation configured
- [ ] Log aggregation set up (optional)
- [ ] Error alerting configured
- [ ] Regular log review scheduled

### Backup Verification
- [ ] Automated backups running
- [ ] Backup restoration tested
- [ ] Backup storage secured
- [ ] Backup retention policy defined

## 🌐 Domain & SSL (If Applicable)

### Domain Configuration
- [ ] Domain DNS pointing to VPS IP
- [ ] Nginx installed and configured
- [ ] Nginx config syntax validated
  ```bash
  sudo nginx -t
  ```
- [ ] Nginx reloaded successfully

### SSL Certificate
- [ ] Certbot installed
- [ ] SSL certificate obtained
  ```bash
  sudo certbot --nginx -d your-domain.com
  ```
- [ ] Auto-renewal tested
  ```bash
  sudo certbot renew --dry-run
  ```
- [ ] HTTPS working
- [ ] HTTP redirects to HTTPS

## 📝 Documentation

- [ ] System architecture documented
- [ ] Access credentials stored securely (password manager)
- [ ] Recovery procedures documented
- [ ] Team members trained
- [ ] Emergency contact list created
- [ ] Runbook created for common operations

## 🔄 Maintenance Plan

### Daily
- [ ] Check container status
- [ ] Review error logs
- [ ] Monitor disk space

### Weekly
- [ ] Verify backups
- [ ] Check resource usage trends
- [ ] Review meeting transcription quality
- [ ] Clean old audio files (optional)

### Monthly
- [ ] Update Docker images
  ```bash
  docker-compose pull
  docker-compose up -d
  ```
- [ ] Review and rotate logs
- [ ] Test backup restoration
- [ ] Update dependencies
- [ ] Security audit

### Quarterly
- [ ] Review and update passwords
- [ ] Audit access logs
- [ ] Performance review
- [ ] Capacity planning
- [ ] Update documentation

## ⚠️ Common Issues Checklist

Before going live, verify these common issues are addressed:

- [ ] `.env` file created (will fail without it)
- [ ] Strong passwords set (not placeholders)
- [ ] Firewall allows required ports
- [ ] Docker has sufficient resources
- [ ] Disk space sufficient (20GB+ recommended)
- [ ] Ollama model pulled
- [ ] All services healthy
- [ ] No port conflicts
- [ ] SELinux/AppArmor configured (if applicable)

## 🆘 Emergency Procedures

### If system fails:
1. Check container status: `docker-compose ps`
2. Check logs: `docker-compose logs --tail=100`
3. Restart services: `docker-compose restart`
4. If database corrupted: restore from backup
5. Contact team/support

### If security breach suspected:
1. Immediately stop services: `docker-compose down`
2. Change all passwords
3. Review logs for unauthorized access
4. Restore from known-good backup
5. Audit all data access
6. Report incident

## ✅ Sign-Off

Before marking production-ready, ensure:

- [ ] All security items checked
- [ ] All deployment steps completed
- [ ] All verification tests passed
- [ ] Monitoring configured
- [ ] Backup tested
- [ ] Team trained
- [ ] Documentation complete

**Production deployment signed off by:** _______________

**Date:** _______________

**Reviewed by:** _______________

---

## 🎉 Ready for Production!

Once all items are checked, your Meeting Transcriber is production-ready and secure!

**Remember:**
- Never commit `.env` file
- Regular backups are critical
- Monitor resource usage
- Keep Docker images updated
- Review logs regularly

**Support:** See PRODUCTION_SETUP.md for detailed procedures
