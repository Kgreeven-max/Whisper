# Google Calendar Integration Setup - Notion-Style Auto-Record

This guide shows you how to enable **automatic meeting detection and recording prompts** - just like Notion!

---

## 🎯 What You'll Get

Once set up, your users will:
1. Get a **browser notification** 5 minutes before a meeting starts
2. See a beautiful **Notion-style prompt**: "Meeting Starting Soon - Record This Meeting?"
3. Click **one button** to start recording
4. Meeting title automatically filled from calendar
5. Recording auto-uploads and transcribes when done

**Exactly like Notion's recording experience!**

---

## 📋 Prerequisites

- Google Account
- Access to Google Cloud Console
- Your VPS public IP or domain name

---

## 🚀 Step-by-Step Setup

### Step 1: Create Google Cloud Project

1. Go to **[Google Cloud Console](https://console.cloud.google.com/)**

2. Click **"Select a project"** → **"New Project"**

3. Enter project details:
   - **Project name**: "Meeting Transcriber" (or your choice)
   - **Location**: No organization (or your organization)
   - Click **"Create"**

4. Wait for project creation (10-20 seconds)

5. Select your new project from the dropdown

---

### Step 2: Enable Google Calendar API

1. In Google Cloud Console, click **☰ Menu** → **"APIs & Services"** → **"Library"**

2. Search for **"Google Calendar API"**

3. Click **"Google Calendar API"**

4. Click **"Enable"** button

5. Wait for enablement (5-10 seconds)

---

### Step 3: Configure OAuth Consent Screen

1. Click **☰ Menu** → **"APIs & Services"** → **"OAuth consent screen"**

2. Choose **"External"** (unless you have Google Workspace)

3. Click **"Create"**

4. Fill in App Information:
   - **App name**: Meeting Transcriber
   - **User support email**: your-email@gmail.com
   - **App logo**: (optional, skip for now)
   - **Application home page**: http://your-vps-ip:8080
   - **Authorized domains**: (leave empty for now, or add your domain)
   - **Developer contact information**: your-email@gmail.com

5. Click **"Save and Continue"**

6. **Scopes** page:
   - Click **"Add or Remove Scopes"**
   - Search and select: `https://www.googleapis.com/auth/calendar.readonly`
   - Click **"Update"**
   - Click **"Save and Continue"**

7. **Test users** page:
   - Click **"Add Users"**
   - Enter email addresses of users who can test (max 100)
   - Add your own email and any other test users
   - Click **"Add"**
   - Click **"Save and Continue"**

8. Click **"Back to Dashboard"**

---

### Step 4: Create OAuth Credentials

1. Click **☰ Menu** → **"APIs & Services"** → **"Credentials"**

2. Click **"+ Create Credentials"** → **"OAuth client ID"**

3. Choose **Application type**: **"Web application"**

4. Fill in details:
   - **Name**: Meeting Transcriber Web App

   - **Authorized JavaScript origins**:
     ```
     http://localhost:8080
     http://your-vps-ip:8080
     ```
     (Add your domain if you have one)

   - **Authorized redirect URIs**:
     ```
     http://localhost:8080/api/calendar/callback
     http://your-vps-ip:8080/api/calendar/callback
     ```
     (Replace `your-vps-ip` with actual IP or domain)

5. Click **"Create"**

6. **Important**: Copy the credentials shown:
   - **Client ID**: Looks like `123456789-abcdefg.apps.googleusercontent.com`
   - **Client Secret**: Looks like `GOCSPX-abcdefghij...`

   **Save these! You'll need them in Step 5.**

---

### Step 5: Add Credentials to Your Application

1. SSH into your VPS:
   ```bash
   ssh your-vps
   cd Whisper
   ```

2. Edit `.env` file:
   ```bash
   nano .env
   ```

3. Add these lines (use your actual credentials):
   ```bash
   # Google Calendar Integration
   GOOGLE_CLIENT_ID=123456789-abcdefg.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-abcdefghijklmnop
   APP_URL=http://your-vps-ip:8080
   ```

   **Replace:**
   - `GOOGLE_CLIENT_ID` with your actual Client ID
   - `GOOGLE_CLIENT_SECRET` with your actual Client Secret
   - `APP_URL` with your actual VPS IP or domain

4. Save and exit (Ctrl+X, then Y, then Enter)

5. Restart the application:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

6. Check logs to verify:
   ```bash
   docker-compose logs -f web
   ```

---

### Step 6: Connect Calendar (User Side)

1. Open your browser and go to: `http://your-vps-ip:8080`

2. Login to your account

3. Navigate to **Settings** (⚙️ in sidebar)

4. Scroll to **"Calendar Integration"** section

5. Click **"📅 Connect Google Calendar"** button

6. OAuth popup opens:
   - Sign in with Google
   - Choose your Google account
   - Click **"Allow"** to grant calendar access

7. Popup closes, you see **"✓ Calendar Connected"**

8. Done! You'll now get prompts when meetings start.

---

## ✅ Testing

### Test the Integration:

1. **Create a test calendar event**:
   - Go to [Google Calendar](https://calendar.google.com)
   - Create an event starting in 5-10 minutes
   - Give it a title like "Test Meeting"

2. **Wait for the prompt**:
   - Leave your browser tab open
   - 5 minutes before meeting start, you'll see:
     - Browser notification (if allowed)
     - Notion-style prompt modal

3. **Click "Record This Meeting"**:
   - Redirects to `/live` page
   - Meeting title pre-filled
   - Click "Start Recording"
   - Speak into microphone
   - Click "Stop"
   - Auto-uploads and processes

---

## 🎨 How It Works

### Backend Flow:

```
1. User clicks "Connect Calendar" in Settings
2. Backend generates OAuth URL → Redirects to Google
3. User authorizes → Google redirects back with code
4. Backend exchanges code for access/refresh tokens
5. Tokens stored in database (encrypted in production)
6. Every minute: Check for meetings starting in 5 min
7. If found: Return to frontend → Show prompt
```

### Frontend Flow:

```
1. Every 60 seconds: Call /api/calendar/check-meetings
2. If meetings found:
   a. Show browser notification
   b. Show Notion-style modal prompt
   c. User clicks "Record This Meeting"
   d. Navigate to /live?auto=true&title=Meeting+Title
3. Recording starts, auto-uploads when done
```

### Database Tables:

```sql
-- Stores OAuth tokens per user
calendar_tokens (
  user_id → UNIQUE
  access_token
  refresh_token
  token_expiry
)

-- Tracks which events we've prompted for
calendar_events_prompted (
  user_id, event_id → UNIQUE
  prompted_at
  recording_started
)
```

---

## 🔒 Security Notes

### Token Storage:
- Tokens stored in PostgreSQL
- **Production**: Use encryption (add `pgcrypto` extension)
- Each user has isolated tokens
- Tokens auto-refresh when expired

### OAuth Scopes:
- We only request **`calendar.readonly`**
- Can't create/edit/delete calendar events
- Only reads upcoming events
- Minimal permissions = safer

### Privacy:
- Event details only shown to user who connected
- Event IDs hashed before storage (optional enhancement)
- User can disconnect anytime
- Deleting account deletes all tokens

---

## 🐛 Troubleshooting

### "Google Calendar not configured" error:

**Problem**: `GOOGLE_CLIENT_ID` not set in `.env`

**Solution**:
```bash
# Check if variables are set
docker exec meeting-web printenv | grep GOOGLE

# If empty, add to .env and restart
nano .env
# Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET
docker-compose restart web
```

---

### OAuth redirect mismatch error:

**Problem**: Redirect URI doesn't match Google Cloud Console

**Solution**:
1. Check your `.env` APP_URL matches your actual URL
2. Go to Google Cloud Console → Credentials
3. Edit OAuth client
4. Add the exact redirect URI: `http://your-vps-ip:8080/api/calendar/callback`
5. Save changes (takes 5 minutes to propagate)

---

### "Calendar check" errors in logs:

**Problem**: Token expired or invalid

**Solution**:
```bash
# Check logs
docker-compose logs -f web | grep -i calendar

# If token expired, user needs to reconnect:
# 1. Go to Settings
# 2. Click "Disconnect Calendar"
# 3. Click "Connect Google Calendar" again
```

---

### No prompts showing:

**Problem 1**: Browser notifications blocked

**Solution**: Allow notifications in browser settings

**Problem 2**: Calendar not connected

**Solution**: Check Settings → Calendar Integration → Should show "✓ Calendar Connected"

**Problem 3**: No meetings in calendar

**Solution**: Create a test event starting in 5-10 minutes

---

## 📊 Monitoring

### Check calendar connections:

```sql
-- Connect to database
docker exec -it meeting-postgres psql -U meeting_user -d meetings

-- See connected users
SELECT u.username, ct.created_at, ct.token_expiry
FROM calendar_tokens ct
JOIN users u ON u.id = ct.user_id;

-- See prompted events today
SELECT u.username, cep.event_start, cep.recording_started
FROM calendar_events_prompted cep
JOIN users u ON u.id = cep.user_id
WHERE cep.prompted_at > CURRENT_DATE
ORDER BY cep.event_start DESC;
```

### Check API logs:

```bash
# See calendar API calls
docker-compose logs -f web | grep -i calendar

# Should see every minute:
# "Calendar check: ..." (if calendar not connected, or no meetings)
# "Calendar check error: ..." (if error)
```

---

## 🚀 Production Enhancements

For production deployment, consider:

### 1. Token Encryption:
```sql
-- Enable pgcrypto extension
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Encrypt tokens before storing
INSERT INTO calendar_tokens (user_id, access_token)
VALUES (1, pgp_sym_encrypt('token_value', 'encryption_key'));

-- Decrypt when reading
SELECT pgp_sym_decrypt(access_token::bytea, 'encryption_key')
FROM calendar_tokens WHERE user_id = 1;
```

### 2. HTTPS Setup:
- Get SSL certificate (Let's Encrypt)
- Update APP_URL to https://
- Update OAuth redirect URIs to https://

### 3. Publish OAuth App:
- Google Cloud Console → OAuth consent screen
- Click "Publish App"
- Submit for verification (1-2 weeks)
- Allows unlimited users (not just 100 test users)

### 4. Rate Limiting:
```python
# In app.py - add rate limiting
from flask_limiter import Limiter

limiter = Limiter(app, key_func=lambda: request.remote_addr)

@app.route('/api/calendar/check-meetings')
@limiter.limit("10 per minute")  # Prevent abuse
@jwt_required
def calendar_check_meetings():
    # ...
```

---

## 🎉 Summary

You now have **Notion-style automatic meeting detection**:

✅ Users connect Google Calendar in Settings
✅ System checks for meetings every minute
✅ 5 minutes before meeting: Beautiful prompt appears
✅ One-click to start recording
✅ Meeting title auto-filled
✅ Recording auto-uploads and processes

**Users will say: "Wow, this is just like Notion!"** 🎉

---

## 📝 Next Steps

1. **Complete Google Cloud Console setup** (Steps 1-4)
2. **Add credentials to .env** (Step 5)
3. **Restart application**
4. **Test with users** (Step 6)
5. **Monitor logs** for any issues
6. **Consider production enhancements** (encryption, HTTPS, publish app)

---

## 🔗 Useful Links

- [Google Cloud Console](https://console.cloud.google.com/)
- [Google Calendar API Docs](https://developers.google.com/calendar)
- [OAuth 2.0 Guide](https://developers.google.com/identity/protocols/oauth2)
- [Issue Tracker](https://github.com/your-repo/issues)

---

**Need help? Check the troubleshooting section above or open an issue!**
