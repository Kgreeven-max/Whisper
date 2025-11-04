# Automatic Meeting Detection - Setup Guide

This guide will help you set up the **automatic Teams meeting detection** that works just like Notion's meeting transcriber.

---

## 🎯 What This Does

**Just like Notion:**
1. You join a Teams meeting
2. **Popup appears**: "Would you like to transcribe this meeting?"
3. Click "Yes" (or it auto-starts if configured)
4. Recording starts automatically
5. When meeting ends, recording stops automatically
6. You get the transcript + AI analysis!

**No manual commands needed!**

---

## 🚀 Quick Start

### Windows

```cmd
cd client
install_windows.bat
python meeting_monitor.py
```

### macOS

```bash
cd client
./install_macos.sh
source venv/bin/activate
python3 meeting_monitor.py
```

### Linux

```bash
cd client
./install_linux.sh
source venv/bin/activate
python3 meeting_monitor.py
```

---

## 📋 Detailed Setup

### Step 1: Install Dependencies

**All platforms:** Navigate to the client directory first
```bash
cd client
```

**Then run the platform-specific installer:**

| Platform | Command |
|----------|---------|
| Windows | `install_windows.bat` |
| macOS | `./install_macos.sh` |
| Linux | `./install_linux.sh` |

This installs:
- Python dependencies
- System tray support
- Notification system
- Platform-specific audio/window detection
- Calendar integration libraries

---

### Step 2: Configure VPS URL

Edit the configuration file:

**Location:** `~/.meeting-transcriber/config.json`

```bash
# Create config directory
mkdir -p ~/.meeting-transcriber

# Create config file
cat > ~/.meeting-transcriber/config.json << 'EOF'
{
  "vps_url": "http://your-vps-ip:8080",
  "check_interval": 10,
  "auto_start": true,
  "show_notifications": true,
  "detect_teams": true,
  "calendar_enabled": false
}
EOF
```

**Replace `your-vps-ip:8080` with your actual VPS URL!**

**Configuration Options:**
- `vps_url`: Your VPS address (e.g., `http://192.168.1.100:8080`)
- `check_interval`: How often to check for meetings (seconds)
- `auto_start`: Auto-start recording without asking (true/false)
- `show_notifications`: Show popup notifications (true/false)
- `detect_teams`: Enable Teams meeting detection (true/false)
- `calendar_enabled`: Use calendar integration (true/false)

---

### Step 3: Run the Monitor

**Method A: Interactive (with system tray)**

```bash
# Windows
python meeting_monitor.py

# macOS/Linux
python3 meeting_monitor.py
```

You'll see a **microphone icon** in your system tray!

**Method B: Background service**

```bash
# Run in background
python3 meeting_monitor.py --background &

# Check it's running
ps aux | grep meeting_monitor
```

---

### Step 4: Test It!

1. **Join a Teams meeting**
2. **Wait 10 seconds** (check interval)
3. **See notification**: "Meeting Detected - Click to transcribe"
4. **If auto_start=true**: Recording starts automatically!
5. **Leave meeting**: Recording stops, transcript processes

---

## 📅 Calendar Integration (Optional)

### Why Use Calendar Integration?

**Benefits:**
- Shows meeting name from calendar (not just "Teams Meeting")
- Knows attendee list automatically
- Can prompt you before meeting starts
- Better meeting organization

### Google Calendar Setup

**Step 1: Get Google Calendar API Credentials**

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create new project: "Meeting Transcriber"
3. Enable Google Calendar API
4. Create OAuth 2.0 credentials (Desktop app)
5. Download `credentials.json`

**Step 2: Save Credentials**

```bash
# Copy downloaded file
cp ~/Downloads/credentials.json ~/.meeting-transcriber/google_credentials.json
```

**Step 3: Authenticate**

```bash
cd client
python3 calendar_integration.py google
```

Follow the browser prompts to authenticate.

**Step 4: Enable in Config**

Edit `~/.meeting-transcriber/config.json`:

```json
{
  "calendar_enabled": true,
  "calendar_provider": "google"
}
```

**Step 5: Test**

```bash
python3 calendar_integration.py google
```

You should see your upcoming meetings!

### Microsoft Outlook/Teams Calendar Setup

**Step 1: Register Azure AD App**

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to: Azure Active Directory → App registrations
3. Click "New registration"
   - Name: "Meeting Transcriber"
   - Supported account types: "Accounts in this organizational directory only"
   - Redirect URI: Leave blank
4. Click "Register"
5. Copy the **Application (client) ID**

**Step 2: Set Permissions**

