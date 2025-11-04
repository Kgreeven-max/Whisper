# 🚀 Quick Start - Cannot Fail Guide

**Follow these exact steps - nothing else needed!**

---

## Step 1: On Your VPS

```bash
cd /opt
git clone https://github.com/Kgreeven-max/Whisper.git meeting-transcriber
cd meeting-transcriber
git checkout claude/notion-meeting-transcriber-vps-011CUnFKEU8KLtfhEMdsKMdG
```

---

## Step 2: Generate Passwords

Run these commands and **save the output**:

```bash
# Generate password (copy this output)
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate secret key (copy this output)
python3 -c "import secrets; print(secrets.token_hex(32))"
```

You'll see two random strings - **copy both**!

---

## Step 3: Create Config File

```bash
cp .env.example .env
nano .env
```

**In the nano editor:**

1. Find the line: `POSTGRES_PASSWORD=REPLACE_WITH_SECURE_PASSWORD`
2. Replace `REPLACE_WITH_SECURE_PASSWORD` with the **first** output you copied
3. Find the line: `SECRET_KEY=REPLACE_WITH_SECURE_SECRET_KEY`
4. Replace `REPLACE_WITH_SECURE_SECRET_KEY` with the **second** output you copied
5. Press `Ctrl+X`, then `Y`, then `Enter` to save

**Example of what it should look like:**
```bash
POSTGRES_PASSWORD=xK9mP2nR8vL4hT6qW1zN3bV5cX7yF0jS
SECRET_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6
```

---

## Step 4: Deploy

```bash
./deploy.sh
```

**That's it!**

The script will:
- Check your passwords are set ✓
- Install Docker if needed ✓
- Start all services ✓
- Pull AI model ✓

Takes 5-10 minutes.

---

## Step 5: Access

Open browser:
```
http://your-vps-ip:8080
```

**Done!** 🎉

---

## Quick Test

Upload a short audio file (1-2 minutes) to test it works!

---

## Troubleshooting

**"ERROR: .env file not found"**
- You skipped Step 3. Go back and create `.env` file.

**"ERROR: .env file contains placeholder values"**
- You didn't replace the passwords. Edit `.env` again:
  ```bash
  nano .env
  ```

**"Cannot connect to Docker"**
- Log out and log back in after Docker installs:
  ```bash
  exit
  ```
  Then SSH back in and run `./deploy.sh` again

**Services not starting**
- Check logs:
  ```bash
  docker-compose logs
  ```

**Still stuck?**
- Check PRODUCTION_CHECKLIST.md
- Check TESTING.md

---

## That's Really It!

No complicated steps. No placeholders to figure out. Just:

1. Clone repo
2. Generate passwords
3. Put passwords in `.env`
4. Run `./deploy.sh`
5. Open browser

**5 steps. Cannot fail.** ✓
