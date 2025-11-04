#!/usr/bin/env python3
"""
Meeting Transcriber - Desktop Audio Capture Client
Captures system audio and streams to VPS for real-time transcription
"""

import pyaudio
import wave
import requests
import json
import time
import threading
import os
import sys
from datetime import datetime

# Configuration
VPS_URL = "http://localhost:8080"  # Change this to your VPS URL
CHUNK_SIZE = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1  # Mono audio
RATE = 16000  # 16kHz for Whisper
CHUNK_DURATION = 5  # Send audio every 5 seconds

class AudioCapture:
    def __init__(self, vps_url, meeting_title="Live Meeting"):
        self.vps_url = vps_url.rstrip('/')
        self.meeting_title = meeting_title
        self.is_recording = False
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.session_id = None
        self.frames = []
        self.temp_file = None

    def list_audio_devices(self):
        """List all available audio devices"""
        print("\n=== Available Audio Devices ===")
        info = self.audio.get_host_api_info_by_index(0)
        num_devices = info.get('deviceCount')

        devices = []
        for i in range(0, num_devices):
            device_info = self.audio.get_device_info_by_host_api_device_index(0, i)
            if device_info.get('maxInputChannels') > 0:
                devices.append({
                    'index': i,
                    'name': device_info.get('name'),
                    'channels': device_info.get('maxInputChannels')
                })
                print(f"{i}: {device_info.get('name')} (Channels: {device_info.get('maxInputChannels')})")

        return devices

    def start_session(self):
        """Start a new recording session on the VPS"""
        try:
            response = requests.post(
                f"{self.vps_url}/api/live/start",
                json={
                    'title': self.meeting_title,
                    'timestamp': datetime.now().isoformat()
                },
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                self.session_id = data.get('session_id')
                print(f"✅ Session started: {self.session_id}")
                return True
            else:
                print(f"❌ Failed to start session: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ Error starting session: {e}")
            return False

    def send_audio_chunk(self, audio_data):
        """Send audio chunk to VPS for processing"""
        if not self.session_id:
            return

        try:
            # Save chunk to temporary WAV file
            temp_path = f"/tmp/chunk_{int(time.time())}.wav"
            wf = wave.open(temp_path, 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.audio.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(audio_data)
            wf.close()

            # Send to VPS
            with open(temp_path, 'rb') as f:
                files = {'audio': f}
                data = {'session_id': self.session_id}
                response = requests.post(
                    f"{self.vps_url}/api/live/chunk",
                    files=files,
                    data=data,
                    timeout=30
                )

            # Clean up
            os.remove(temp_path)

            if response.status_code == 200:
                result = response.json()
                if result.get('text'):
                    print(f"📝 {result.get('text')}")
                return True
            else:
                print(f"⚠️ Chunk processing failed: {response.status_code}")
                return False

        except Exception as e:
            print(f"⚠️ Error sending chunk: {e}")
            return False

    def stop_session(self):
        """Stop the recording session"""
        if not self.session_id:
            return

        try:
            response = requests.post(
                f"{self.vps_url}/api/live/stop",
                json={'session_id': self.session_id},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                meeting_id = data.get('meeting_id')
                print(f"\n✅ Session completed!")
                print(f"View at: {self.vps_url}/meeting/{meeting_id}")
                return True
            else:
                print(f"❌ Failed to stop session: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ Error stopping session: {e}")
            return False

    def start_recording(self, device_index=None):
        """Start capturing audio"""
        if self.is_recording:
            print("Already recording!")
            return

        # Start session on VPS
        if not self.start_session():
            return

        self.is_recording = True
        self.frames = []

        try:
            # Open audio stream
            self.stream = self.audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=CHUNK_SIZE
            )

            print(f"\n🎙️  Recording started...")
            print(f"Meeting: {self.meeting_title}")
            print(f"Press Ctrl+C to stop\n")

            # Record and send in chunks
            chunk_frames = []
            chunks_per_send = int(RATE / CHUNK_SIZE * CHUNK_DURATION)
            chunk_count = 0

            while self.is_recording:
                try:
                    data = self.stream.read(CHUNK_SIZE, exception_on_overflow=False)
                    chunk_frames.append(data)
                    self.frames.append(data)
                    chunk_count += 1

                    # Send chunk every CHUNK_DURATION seconds
                    if chunk_count >= chunks_per_send:
                        audio_data = b''.join(chunk_frames)
                        threading.Thread(
                            target=self.send_audio_chunk,
                            args=(audio_data,),
                            daemon=True
                        ).start()
                        chunk_frames = []
                        chunk_count = 0

                except KeyboardInterrupt:
                    print("\n\n⏹️  Stopping recording...")
                    break
                except Exception as e:
                    print(f"⚠️ Recording error: {e}")
                    break

            # Send any remaining audio
            if chunk_frames:
                audio_data = b''.join(chunk_frames)
                self.send_audio_chunk(audio_data)

        except Exception as e:
            print(f"❌ Failed to start recording: {e}")
        finally:
            self.stop_recording()

    def stop_recording(self):
        """Stop capturing audio"""
        self.is_recording = False

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()

        # Stop session on VPS
        self.stop_session()

        print("Recording stopped.")

    def cleanup(self):
        """Clean up resources"""
        if self.stream:
            self.stream.close()
        self.audio.terminate()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Meeting Transcriber - Live Audio Capture')
    parser.add_argument('--vps-url', help='VPS URL', default=VPS_URL)
    parser.add_argument('--title', help='Meeting title', default=None)
    parser.add_argument('--auto-start', action='store_true', help='Start recording automatically without prompts')
    parser.add_argument('--device', type=int, help='Audio device index', default=None)

    args = parser.parse_args()

    print("=" * 50)
    print("Meeting Transcriber - Live Audio Capture")
    print("=" * 50)

    # Get VPS URL
    if not args.auto_start:
        vps_url = input(f"\nEnter VPS URL [{args.vps_url}]: ").strip()
        if not vps_url:
            vps_url = args.vps_url
    else:
        vps_url = args.vps_url

    # Get meeting title
    if args.title:
        meeting_title = args.title
    elif not args.auto_start:
        meeting_title = input("Enter meeting title [Live Meeting]: ").strip()
        if not meeting_title:
            meeting_title = "Live Meeting"
    else:
        meeting_title = "Live Meeting"

    # Create capture instance
    capture = AudioCapture(vps_url, meeting_title)

    # List audio devices
    devices = capture.list_audio_devices()

    if not devices:
        print("\n❌ No input devices found!")
        print("\nTroubleshooting:")
        print("- Check your microphone is connected")
        print("- Check audio permissions")
        print("- Try running as administrator/sudo")
        return

    # Select device
    if args.device is not None:
        device_index = args.device
    elif not args.auto_start:
        print("\nSelect audio device:")
        print("💡 Tip: For system audio capture:")
        print("   - Windows: Use 'Stereo Mix' or install VB-Cable")
        print("   - Mac: Use BlackHole or Loopback")
        print("   - Linux: Use PulseAudio monitor device")

        device_input = input(f"\nDevice number [0]: ").strip()
        device_index = int(device_input) if device_input else 0
    else:
        device_index = 0  # Use default device in auto-start mode

    # Verify VPS connection
    print(f"\n🔄 Testing connection to {vps_url}...")
    try:
        response = requests.get(f"{vps_url}/health", timeout=5)
        if response.status_code == 200:
            print("✅ VPS connection successful!")
        else:
            print(f"⚠️ VPS returned status {response.status_code}")
    except Exception as e:
        print(f"❌ Cannot connect to VPS: {e}")
        print("\nMake sure:")
        print("1. VPS is running (docker-compose up)")
        print("2. URL is correct (include http://)")
        print("3. Firewall allows connection")
        return

    # Start recording
    try:
        capture.start_recording(device_index=device_index)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    finally:
        capture.cleanup()
        print("\n👋 Goodbye!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        sys.exit(0)
