# Shazam Taste Filter - Setup Guide

Work through these steps in order. Each step has a test script so you
can confirm it works before moving on.

---

## Prerequisites

You need Python 3.11+ installed on your laptop for the testing phase.
Check with: `python3 --version`

Install dependencies once:
```bash
cd "Shazam AI"
pip3 install -r requirements.txt
```

Copy the config template:
```bash
cp .env.example .env
```

---

## Step 1 - Get your Shazam cookies

These let the script read your Shazam library without logging in every time.

1. Open **https://www.shazam.com** in Chrome
2. Log in with your account (Apple ID or Google)
3. Go to **https://www.shazam.com/myshazam** - you should see your song history
4. Press **F12** to open DevTools
5. Go to the **Network** tab
6. Refresh the page (Cmd+R / Ctrl+R)
7. In the Network tab, click on the first request to **www.shazam.com**
8. In the right panel, scroll to **Request Headers**
9. Find the line that says **cookie:** and copy the entire value (it's long)
10. Paste it in `.env` as: `SHAZAM_COOKIES=<paste here>`

**Test it:**
```bash
python3 tests/step1_test_shazam.py
```
Expected output: your 5 most recent Shazam songs printed in the terminal.

**Cookie lifespan:** Shazam cookies typically last 3-6 months. When they expire,
the script will print a clear error and you re-do this step (5 minutes).

---

## Step 2 - Set up YouTube Music

1. Open **https://music.youtube.com** in Chrome (make sure you're logged in)
2. Press **F12** -> **Network** tab
3. Play any song (click on a track)
4. In the Network tab, look for a request to `music.youtube.com`
5. Right-click it -> **Copy** -> **Copy as cURL**
6. In your terminal, run:
   ```bash
   ytmusicapi browser
   ```
   Paste the cURL string when prompted. Press Enter twice when done.
   It will print a JSON object - copy the entire output.
7. Paste it in `.env` as: `YTMUSIC_HEADERS=<paste the JSON here>`
   (keep it on one line)

**Find your playlist IDs:**
- Open the playlist on music.youtube.com
- The URL looks like: `https://music.youtube.com/playlist?list=PLxxxxxxxxxxxxxx`
- The ID is everything after `list=` (e.g. `PLxxxxxxxxxxxxxx`)
- Put your duplicate-check playlist ID in `CHECK_PLAYLIST_ID`
- Put your taste reference playlist ID in `TASTE_PLAYLIST_ID`

**Test it:**
```bash
python3 tests/step2_test_ytmusic.py
```
Expected output: songs from both playlists + your top artists by play count.

---

## Step 3 - Get a Gemini API key (free)

1. Go to **https://aistudio.google.com/app/apikey**
2. Sign in with your Google account
3. Click **Create API key**
4. Copy the key and paste in `.env` as: `GEMINI_API_KEY=<paste here>`

Free tier is 15 requests/minute and 1 million tokens/day - more than enough.

**Test it:**
```bash
python3 tests/step3_test_scorer.py
```
Expected output: 5 test songs scored with reasons. House/desi hip-hop should score higher than folk/ballads.

---

## Step 4 - Set up Gmail

1. Make sure **2-Step Verification** is on for your Google account
   (required for App Passwords): https://myaccount.google.com/security
2. Go to **https://myaccount.google.com/apppasswords**
3. Select app: **Mail** | Select device: **Other** -> type "Shazam Filter"
4. Click **Generate**
5. Copy the 16-character password (no spaces)
6. In `.env`:
   ```
   GMAIL_ADDRESS=youremail@gmail.com
   GMAIL_APP_PASSWORD=abcdabcdabcdabcd
   ```

**Test it:**
```bash
python3 tests/step4_test_email.py
```
Expected output: a formatted HTML email arrives in your inbox with 3 fake test songs.

---

## Step 5 - Full dry run

With all 4 pieces working, do a complete end-to-end test against your real data:

```bash
python3 tests/step5_full_dry_run.py
```

This runs the full pipeline - fetches your real Shazam songs, cross-references your
real playlists, scores with Gemini - but prints to terminal instead of sending email.

Try with fewer songs first:
```bash
python3 tests/step5_full_dry_run.py --limit 5
```

**If the scores look right:** tell Claude you're happy and ready to deploy.
**If scores seem off:** adjust `SCORE_THRESHOLD` in `.env` (try 7 for stricter filtering).

---

## Step 6 - Production deployment (GitHub Actions)

**Only do this after Step 5 looks good.**

Tell Claude "I'm happy with the dry run, let's deploy to GitHub Actions."

Claude will give you the final deployment steps which involve:
- Creating a private GitHub repo
- Adding your `.env` values as GitHub Secrets
- Uploading the code
- Enabling the nightly cron schedule

The script will then run automatically every night at a time you choose,
and email you only when there are new songs to report.

---

## Troubleshooting

**Shazam returns 0 songs**
Check you're logged into shazam.com with the same account linked to your Samsung.
The cookies must come from a logged-in session.

**ytmusicapi auth error**
Your YouTube Music headers may have expired (they last ~3 months).
Re-run the browser header capture from Step 2.

**Gemini quota exceeded**
You're unlikely to hit this on the free tier. If you do, add a delay:
set `GEMINI_DELAY=3` in your `.env` (3 seconds between requests).

**Gmail authentication failed**
Make sure you're using the App Password, NOT your Gmail password.
Regular passwords don't work with SMTP anymore.
