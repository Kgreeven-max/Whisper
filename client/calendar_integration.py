#!/usr/bin/env python3
"""
Calendar Integration for Meeting Transcriber
Supports Google Calendar and Microsoft Outlook/Teams Calendar
"""

import os
import json
import pickle
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
CONFIG_DIR = Path.home() / '.meeting-transcriber'
GOOGLE_TOKEN_FILE = CONFIG_DIR / 'google_token.pickle'
GOOGLE_CREDS_FILE = CONFIG_DIR / 'google_credentials.json'
MS_TOKEN_FILE = CONFIG_DIR / 'ms_token.json'


class CalendarIntegration:
    def __init__(self, provider='google'):
        """
        Initialize calendar integration
        provider: 'google' or 'outlook'
        """
        self.provider = provider
        self.service = None

        CONFIG_DIR.mkdir(exist_ok=True)

    def authenticate_google(self):
        """Authenticate with Google Calendar"""
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

            creds = None

            # Load saved credentials
            if GOOGLE_TOKEN_FILE.exists():
                with open(GOOGLE_TOKEN_FILE, 'rb') as token:
                    creds = pickle.load(token)

            # If no valid credentials, authenticate
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not GOOGLE_CREDS_FILE.exists():
                        raise FileNotFoundError(
                            f"Google credentials file not found: {GOOGLE_CREDS_FILE}\n"
                            "Download from Google Cloud Console and save as google_credentials.json"
                        )

                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(GOOGLE_CREDS_FILE), SCOPES)
                    creds = flow.run_local_server(port=0)

                # Save credentials
                with open(GOOGLE_TOKEN_FILE, 'wb') as token:
                    pickle.dump(creds, token)

            self.service = build('calendar', 'v3', credentials=creds)
            return True

        except ImportError:
            print("Error: Google Calendar libraries not installed")
            print("Install with: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
            return False
        except Exception as e:
            print(f"Error authenticating with Google Calendar: {e}")
            return False

    def authenticate_microsoft(self):
        """Authenticate with Microsoft Graph (Outlook/Teams Calendar)"""
        try:
            import msal

            # Microsoft Graph API configuration
            CLIENT_ID = os.getenv('MS_CLIENT_ID')
            TENANT_ID = os.getenv('MS_TENANT_ID', 'common')
            SCOPES = ['Calendars.Read', 'Calendars.Read.Shared']

            if not CLIENT_ID:
                raise ValueError(
                    "MS_CLIENT_ID environment variable not set\n"
                    "Register app at: https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps"
                )

            # Load saved token
            token_cache = msal.SerializableTokenCache()
            if MS_TOKEN_FILE.exists():
                with open(MS_TOKEN_FILE, 'r') as f:
                    token_cache.deserialize(f.read())

            # Create MSAL app
            app = msal.PublicClientApplication(
                CLIENT_ID,
                authority=f"https://login.microsoftonline.com/{TENANT_ID}",
                token_cache=token_cache
            )

            # Try to get token from cache
            accounts = app.get_accounts()
            result = None

            if accounts:
                result = app.acquire_token_silent(SCOPES, account=accounts[0])

            # If no cached token, authenticate
            if not result:
                flow = app.initiate_device_flow(scopes=SCOPES)
                if "user_code" not in flow:
                    raise ValueError("Failed to create device flow")

                print("\n" + "=" * 60)
                print("Microsoft Calendar Authentication")
                print("=" * 60)
                print(flow["message"])
                print("=" * 60)

                result = app.acquire_token_by_device_flow(flow)

            if "access_token" in result:
                # Save token
                if token_cache.has_state_changed:
                    with open(MS_TOKEN_FILE, 'w') as f:
                        f.write(token_cache.serialize())

                self.service = {
                    'token': result['access_token'],
                    'app': app
                }
                return True
            else:
                print(f"Error: {result.get('error')}")
                print(f"Description: {result.get('error_description')}")
                return False

        except ImportError:
            print("Error: Microsoft Graph libraries not installed")
            print("Install with: pip install msal requests")
            return False
        except Exception as e:
            print(f"Error authenticating with Microsoft Calendar: {e}")
            return False

    def get_upcoming_meetings(self, hours=24):
        """
        Get upcoming meetings within the next X hours
        Returns list of meeting dict with: title, start_time, end_time, attendees
        """
        if self.provider == 'google':
            return self._get_google_meetings(hours)
        elif self.provider == 'outlook':
            return self._get_microsoft_meetings(hours)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    def _get_google_meetings(self, hours):
        """Get upcoming Google Calendar meetings"""
        if not self.service:
            if not self.authenticate_google():
                return []

        try:
            now = datetime.utcnow()
            time_min = now.isoformat() + 'Z'
            time_max = (now + timedelta(hours=hours)).isoformat() + 'Z'

            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            meetings = []
            for event in events:
                # Skip all-day events
                if 'dateTime' not in event['start']:
                    continue

                # Check if it's a Teams meeting
                is_teams = False
                if 'conferenceData' in event:
                    is_teams = True
                elif 'description' in event and 'teams.microsoft.com' in event.get('description', '').lower():
                    is_teams = True

                # Parse attendees
                attendees = []
                if 'attendees' in event:
                    attendees = [a.get('email', '') for a in event['attendees']]

                meetings.append({
                    'id': event['id'],
                    'title': event.get('summary', 'No title'),
                    'start_time': datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00')),
                    'end_time': datetime.fromisoformat(event['end']['dateTime'].replace('Z', '+00:00')),
                    'attendees': attendees,
                    'is_teams': is_teams,
                    'location': event.get('location', ''),
                    'description': event.get('description', '')
                })

            return meetings

        except Exception as e:
            print(f"Error getting Google Calendar meetings: {e}")
            return []

    def _get_microsoft_meetings(self, hours):
        """Get upcoming Microsoft Calendar meetings"""
        if not self.service:
            if not self.authenticate_microsoft():
                return []

        try:
            import requests

            now = datetime.utcnow()
            time_min = now.isoformat() + 'Z'
            time_max = (now + timedelta(hours=hours)).isoformat() + 'Z'

            headers = {
                'Authorization': f"Bearer {self.service['token']}",
                'Content-Type': 'application/json'
            }

            url = 'https://graph.microsoft.com/v1.0/me/calendarview'
            params = {
                'startDateTime': time_min,
                'endDateTime': time_max,
                '$orderby': 'start/dateTime',
                '$select': 'subject,start,end,attendees,location,onlineMeeting,body'
            }

            response = requests.get(url, headers=headers, params=params)

            if response.status_code != 200:
                print(f"Error: {response.status_code} - {response.text}")
                return []

            events = response.json().get('value', [])

            meetings = []
            for event in events:
                # Check if it's a Teams meeting
                is_teams = event.get('onlineMeeting') is not None

                # Parse attendees
                attendees = []
                if 'attendees' in event:
                    attendees = [a['emailAddress']['address'] for a in event['attendees']]

                meetings.append({
                    'id': event['id'],
                    'title': event.get('subject', 'No title'),
                    'start_time': datetime.fromisoformat(event['start']['dateTime']),
                    'end_time': datetime.fromisoformat(event['end']['dateTime']),
                    'attendees': attendees,
                    'is_teams': is_teams,
                    'location': event.get('location', {}).get('displayName', ''),
                    'description': event.get('body', {}).get('content', '')
                })

            return meetings

        except Exception as e:
            print(f"Error getting Microsoft Calendar meetings: {e}")
            return []

    def get_current_meeting(self):
        """
        Get currently happening meeting
        Returns meeting dict or None
        """
        meetings = self.get_upcoming_meetings(hours=1)

        now = datetime.now()

        for meeting in meetings:
            # Make timezone-aware comparison
            start_time = meeting['start_time'].replace(tzinfo=None) if meeting['start_time'].tzinfo else meeting['start_time']
            end_time = meeting['end_time'].replace(tzinfo=None) if meeting['end_time'].tzinfo else meeting['end_time']

            if start_time <= now <= end_time:
                return meeting

        return None

    def get_next_meeting(self):
        """
        Get the next upcoming meeting
        Returns meeting dict or None
        """
        meetings = self.get_upcoming_meetings(hours=24)

        now = datetime.now()

        for meeting in meetings:
            start_time = meeting['start_time'].replace(tzinfo=None) if meeting['start_time'].tzinfo else meeting['start_time']

            if start_time > now:
                return meeting

        return None


def main():
    """Test calendar integration"""
    import sys

    print("=" * 60)
    print("Calendar Integration Test")
    print("=" * 60)
    print()

    provider = sys.argv[1] if len(sys.argv) > 1 else 'google'

    print(f"Testing {provider} calendar...")
    print()

    calendar = CalendarIntegration(provider=provider)

    # Authenticate
    if provider == 'google':
        if not calendar.authenticate_google():
            print("Authentication failed!")
            return
    elif provider == 'outlook':
        if not calendar.authenticate_microsoft():
            print("Authentication failed!")
            return

    print("✅ Authentication successful!")
    print()

    # Get upcoming meetings
    print("Upcoming meetings (next 24 hours):")
    print("-" * 60)

    meetings = calendar.get_upcoming_meetings(hours=24)

    if not meetings:
        print("No meetings found")
    else:
        for meeting in meetings:
            print(f"\n📅 {meeting['title']}")
            print(f"   Time: {meeting['start_time'].strftime('%I:%M %p')} - {meeting['end_time'].strftime('%I:%M %p')}")
            print(f"   Teams: {'Yes' if meeting['is_teams'] else 'No'}")
            if meeting['attendees']:
                print(f"   Attendees: {len(meeting['attendees'])} people")

    print("\n" + "=" * 60)

    # Get current meeting
    current = calendar.get_current_meeting()
    if current:
        print(f"\n⏰ Currently in meeting: {current['title']}")
    else:
        print(f"\n⏰ No current meeting")

    # Get next meeting
    next_meeting = calendar.get_next_meeting()
    if next_meeting:
        time_until = (next_meeting['start_time'].replace(tzinfo=None) - datetime.now()).total_seconds() / 60
        print(f"⏰ Next meeting in {int(time_until)} minutes: {next_meeting['title']}")
    else:
        print("⏰ No upcoming meetings")


if __name__ == '__main__':
    main()
