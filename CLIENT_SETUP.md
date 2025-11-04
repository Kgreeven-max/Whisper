# Desktop Client Setup - Live Audio Capture

This guide will help you set up the desktop client to capture system audio during meetings, just like Notion's meeting transcriber.

## What the Client Does

The desktop client:
- **Captures your computer's audio** (what you hear in Teams/Zoom/etc.)
- **Streams it to your VPS** in real-time
- **Shows live transcription** as the meeting happens
- **Works with any meeting platform** (Teams, Zoom, Google Meet, etc.)

## Quick Start

```bash
# 1. Install dependencies
cd client
pip install -r requirements.txt

# 2. Run the client
python audio_capture.py

# 3. Enter your VPS URL (e.g., http://your-vps-ip:8080)
# 4. Enter meeting title
# 5. Select audio device
# 6. Start your meeting!
```

---

## Platform-Specific Setup

### 🪟 Windows

#### Step 1: Enable Stereo Mix

Windows can capture system audio using "Stereo Mix":

1. Right-click the **speaker icon** in system tray
2. Select **"Sounds"** → **"Recording"** tab
3. Right-click in empty space → **"Show Disabled Devices"**
4. Find **"Stereo Mix"** → Right-click → **"Enable"**
5. Right-click **"Stereo Mix"** → **"Set as Default Device"**

#### Step 2: Install Python Dependencies

```bash
pip install pyaudio requests
```

**If PyAudio fails to install:**

```bash
# Download wheel file:
# Go to: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
# Download PyAudio‑0.2.14‑cp311‑cp311‑win_amd64.whl (adjust for your Python version)

pip install PyAudio‑0.2.14‑cp311‑cp311‑win_amd64.whl
pip install requests
```

#### Step 3: Alternative - Use VB-Cable

If Stereo Mix doesn't work:

1. Download **VB-CABLE Virtual Audio Device**:
   - https://vb-audio.com/Cable/
2. Install it
3. Set VB-Cable as default playback device
4. Use VB-Cable as input in the client

### 🍎 macOS

#### Step 1: Install BlackHole (Virtual Audio Driver)

```bash
# Using Homebrew
brew install blackhole-2ch

# Or download from:
# https://existential.audio/blackhole/
```

#### Step 2: Create Multi-Output Device

1. Open **Audio MIDI Setup** (Applications → Utilities)
2. Click **"+"** → **"Create Multi-Output Device"**
3. Check both:
   - **Built-in Output** (to hear audio)
   - **BlackHole 2ch** (to capture audio)
4. Right-click → **"Use This Device For Sound Output"**

#### Step 3: Install Python Dependencies

```bash
# Install portaudio first
brew install portaudio

# Install Python packages
pip3 install pyaudio requests
```

#### Step 4: Run the Client

```bash
python3 client/audio_capture.py
```

Select "BlackHole 2ch" as the input device.

### 🐧 Linux

