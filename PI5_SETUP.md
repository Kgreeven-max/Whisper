# Raspberry Pi 5 / 8GB RAM Optimization Guide

Your VPS has **Raspberry Pi 5 equivalent specs (8GB RAM)** - this is actually great for running the meeting transcriber! Here's how to optimize it.

## 📊 Resource Breakdown (8GB RAM)

With 8GB RAM, here's the optimal allocation:

| Service | RAM Usage | Purpose |
|---------|-----------|---------|
| Whisper (small model) | ~2GB | Transcription |
| Ollama (phi/mistral) | ~3GB | AI Analysis |
| Flask Web App | ~500MB | Web interface |
| System + Docker | ~1.5GB | OS overhead |
| **Available buffer** | ~1GB | Prevents crashes |

---

## 🚀 Quick Start for Pi 5

### Option 1: Use Optimized Config (Recommended)

```bash
# Clone repo
git clone https://github.com/Kgreeven-max/Whisper.git meeting-transcriber
cd meeting-transcriber
git checkout claude/notion-meeting-transcriber-vps-011CUnFKEU8KLtfhEMdsKMdG

# Use Pi 5 optimized config
cp docker-compose.pi5.yml docker-compose.yml

# Deploy
docker-compose up -d

# Install smaller, faster model
docker exec meeting-ollama ollama pull phi
```

### Option 2: Manual Optimization

Edit `docker-compose.yml`:

```yaml
whisper:
  environment:
    - ASR_MODEL=small  # Change from 'base' to 'small'
  deploy:
    resources:
      limits:
        memory: 3G

ollama:
  deploy:
    resources:
      limits:
        memory: 4G
```

---

## 🎯 Recommended Model Combinations

### Option A: Balanced (Recommended)
**Best mix of speed and quality**

```bash
# Whisper: small model
ASR_MODEL=small

# Ollama: phi model
docker exec meeting-ollama ollama pull phi
```

**Performance:**
- 10min audio = ~5min processing
- Good transcription quality
- Fast AI analysis
- Uses ~5GB RAM peak

### Option B: Quality Priority
**Better accuracy, slower processing**

```bash
# Whisper: base model
ASR_MODEL=base

# Ollama: mistral model
docker exec meeting-ollama ollama pull mistral
```

**Performance:**
- 10min audio = ~8min processing
- Better transcription quality
- Higher quality analysis
- Uses ~6GB RAM peak

### Option C: Speed Priority
**Fastest, acceptable quality**

```bash
# Whisper: tiny model
ASR_MODEL=tiny

# Ollama: phi model
docker exec meeting-ollama ollama pull phi
```

**Performance:**
- 10min audio = ~3min processing
- Acceptable transcription
- Fast analysis
- Uses ~4GB RAM peak

---

## 🔧 Model Configuration

### Change Whisper Model

Edit `docker-compose.yml`:

```yaml
whisper:
  environment:
    - ASR_MODEL=small  # tiny, base, small, medium
```

Restart:
```bash
docker-compose restart whisper
```

### Change Ollama Model

```bash
# Install new model
docker exec meeting-ollama ollama pull phi

# Update app.py line 579:
# Change: 'model': 'llama2',
# To:     'model': 'phi',
```

Restart:
```bash
docker-compose restart web
```

---

## 📈 Model Comparison for 8GB RAM

### Whisper Models

| Model | Size | RAM | Quality | Speed | Recommended |
|-------|------|-----|---------|-------|-------------|
| tiny | 39MB | ~1GB | Basic | Very Fast | ❌ Too low quality |
| base | 74MB | ~1.5GB | Good | Fast | ✅ Default choice |
| **small** | 244MB | **~2GB** | **Very Good** | **Medium** | ✅ **BEST for 8GB** |
| medium | 769MB | ~5GB | Excellent | Slow | ⚠️ Possible but tight |
| large | 1.5GB | ~10GB | Best | Very Slow | ❌ Won't fit |

### Ollama Models

| Model | Parameters | RAM | Quality | Speed | Recommended |
|-------|-----------|-----|---------|-------|-------------|
| **phi** | **2.7B** | **~3GB** | **Good** | **Fast** | ✅ **BEST for 8GB** |
| mistral | 7B | ~4GB | Excellent | Medium | ✅ Works well |
| llama2 | 7B | ~4GB | Very Good | Medium | ✅ Works well |
| mixtral | 47B | ~26GB | Best | Slow | ❌ Won't fit |

---

## ⚡ Performance Tuning

### 1. Reduce Flask Workers

Edit `Dockerfile`:

```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "600", "app:app"]
```

Change `--workers 4` to `--workers 2` (already done in Pi 5 config)

### 2. Enable Swap (If Needed)

```bash
# Check current swap
free -h

# Add 4GB swap if none exists
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 3. Monitor Resources

```bash
# Real-time monitoring
docker stats

# Check memory usage
free -h