1. In your app, go to: API permissions
2. Add permission → Microsoft Graph → Delegated permissions
3. Add: `Calendars.Read`, `Calendars.Read.Shared`
4. Click "Grant admin consent"

**Step 3: Set Environment Variable**

```bash
# Windows (PowerShell)
$env:MS_CLIENT_ID="your-client-id-here"

# Windows (CMD)
set MS_CLIENT_ID=your-client-id-here

# macOS/Linux
export MS_CLIENT_ID="your-client-id-here"

# Make permanent (add to ~/.bashrc or ~/.zshrc)
echo 'export MS_CLIENT_ID="your-client-id-here"' >> ~/.bashrc
```

**Step 4: Authenticate**

```bash
python3 calendar_integration.py outlook
```

Follow the device code flow prompts.

**Step 5: Enable in Config**

Edit `~/.meeting-transcriber/config.json`:

```json
{
  "calendar_enabled": true,
  "calendar_provider": "outlook"
}
```

---

## 🖥️ Auto-Start on Boot

### Windows

**Option 1: Task Scheduler**

1. Open Task Scheduler
2. Create Basic Task
3. Name: "Meeting Transcriber"
4. Trigger: "When I log on"
5. Action: "Start a program"
   - Program: `python`
   - Arguments: `C:\path\to\client\meeting_monitor.py`
6. Finish

**Option 2: Startup Folder**

1. Press `Win+R`
2. Type: `shell:startup`
3. Create shortcut to `meeting_monitor.py`

### macOS

Create Launch Agent:

```bash
# Create plist file
cat > ~/Library/LaunchAgents/com.meetingtranscriber.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.meetingtranscriber</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/client/meeting_monitor.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF

# Load it
launchctl load ~/Library/LaunchAgents/com.meetingtranscriber.plist

# Enable it
launchctl start com.meetingtranscriber
```

### Linux

**Option 1: Systemd User Service**

```bash
# Create service file
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/meeting-transcriber.service << 'EOF'
[Unit]
Description=Meeting Transcriber Monitor
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /path/to/client/meeting_monitor.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

# Enable and start
systemctl --user enable meeting-transcriber
systemctl --user start meeting-transcriber

# Check status
systemctl --user status meeting-transcriber
```

**Option 2: Desktop Autostart**

```bash
# Create desktop entry
mkdir -p ~/.config/autostart

cat > ~/.config/autostart/meeting-transcriber.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=Meeting Transcriber
Exec=/usr/bin/python3 /path/to/client/meeting_monitor.py
Terminal=false
StartupNotify=false
EOF
```

---

## 🎛️ System Tray Controls

When running, you'll have a **system tray icon** with these options:

- **Monitoring** ✓ - Shows if monitoring is active
- **Recording** ✓ - Shows if currently recording
- **Start Monitoring** - Start watching for meetings
- **Stop Monitoring** - Stop watching
- **Open Dashboard** - Opens web interface in browser
- **Settings** - View/edit configuration
- **Quit** - Stop the application

---

## 🔧 How It Works

### Meeting Detection Process

1. **Every 10 seconds** (configurable):
   - Check if Teams is running
   - Check if you're in a meeting
   - Check calendar for upcoming meetings

2. **When meeting detected**:
   - Get meeting title (from window or calendar)
   - Show notification
   - If `auto_start=true`: Start recording automatically
   - If `auto_start=false`: Wait for user click

3. **While recording**:
   - Audio streams to VPS every 5 seconds
   - Real-time transcription
   - Updates database

4. **When meeting ends**:
   - Stops recording automatically
   - Finalizes transcript
   - AI analysis runs
   - Notification: "Transcript ready!"

### Platform-Specific Detection

**Windows:**
- Uses `win32gui` to detect Teams windows
- Looks for window titles containing: "Meeting |", "Call |", "| Microsoft Teams"
- Checks if process is actually Teams

**macOS:**
- Uses AppleScript to get active window
- Checks Microsoft Teams window titles
- Detects meeting indicators

**Linux:**
- Uses `xdotool` to get active window
- Monitors Teams process
- Checks window titles for meeting indicators

**Fallback (all platforms):**
- If window detection fails, checks CPU usage
- Teams using >5% CPU = likely in meeting

---

## 🐛 Troubleshooting

### "No module named 'XXX'"

Install missing dependencies:

```bash
pip install -r requirements.txt

# Windows-specific
pip install pywin32

# Linux-specific
pip install python-xlib
```

### Meetings Not Detected

**Check Teams is running:**
```bash
# Windows
tasklist | findstr Teams

# macOS/Linux
ps aux | grep -i teams
```

**Check monitor is running:**
```bash
ps aux | grep meeting_monitor
```

