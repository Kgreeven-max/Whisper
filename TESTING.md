# Testing & Troubleshooting Checklist

## Initial Deployment Test

### Step 1: Start Services
```bash
cd /path/to/meeting-transcriber
docker-compose up -d
```

**Expected**: All 3 services start without errors

**If it fails**:
- Check: `docker-compose logs`
- Common issue: Port already in use
- Fix: Change ports in docker-compose.yml

### Step 2: Check Service Health (wait 2-3 minutes)
```bash
docker-compose ps
```

**Expected**: All services show "Up" status

**If whisper fails**:
```bash
docker-compose logs whisper
```
- May need more memory
- Try smaller model: Change `ASR_MODEL=tiny` in docker-compose.yml

**If ollama fails**:
```bash
docker-compose logs ollama
```
- Usually just needs more time to start

**If web fails**:
```bash
docker-compose logs web
```
- Check if uploads/data directories exist
- May need to create them manually: `mkdir -p uploads data`

### Step 3: Test Web Interface
```bash
curl http://localhost:8080/health
```

**Expected**: `{"status":"healthy","timestamp":"..."}`

**If connection refused**:
- Web service not started
- Check logs: `docker-compose logs web`
- May need to rebuild: `docker-compose up -d --build`

### Step 4: Test Whisper API
```bash
curl http://localhost:9000/
```