#### Step 1: Install Dependencies

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3-pyaudio python3-requests portaudio19-dev
```

**Fedora:**
```bash
sudo dnf install python3-pyaudio python3-requests portaudio-devel
```

**Arch:**
```bash
sudo pacman -S python-pyaudio python-requests portaudio
```

#### Step 2: Find Your Audio Monitor Device

```bash
pactl list sources | grep -i monitor
```

Look for something like:
- `alsa_output.pci-0000_00_1f.3.analog-stereo.monitor`

#### Step 3: Run the Client

```bash
python3 client/audio_capture.py
```

Select the monitor device when prompted.

---

## Usage

### Starting a Recording

1. **Launch the client:**
   ```bash
   python client/audio_capture.py
   ```

2. **Enter VPS URL:**
   ```
   Enter VPS URL [http://localhost:8080]: http://your-vps-ip:8080
   ```

3. **Enter meeting title:**
   ```
   Enter meeting title [Live Meeting]: Weekly Team Standup
   ```

4. **Select audio device:**
   ```
   === Available Audio Devices ===
   0: Microphone (Realtek)
   1: Stereo Mix (Realtek)
   2: VB-Cable Output

   Select audio device: 1
   ```

5. **Verify VPS connection:**
   ```
   🔄 Testing connection to http://your-vps:8080...
   ✅ VPS connection successful!
   ```

6. **Start your meeting** (Teams/Zoom/etc.)

7. **Watch live transcription:**
   ```
   🎙️  Recording started...
   Meeting: Weekly Team Standup
   Press Ctrl+C to stop

   📝 Okay so let's start with updates from last week
   📝 John do you want to go first
   📝 Sure we completed the authentication module
   ```

8. **Stop recording:**
   - Press `Ctrl+C`
   - Client uploads final analysis
   - Get meeting URL to view results

### Viewing Results

After stopping:
```
✅ Session completed!
View at: http://your-vps:8080/meeting/42
```

Open that URL to see:
- Full transcript
- AI-generated summary
- Key points
- Action items
- Decisions

---

## Troubleshooting

### No Audio Devices Found

**Windows:**
- Enable "Stereo Mix" in Sound settings
- Install VB-Cable as alternative

**macOS:**
- Install and configure BlackHole
- Create Multi-Output Device

**Linux:**
- Check PulseAudio is running: `pulseaudio --check`
- List sources: `pactl list sources`

### PyAudio Installation Fails

**Windows:**
- Download precompiled wheel from:
  https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio

**macOS:**
- Install portaudio: `brew install portaudio`
- Then: `pip3 install pyaudio`

**Linux:**
- Install dev package: `sudo apt install portaudio19-dev`

### Connection to VPS Fails

1. **Check VPS is running:**
   ```bash
   curl http://your-vps:8080/health
   ```

2. **Check firewall allows port 8080:**
   ```bash
   sudo ufw allow 8080/tcp
   ```

3. **Use correct URL format:**
   - ✅ `http://192.168.1.100:8080`
   - ✅ `http://your-domain.com:8080`
   - ❌ `your-vps-ip` (missing http://)
   - ❌ `https://...` (if you're not using SSL)

### No Transcript Appearing

1. **Check Whisper is running:**
   ```bash
   docker-compose logs whisper
   ```

2. **Verify audio is being captured:**
   - Play some audio/music
   - Check if client shows "Sending chunk..."

3. **Check VPS logs:**
   ```bash
   docker-compose logs web
   ```

### Delay in Transcription

This is normal! Transcription happens every 5 seconds:
- Audio is collected for 5 seconds
- Sent to VPS
- Whisper transcribes it (~2-3 seconds)
- Text appears in console

Total delay: ~7-8 seconds

### Poor Transcription Quality

1. **Use better Whisper model:**
   Edit `docker-compose.yml`:
   ```yaml
   environment:
     - ASR_MODEL=medium  # or large
   ```

2. **Improve audio quality:**
   - Use headphones (reduces echo)
   - Mute when not speaking
   - Reduce background noise

3. **Speak clearly:**
   - Don't talk over others
   - Pause between sentences
   - Use clear language

---

## Advanced Configuration

### Change Chunk Duration

Edit `client/audio_capture.py`:

```python
CHUNK_DURATION = 10  # Send audio every 10 seconds instead of 5
```

Longer chunks:
- ✅ Better transcription quality
- ✅ More context for Whisper
- ❌ Longer delay before seeing text

### Run in Background

**Linux/macOS:**
```bash
nohup python3 client/audio_capture.py &
```

**Windows:**
Use Task Scheduler or create a .bat file

### Custom Audio Format

Edit `client/audio_capture.py`:

```python
RATE = 44100  # Higher quality (default 16000)
CHANNELS = 2  # Stereo (default 1 for mono)
```

⚠️ Higher quality = more bandwidth and processing

---

## Comparison: Desktop Client vs Web Interface

| Feature | Desktop Client | Web Interface |
|---------|---------------|---------------|
| Setup | Requires Python | No install needed |
| Audio Source | System audio | Microphone only |
| Quality | Better | Limited by browser |
| Compatibility | All meeting apps | Any device |
| Privacy | Audio stays on VPS | Same |
| Reliability | Very reliable | Network dependent |

**Recommendation:** Use Desktop Client for best results

---

## Tips for Best Results

### Audio Setup
- ✅ Use headphones to prevent echo
- ✅ Mute when not speaking
- ✅ Position mic properly
- ✅ Use good quality audio device

### Meeting Practices
- ✅ One person speaks at a time
- ✅ Speak clearly and at moderate pace
- ✅ Avoid talking over each other
- ✅ Pause after important points

### Technical Tips
- ✅ Close unnecessary apps (reduce CPU load)
- ✅ Use wired internet (more stable)
- ✅ Check VPS has enough resources
- ✅ Test with short meeting first

---

## Automated Startup (Optional)

### Windows - Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Trigger: "When I log on"
4. Action: Start program
   - Program: `python`
   - Arguments: `C:\path\to\client\audio_capture.py`

### macOS - Launch Agent

Create `~/Library/LaunchAgents/com.meetingtranscriber.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.meetingtranscriber</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/client/audio_capture.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

Load it:
```bash
launchctl load ~/Library/LaunchAgents/com.meetingtranscriber.plist
```

### Linux - systemd Service

Create `/etc/systemd/system/meeting-transcriber-client.service`:

```ini
[Unit]
Description=Meeting Transcriber Client
After=network.target

[Service]
Type=simple
User=youruser
ExecStart=/usr/bin/python3 /path/to/client/audio_capture.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl enable meeting-transcriber-client
sudo systemctl start meeting-transcriber-client
```

---

## Security Notes

- Audio is streamed over HTTP by default
- For production, use HTTPS (set up SSL on VPS)
- Audio is NOT stored permanently on your computer
- Only final transcript is saved on VPS
- Temporary chunks are deleted after processing

---

## Getting Help

**Client won't start:**
```bash
python client/audio_capture.py --debug
```

**Check logs:**
- Client console output
- VPS logs: `docker-compose logs web`

**Common issues:**
1. PyAudio not installed → See installation section
2. No audio devices → See audio setup section
3. VPS connection fails → Check firewall and URL
4. No transcription → Check Whisper logs

**Still stuck?** Check TESTING.md for more troubleshooting steps.
