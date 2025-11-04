#!/usr/bin/env python3
"""
Meeting Monitor - Background service for automatic meeting detection
Monitors for Teams meetings and offers to transcribe them automatically
"""

import psutil
import time
import threading
import os
import sys
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# Cross-platform imports
try:
    from plyer import notification
    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False
    print("Warning: plyer not installed. Notifications will use fallback.")

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False
    print("Warning: pystray not installed. System tray will be disabled.")

# Configuration
CONFIG_DIR = Path.home() / '.meeting-transcriber'
CONFIG_FILE = CONFIG_DIR / 'config.json'
STATE_FILE = CONFIG_DIR / 'state.json'

# Default configuration
DEFAULT_CONFIG = {
    'vps_url': 'http://localhost:8080',
    'check_interval': 10,  # seconds
    'auto_start': True,
    'show_notifications': True,
    'detect_teams': True,
    'calendar_enabled': False,
    'calendar_provider': None,  # 'google' or 'outlook'
}

# State management
current_state = {
    'monitoring': False,
    'recording': False,
    'current_meeting': None,
    'last_check': None,
    'detected_meetings': []
}

class MeetingMonitor:
    def __init__(self):
        self.config = self.load_config()
        self.state = self.load_state()
        self.running = False
        self.monitor_thread = None
        self.recording_process = None
        self.tray_icon = None

        # Ensure config directory exists
        CONFIG_DIR.mkdir(exist_ok=True)

    def load_config(self):
        """Load configuration from file"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    # Merge with defaults
                    return {**DEFAULT_CONFIG, **config}
            except Exception as e:
                print(f"Error loading config: {e}")
        return DEFAULT_CONFIG.copy()

    def save_config(self):
        """Save configuration to file"""
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def load_state(self):
        """Load state from file"""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading state: {e}")
        return current_state.copy()

    def save_state(self):
        """Save state to file"""
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"Error saving state: {e}")

    def is_teams_running(self):
        """Check if Microsoft Teams is running"""
        teams_process_names = [
            'Teams.exe',           # Windows
            'Microsoft Teams',     # macOS
            'teams',               # Linux
            'teams-for-linux'      # Linux alternative
        ]

        for proc in psutil.process_iter(['name']):
            try:
                proc_name = proc.info['name']
                if any(teams_name.lower() in proc_name.lower() for teams_name in teams_process_names):
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return False

    def is_in_meeting(self):
        """
        Detect if currently in a Teams meeting
        Uses platform-specific detection methods
        """
        if sys.platform == 'win32':
            return self._is_in_meeting_windows()
        elif sys.platform == 'darwin':
            return self._is_in_meeting_macos()
        else:
            return self._is_in_meeting_linux()

    def _is_in_meeting_windows(self):
        """Windows-specific meeting detection"""
        try:
            import win32gui
            import win32process

            def callback(hwnd, windows):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    # Teams meeting windows contain these patterns
                    meeting_indicators = [
                        '| Microsoft Teams',
                        'Meeting |',
                        'Call |',
                    ]
                    if any(indicator in title for indicator in meeting_indicators):
                        # Check if it's actually Teams
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        try:
                            proc = psutil.Process(pid)
                            if 'teams' in proc.name().lower():
                                windows.append({
                                    'title': title,
                                    'pid': pid,
                                    'hwnd': hwnd
                                })
                        except:
                            pass
                return True

            windows = []
            win32gui.EnumWindows(callback, windows)
            return len(windows) > 0, windows[0]['title'] if windows else None

        except ImportError:
            print("Warning: win32gui not available. Install pywin32 for better detection.")
            # Fallback: check if Teams process is using audio
            return self._check_audio_usage(), None
        except Exception as e:
            print(f"Error detecting Windows meeting: {e}")
            return False, None

    def _is_in_meeting_macos(self):
        """macOS-specific meeting detection"""
        try:
            # Use AppleScript to check active window
            script = '''
            tell application "System Events"
                set frontApp to name of first application process whose frontmost is true
                if frontApp contains "Microsoft Teams" then
                    tell process "Microsoft Teams"
                        set windowTitle to name of front window
                        return windowTitle
                    end tell
                end if
            end tell
            '''
            result = subprocess.run(['osascript', '-e', script],
                                  capture_output=True, text=True, timeout=5)

            if result.returncode == 0 and result.stdout.strip():
                title = result.stdout.strip()
                meeting_indicators = ['Meeting', 'Call', '|']
                in_meeting = any(indicator in title for indicator in meeting_indicators)
                return in_meeting, title if in_meeting else None

            return False, None

        except Exception as e:
            print(f"Error detecting macOS meeting: {e}")
            return self._check_audio_usage(), None

    def _is_in_meeting_linux(self):
        """Linux-specific meeting detection"""
        try:
            # Try to get active window title using xdotool
            result = subprocess.run(['xdotool', 'getactivewindow', 'getwindowname'],
                                  capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                title = result.stdout.strip()
                if 'teams' in title.lower():
                    meeting_indicators = ['Meeting', 'Call', '|']
                    in_meeting = any(indicator in title for indicator in meeting_indicators)
                    return in_meeting, title if in_meeting else None

            return False, None

        except FileNotFoundError:
            print("Warning: xdotool not installed. Install for better detection.")
            return self._check_audio_usage(), None
        except Exception as e:
            print(f"Error detecting Linux meeting: {e}")
            return self._check_audio_usage(), None

    def _check_audio_usage(self):
        """Fallback: Check if Teams is using audio (microphone/speakers)"""
        # This is a basic heuristic - if Teams is running and using CPU, likely in a meeting
        try:
            for proc in psutil.process_iter(['name', 'cpu_percent']):
                if 'teams' in proc.info['name'].lower():
                    # If Teams is using significant CPU, might be in meeting
                    cpu = proc.cpu_percent(interval=1)
                    if cpu > 5:  # Arbitrary threshold
                        return True, None
        except Exception as e:
            print(f"Error checking audio usage: {e}")

        return False, None

    def show_notification(self, title, message, timeout=10):
        """Show native notification"""
        if not self.config['show_notifications']:
            return

        try:
            if HAS_PLYER:
                notification.notify(
                    title=title,
                    message=message,
                    app_name='Meeting Transcriber',
                    timeout=timeout
                )
            else:
                # Fallback to print
                print(f"[NOTIFICATION] {title}: {message}")
        except Exception as e:
            print(f"Error showing notification: {e}")

    def prompt_start_recording(self, meeting_title=None):
        """Show popup asking if user wants to transcribe"""
        if not meeting_title:
            meeting_title = "Teams Meeting"

        message = f"Would you like to transcribe this meeting?\n\n{meeting_title}"

        # Show notification with interactive buttons (if supported)
        self.show_notification(
            "Meeting Detected",
            f"Click to transcribe: {meeting_title}"
        )

        # For now, auto-start if configured
        if self.config.get('auto_start', True):
            print(f"Auto-starting recording for: {meeting_title}")
            self.start_recording(meeting_title)
            return True

        return False

    def start_recording(self, meeting_title):
        """Start audio recording"""
        if self.recording_process:
            print("Already recording!")
            return False

        try:
            # Start the audio capture client
            client_path = Path(__file__).parent / 'audio_capture.py'

            # Run in background
            self.recording_process = subprocess.Popen([
                sys.executable,
                str(client_path),
                '--vps-url', self.config['vps_url'],
                '--title', meeting_title,
                '--auto-start'
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            self.state['recording'] = True
            self.state['current_meeting'] = {
                'title': meeting_title,
                'start_time': datetime.now().isoformat()
            }
            self.save_state()

            self.show_notification(
                "Recording Started",
                f"Transcribing: {meeting_title}"
            )

            return True

        except Exception as e:
            print(f"Error starting recording: {e}")
            return False

    def stop_recording(self):
        """Stop audio recording"""
        if not self.recording_process:
            print("Not currently recording")
            return

        try:
            # Send interrupt signal
            self.recording_process.terminate()
            self.recording_process.wait(timeout=10)

            meeting_title = self.state.get('current_meeting', {}).get('title', 'Meeting')

            self.recording_process = None
            self.state['recording'] = False
            self.state['current_meeting'] = None
            self.save_state()

            self.show_notification(
                "Recording Stopped",
                f"Processing: {meeting_title}"
            )

        except Exception as e:
            print(f"Error stopping recording: {e}")

    def monitor_loop(self):
        """Main monitoring loop"""
        print("Starting meeting monitor...")
        self.state['monitoring'] = True
        self.save_state()

        was_in_meeting = False
        current_meeting_title = None

        while self.running:
            try:
                # Check if Teams is running
                if self.config['detect_teams'] and self.is_teams_running():
                    # Check if in a meeting
                    in_meeting, meeting_title = self.is_in_meeting()

                    if in_meeting and not was_in_meeting:
                        # Meeting just started
                        print(f"Meeting detected: {meeting_title}")
                        current_meeting_title = meeting_title or "Teams Meeting"

                        if not self.state['recording']:
                            self.prompt_start_recording(current_meeting_title)

                        was_in_meeting = True

                    elif not in_meeting and was_in_meeting:
                        # Meeting just ended
                        print("Meeting ended")

                        if self.state['recording']:
                            self.stop_recording()

                        was_in_meeting = False
                        current_meeting_title = None

                self.state['last_check'] = datetime.now().isoformat()
                self.save_state()

                # Sleep for configured interval
                time.sleep(self.config['check_interval'])

            except Exception as e:
                print(f"Error in monitor loop: {e}")
                time.sleep(self.config['check_interval'])

        self.state['monitoring'] = False
        self.save_state()
        print("Meeting monitor stopped")

    def start(self):
        """Start monitoring"""
        if self.running:
            print("Monitor already running")
            return

        self.running = True
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()

        print("Meeting monitor started")

    def stop(self):
        """Stop monitoring"""
        self.running = False

        if self.recording_process:
            self.stop_recording()

        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)

        print("Meeting monitor stopped")

    def create_tray_icon(self):
        """Create system tray icon"""
        if not HAS_TRAY:
            print("System tray not available")
            return None

        # Create icon image
        def create_image():
            width = 64
            height = 64
            image = Image.new('RGB', (width, height), 'white')
            dc = ImageDraw.Draw(image)
            dc.rectangle((0, 0, width, height), fill='#2563eb')
            dc.ellipse((16, 16, 48, 48), fill='white')
            return image

        # Create menu
        menu = pystray.Menu(
            pystray.MenuItem('Meeting Transcriber', lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                'Monitoring',
                lambda: None,
                checked=lambda item: self.running,
                enabled=False
            ),
            pystray.MenuItem(
                'Recording',
                lambda: None,
                checked=lambda item: self.state['recording'],
                enabled=False
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Start Monitoring', lambda: self.start()),
            pystray.MenuItem('Stop Monitoring', lambda: self.stop()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Open Dashboard', self.open_dashboard),
            pystray.MenuItem('Settings', self.open_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', self.quit_app)
        )

        icon = pystray.Icon('meeting-transcriber', create_image(), 'Meeting Transcriber', menu)
        return icon

    def open_dashboard(self):
        """Open web dashboard in browser"""
        import webbrowser
        webbrowser.open(self.config['vps_url'])

    def open_settings(self):
        """Open settings (for now, just print config file location)"""
        print(f"Config file: {CONFIG_FILE}")
        self.show_notification(
            "Settings",
            f"Edit config file:\n{CONFIG_FILE}"
        )

    def quit_app(self):
        """Quit the application"""
        self.stop()
        if self.tray_icon:
            self.tray_icon.stop()

    def run(self):
        """Run the application with system tray"""
        # Start monitoring
        self.start()

        # Create and run tray icon
        if HAS_TRAY:
            self.tray_icon = self.create_tray_icon()
            self.tray_icon.run()
        else:
            # Run without tray - just keep monitoring
            print("Running without system tray (install pystray for tray icon)")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                self.stop()


def main():
    """Main entry point"""
    print("=" * 60)
    print("Meeting Transcriber - Background Monitor")
    print("=" * 60)
    print()

    monitor = MeetingMonitor()

    # Check if running as background service or interactive
    if '--background' in sys.argv:
        # Run as background service
        monitor.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            monitor.stop()
    else:
        # Run with system tray
        monitor.run()


if __name__ == '__main__':
    main()