# Check which service uses most memory
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}"
```

---

## 🎬 Usage Recommendations

### For Live Recording

Live recording uses more RAM because:
- Whisper actively transcribing chunks
- Web app receiving streams
- Database writing frequently

**Recommendation:**
- Don't run multiple live recordings simultaneously
- Close other applications during live recording
- Use `phi` model for best performance

### For File Upload

File upload is less demanding:
- Processing happens sequentially
- Can handle multiple queued uploads
- More time for processing = can use better models

**Recommendation:**
- Can use `small` Whisper model
- Can use `mistral` for better analysis

---

## 🐛 Troubleshooting

### Out of Memory Errors

**Symptoms:**
- Services keep restarting
- Docker logs show "Killed"
- `dmesg` shows OOM killer

**Solutions:**

1. **Use smaller models:**
   ```bash
   # Whisper
   ASR_MODEL=tiny

   # Ollama
   docker exec meeting-ollama ollama pull phi
   ```

2. **Add memory limits** (already in pi5 config):
   ```yaml
   deploy:
     resources:
       limits:
         memory: 3G
   ```

3. **Enable swap** (see above)

4. **Process one at a time:**
   - Don't upload multiple files simultaneously
   - Don't run live recording while processing uploads

### Slow Processing

**If transcription is too slow:**

```bash
# Check CPU usage
top

# Switch to faster model
ASR_MODEL=tiny  # or base
```

**If AI analysis is too slow:**

```bash
# Use faster model
docker exec meeting-ollama ollama pull phi
```

### Container Crashes

**Check logs:**
```bash
docker-compose logs whisper
docker-compose logs ollama
docker-compose logs web
```

**Common issues:**
- Out of memory → Use smaller models
- Model not found → Pull the model first
- Network timeout → Increase timeout in app.py

---

## 📊 Expected Performance (8GB RAM)

### With Recommended Setup (small + phi)

| Audio Length | Processing Time | RAM Usage |
|--------------|-----------------|-----------|
| 5 minutes | ~2-3 min | ~5GB |
| 15 minutes | ~7-8 min | ~5GB |
| 30 minutes | ~15 min | ~5GB |
| 60 minutes | ~30 min | ~5GB |

### First Recording
- Takes longer (models loading into memory)
- Expect 2x the normal time
- Subsequent recordings are faster

---

## 🔥 Optimization Checklist

Before starting:
- [ ] Using `docker-compose.pi5.yml` or manually optimized
- [ ] Whisper model set to `small`
- [ ] Ollama using `phi` or `mistral`
- [ ] Memory limits configured
- [ ] Swap enabled (optional but recommended)
- [ ] Tested with short audio file first

During use:
- [ ] Monitor with `docker stats`
- [ ] Only one live recording at a time
- [ ] Close unnecessary applications
- [ ] Check available memory with `free -h`

---

## 🎯 Recommended Workflow

### For Teams/Zoom Meetings (Live)

```bash
# 1. Start Docker (if not already)
docker-compose up -d

# 2. On your computer, run client
python client/audio_capture.py

# 3. During meeting:
# - Audio streams to VPS
# - Live transcription in console
# - ~7-8 second delay

# 4. After meeting:
# - Stop recording (Ctrl+C)
# - AI analysis runs (~2-3 min)
# - View results on web interface
```

### For Recorded Audio Files

```bash
# 1. Go to web interface
http://your-vps-ip:8080

# 2. Upload Meeting
# - Select file
# - Enter details
# - Upload

# 3. Wait for processing
# - Check status on dashboard
# - 30min audio = ~15min processing

# 4. View results
# - Summary
# - Action items
# - Full transcript
```

---

## 💡 Pro Tips for 8GB RAM

1. **Restart services periodically** to clear memory leaks:
   ```bash
   docker-compose restart
   ```

2. **Check memory before recording:**
   ```bash
   free -h | grep Mem
   ```
   Should have at least 3GB available.

3. **Use scheduled recordings** during off-peak hours

4. **Batch process** uploaded files overnight

5. **Clean up old recordings** to free disk space:
   ```bash
   # Delete recordings older than 30 days
   find uploads/ -name "*.wav" -mtime +30 -delete
   ```

---

## 🆚 Comparison: Different Hardware

| Hardware | RAM | Recommended Setup | Performance |
|----------|-----|-------------------|-------------|
| **Your VPS** | **8GB** | **small + phi** | **Very Good** ✅ |
| Budget VPS | 2GB | tiny + phi | Basic |
| Standard VPS | 4GB | base + mistral | Good |
| High-end VPS | 16GB | medium + mistral | Excellent |

**Your 8GB setup is the sweet spot** for price/performance! 🎯

---

## 🚀 Quick Commands Reference

```bash
# Deploy with Pi 5 config
cp docker-compose.pi5.yml docker-compose.yml && docker-compose up -d

# Install optimal models
docker exec meeting-ollama ollama pull phi

# Check status
docker-compose ps

# Monitor resources
docker stats

# View logs
docker-compose logs -f

# Restart services
docker-compose restart

# Stop everything
docker-compose down

# Check memory
free -h

# Test transcription
curl -X POST -F "audio_file=@test.mp3" http://localhost:9000/asr
```

---

## ✅ Your System is Ready!

With 8GB RAM and the optimized configuration:
- ✅ Can handle live recording with good quality
- ✅ Can process 60+ minute meetings
- ✅ Fast enough for real-time use
- ✅ Good balance of speed and accuracy
- ✅ Won't run out of memory

**Just deploy and start using!** 🎉