**Check logs:**

Look at terminal output or:
```bash
cat ~/.meeting-transcriber/state.json
```

### Notifications Not Showing

**Windows:**
- Check notification settings (Allow from apps)
- Enable for Python

**macOS:**
- System Preferences → Notifications
- Allow Python notifications

**Linux:**
- Install: `sudo apt install libnotify-bin`
- Check D-Bus is running

### VPS Connection Fails

**Test connection:**
```bash
curl http://your-vps-ip:8080/health
```

**Check firewall:**
```bash
# VPS side
sudo ufw allow 8080/tcp
```

**Check config:**
```bash
cat ~/.meeting-transcriber/config.json
```

### Calendar Not Working

**Google Calendar:**
1. Check credentials file exists:
   ```bash
   ls ~/.meeting-transcriber/google_credentials.json
   ```
2. Re-authenticate:
   ```bash
   rm ~/.meeting-transcriber/google_token.pickle
   python3 calendar_integration.py google
   ```

**Microsoft/Outlook:**
1. Check client ID is set:
   ```bash
   echo $MS_CLIENT_ID
   ```
2. Re-authenticate:
   ```bash
   rm ~/.meeting-transcriber/ms_token.json
   python3 calendar_integration.py outlook
   ```

---

## 💡 Usage Tips

### Best Practices

1. **Start monitor before joining meetings**
   - Set up auto-start on boot
   - Or start manually before first meeting of day

2. **Configure auto_start based on preference**
   - `true`: Automatic, hands-free
   - `false`: Manual confirmation for each meeting

3. **Use calendar integration**
   - Better meeting names
   - Attendee information
   - Preparation time

4. **Check VPS regularly**
   - Ensure it's running
   - Monitor disk space
   - Review transcripts

### Common Workflows

**Workflow 1: Fully Automatic (Recommended)**

```json
{
  "auto_start": true,
  "calendar_enabled": true,
  "show_notifications": true
}
```

- Monitor runs at startup
- Join meeting → Auto records
- Leave meeting → Auto stops
- No interaction needed!

**Workflow 2: Manual Confirmation**

```json
{
  "auto_start": false,
  "calendar_enabled": true,
  "show_notifications": true
}
```

- Monitor detects meeting
- Shows prompt
- You click "Yes" to record
- More control, less automatic

**Workflow 3: Calendar-Only**

```json
{
  "auto_start": false,
  "calendar_enabled": true,
  "detect_teams": false
}
```

- Only uses calendar
- Prompts before scheduled meetings
- Doesn't detect ad-hoc meetings

---

## 📊 Performance

### Resource Usage

**Idle (monitoring):**
- CPU: <1%
- RAM: ~50-100MB
- Network: Minimal

**During recording:**
- CPU: 5-10%
- RAM: ~200-300MB
- Network: ~500KB per 5-second chunk

**Battery impact (laptop):**
- Minimal when monitoring
- Moderate during recording (~same as Teams itself)

### Optimization Tips

1. **Increase check interval** (use less CPU):
   ```json
   "check_interval": 30
   ```

2. **Disable calendar** (if not needed):
   ```json
   "calendar_enabled": false
   ```

3. **Run only when needed**:
   - Don't set auto-start
   - Start before meetings, stop after

---

## ✅ Setup Checklist

Before first use:

- [ ] Install dependencies for your platform
- [ ] Configure VPS URL in config.json
- [ ] Test VPS connection (`curl http://vps:8080/health`)
- [ ] Run monitor (`python3 meeting_monitor.py`)
- [ ] Join test Teams meeting
- [ ] Verify detection works
- [ ] Set up calendar integration (optional)
- [ ] Configure auto-start on boot (optional)
- [ ] Test full workflow end-to-end

---

## 🎉 You're Ready!

Your Notion-style automatic meeting transcriber is set up!

**What happens now:**

1. **Monitor runs in background** ✓
2. **You join Teams meeting** ✓
3. **Popup: "Transcribe this meeting?"** ✓
4. **Recording starts automatically** ✓
5. **Meeting ends, recording stops** ✓
6. **Transcript ready in minutes!** ✓

**No manual commands, no uploads, no hassle!**

Just like Notion, but running on YOUR infrastructure! 🚀

---

## 📞 Getting Help

**Check logs:**
```bash
cat ~/.meeting-transcriber/state.json
```

**Test each component:**
```bash
# Test meeting detection
python3 meeting_monitor.py

# Test calendar
python3 calendar_integration.py google

# Test VPS
curl http://your-vps:8080/health
```

**Common issues:** See Troubleshooting section above

**Still stuck?** Check the main README.md or TESTING.md