**Expected**: Some response (even error is OK - means it's running)

**If connection refused**:
- Whisper not started yet (can take 2-3 minutes first time)
- Check: `docker-compose logs whisper`

### Step 5: Test Ollama API
```bash
curl http://localhost:11434/
```

**Expected**: "Ollama is running"

**If fails**:
- Check: `docker-compose logs ollama`

### Step 6: Pull LLM Model
```bash
docker exec meeting-ollama ollama pull llama2
```

**Expected**: Downloads model (takes 5-10 minutes)

**If fails**:
- Internet connection issue
- Try smaller model: `docker exec meeting-ollama ollama pull phi`

### Step 7: Test Upload
1. Open browser: http://your-server-ip:8080
2. Click "Upload Meeting"
3. Upload a SHORT test file (1-2 minutes of audio)

**Expected**:
- File uploads successfully
- Redirects to meeting page
- Status shows "Processing"

**If upload fails**:
- Check file size < 500MB
- Check format is supported
- Check logs: `docker-compose logs web`

### Step 8: Wait for Processing
- Wait 5-10 minutes for short file
- Refresh the page

**Expected**:
- Status changes to "Completed"
- Summary appears
- Transcript appears

**If stuck on "Processing"**:
```bash
# Check if processing is actually happening
docker-compose logs web

# Check if Whisper is responding
docker-compose logs whisper

# Check database
docker exec meeting-web sqlite3 /app/data/meetings.db "SELECT id, title, status FROM meetings;"
```

## Common Issues & Fixes

### Issue: "No module named 'flask'"
**Cause**: Dependencies not installed
**Fix**:
```bash
docker-compose down
docker-compose up -d --build
```

### Issue: Upload fails with "413 Request Entity Too Large"
**Cause**: Nginx limiting size
**Fix**: Add to nginx config:
```nginx
client_max_body_size 500M;
```

### Issue: Whisper transcription fails
**Symptoms**: Meeting stuck in "processing", logs show Whisper errors
**Fixes**:
1. Check Whisper is running: `curl http://localhost:9000/`
2. Try smaller model in docker-compose.yml: `ASR_MODEL=tiny`
3. Check audio format is supported
4. Restart Whisper: `docker-compose restart whisper`

### Issue: Ollama analysis fails
**Symptoms**: Transcript appears but no summary/action items
**Fixes**:
1. Check model is installed: `docker exec meeting-ollama ollama list`
2. Pull model: `docker exec meeting-ollama ollama pull llama2`
3. Check Ollama running: `curl http://localhost:11434/`
4. Try smaller/faster model: `phi` instead of `llama2`

### Issue: "Database is locked"
**Cause**: Multiple processes accessing database
**Fix**:
```bash
docker-compose restart web
```

### Issue: Out of memory
**Symptoms**: Services crash, logs show "Killed"
**Fixes**:
1. Use smaller models:
   - Whisper: `ASR_MODEL=tiny`
   - Ollama: `phi` instead of `llama2`
2. Reduce workers in Dockerfile: `--workers 2`
3. Upgrade VPS RAM

### Issue: Templates not found
**Symptoms**: "TemplateNotFound" error
**Fix**: Check templates directory exists in Docker:
```bash
docker exec meeting-web ls -la /app/templates/
```

### Issue: Uploads directory not writable
**Symptoms**: "Permission denied" on upload
**Fix**:
```bash
chmod 777 uploads data
docker-compose restart web
```

## Performance Testing

### Test with different file sizes:
- ✅ 1 minute audio (test model works)
- ✅ 5 minute audio (normal use case)
- ✅ 30 minute audio (typical meeting)
- ✅ 60+ minute audio (long meeting)

### Expected processing times:
- 1 min audio = ~1-2 min processing
- 5 min audio = ~3-5 min processing
- 30 min audio = ~10-15 min processing
- 60 min audio = ~20-30 min processing

## Code Issues to Check

### 1. Check app.py line 150
Model name should match what you pulled:
```python
'model': 'llama2',  # or 'mistral', 'phi', etc.
```

### 2. Check Docker network communication
Services should communicate via service names:
- `http://whisper:9000` (not `http://localhost:9000`)
- `http://ollama:11434` (not `http://localhost:11434`)

This is correct in the code ✅

### 3. Check database path consistency
- Config: `/app/data/meetings.db`
- Volume mount: `./data:/app/data`

This is correct ✅

## Manual Test Script

Save this as `test.sh` and run to verify everything:

```bash
#!/bin/bash
echo "Testing Meeting Transcriber..."

echo "1. Testing web health..."
if curl -s http://localhost:8080/health | grep -q "healthy"; then
    echo "✅ Web service OK"
else
    echo "❌ Web service FAILED"
fi

echo "2. Testing Whisper..."
if curl -s http://localhost:9000/ > /dev/null 2>&1; then
    echo "✅ Whisper OK"
else
    echo "❌ Whisper FAILED"
fi

echo "3. Testing Ollama..."
if curl -s http://localhost:11434/ | grep -q "Ollama"; then
    echo "✅ Ollama OK"
else
    echo "❌ Ollama FAILED"
fi

echo "4. Testing database..."
if docker exec meeting-web sqlite3 /app/data/meetings.db "SELECT count(*) FROM meetings;" > /dev/null 2>&1; then
    echo "✅ Database OK"
else
    echo "❌ Database FAILED"
fi

echo "5. Checking model..."
if docker exec meeting-ollama ollama list | grep -q "llama2\|mistral\|phi"; then
    echo "✅ LLM model installed"
else
    echo "⚠️  No LLM model found. Run: docker exec meeting-ollama ollama pull llama2"
fi

echo ""
echo "Done! Check results above."
```

## If Nothing Works

### Nuclear option - complete reset:
```bash
docker-compose down -v
rm -rf uploads/* data/*
docker-compose up -d --build
# Wait 3 minutes
docker exec meeting-ollama ollama pull llama2
# Wait 5 minutes
# Try uploading again
```

## Getting Help

If you encounter issues:
1. Collect logs: `docker-compose logs > debug.log`
2. Check service status: `docker-compose ps`
3. Share specific error messages
4. Include: OS, RAM, Docker version

## Expected Behavior

**Working system should**:
- ✅ Show dashboard at http://server:8080
- ✅ Accept audio uploads
- ✅ Process within reasonable time
- ✅ Generate transcript
- ✅ Generate AI summary
- ✅ Allow search
- ✅ Export to markdown

**First upload will be slowest** (services warming up)
