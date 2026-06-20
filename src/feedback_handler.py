"""
feedback_handler.py

Manages the feedback loop - reads user likes/dislikes from Gmail and
stores them in feedback.json for use in future scoring runs.

Two feedback channels:
  1. Like/Dislike buttons in the email digest (mailto links)
     Subject format: "SHAZAM-FEEDBACK: Song Title by Artist | LIKE"
     Subject format: "SHAZAM-FEEDBACK: Song Title by Artist | DISLIKE"

  2. Reply to the digest email with free-text review
     The script reads replies and passes them to the AI to extract
     structured feedback.

feedback.json structure:
  {
    "liked_songs":    ["Wavy by Karan Aujla", ...],
    "disliked_songs": ["Panwadi by Khesari Lal Yadav", ...],
    "artist_boosts":  {"Karan Aujla": 3, "Khesari Lal Yadav": -1}
  }
"""

import imaplib
import email
import json
import os
import re
from email.header import decode_header
from pathlib import Path

FEEDBACK_FILE = Path(__file__).parent.parent / "feedback.json"
IMAP_SERVER   = "imap.gmail.com"
IMAP_PORT     = 993
DIGEST_SUBJECT_PREFIX = "Shazam Nightly Digest"


# --- Load / Save ---

def load_feedback() -> dict:
    if FEEDBACK_FILE.exists():
        try:
            return json.loads(FEEDBACK_FILE.read_text())
        except Exception:
            pass
    return {"liked_songs": [], "disliked_songs": [], "artist_boosts": {}}


def save_feedback(feedback: dict) -> None:
    FEEDBACK_FILE.write_text(json.dumps(feedback, indent=2, ensure_ascii=False))


# --- IMAP reading ---

def fetch_and_process_feedback(
    gmail_address: str,
    app_password: str,
    groq_client=None,
    debug: bool = False,
) -> dict:
    """
    Connect to Gmail via IMAP, read feedback emails, update and return
    the feedback dict. Marks processed emails as read so they aren't
    processed again.
    """
    feedback = load_feedback()

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(gmail_address, app_password)
        mail.select("inbox")
    except Exception as e:
        print(f"[Feedback] Could not connect to Gmail IMAP: {e}")
        return feedback

    new_likes    = 0
    new_dislikes = 0
    new_replies  = 0

    # --- Process SHAZAM-FEEDBACK button emails ---
    try:
        _, msg_ids = mail.search(None, '(UNSEEN SUBJECT "SHAZAM-FEEDBACK:")')
        ids = msg_ids[0].split() if msg_ids[0] else []

        for mid in ids:
            _, data = mail.fetch(mid, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            subject = _decode_header_value(msg.get("Subject", ""))

            result = _parse_feedback_subject(subject)
            if result:
                song_str, action = result
                artist = _extract_artist_from_song_str(song_str)

                if action == "LIKE":
                    if song_str not in feedback["liked_songs"]:
                        feedback["liked_songs"].append(song_str)
                    if song_str in feedback["disliked_songs"]:
                        feedback["disliked_songs"].remove(song_str)
                    if artist:
                        feedback["artist_boosts"][artist] = feedback["artist_boosts"].get(artist, 0) + 1
                    new_likes += 1

                elif action == "DISLIKE":
                    if song_str not in feedback["disliked_songs"]:
                        feedback["disliked_songs"].append(song_str)
                    if song_str in feedback["liked_songs"]:
                        feedback["liked_songs"].remove(song_str)
                    if artist:
                        feedback["artist_boosts"][artist] = feedback["artist_boosts"].get(artist, 0) - 1
                    new_dislikes += 1

                # Mark as read so we don't reprocess
                mail.store(mid, "+FLAGS", "\\Seen")

                if debug:
                    print(f"[Feedback] {action}: {song_str}")

    except Exception as e:
        print(f"[Feedback] Error reading button feedback: {e}")

    # --- Process digest reply emails ---
    if groq_client:
        try:
            _, msg_ids = mail.search(
                None,
                f'(UNSEEN SUBJECT "Re: {DIGEST_SUBJECT_PREFIX}")'
            )
            ids = msg_ids[0].split() if msg_ids[0] else []

            for mid in ids:
                _, data = mail.fetch(mid, "(RFC822)")
                msg     = email.message_from_bytes(data[0][1])
                body    = _extract_email_body(msg)

                if body and len(body.strip()) > 10:
                    parsed = _parse_reply_with_ai(groq_client, body, feedback, debug=debug)
                    if parsed:
                        feedback = _merge_reply_feedback(feedback, parsed)
                        new_replies += 1

                mail.store(mid, "+FLAGS", "\\Seen")

        except Exception as e:
            print(f"[Feedback] Error reading reply emails: {e}")

    mail.logout()

    if new_likes or new_dislikes or new_replies:
        save_feedback(feedback)
        print(f"[Feedback] Processed: {new_likes} likes, {new_dislikes} dislikes, {new_replies} reply reviews")
    else:
        if debug:
            print("[Feedback] No new feedback emails found")

    return feedback


# --- AI reply parsing ---

def _parse_reply_with_ai(gemini_model, body: str, existing_feedback: dict, debug: bool = False) -> dict:
    """
    Use Gemini to extract structured feedback from a free-text reply email.
    Returns dict with liked_songs, disliked_songs, artist_boosts or None on failure.
    """
    prompt = f"""The user sent this reply reviewing songs from their Shazam digest email.
Extract their feedback as structured data.

USER'S REPLY:
{body[:2000]}

Extract and respond in this EXACT JSON format (no extra text):
{{
  "liked_songs": ["Song Title by Artist", ...],
  "disliked_songs": ["Song Title by Artist", ...],
  "liked_artists": ["Artist Name", ...],
  "disliked_artists": ["Artist Name", ...]
}}

Only include songs/artists explicitly mentioned with positive or negative sentiment.
If unclear, omit. Return empty lists if nothing clear was found."""

    try:
        from google.genai import types as genai_types
        response = gemini_model.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=500,
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = response.text.strip()
        # Extract JSON block
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        if debug:
            print(f"[Feedback] AI reply parsing failed: {e}")
    return None


def _merge_reply_feedback(feedback: dict, parsed: dict) -> dict:
    for song in parsed.get("liked_songs", []):
        if song and song not in feedback["liked_songs"]:
            feedback["liked_songs"].append(song)
        if song in feedback["disliked_songs"]:
            feedback["disliked_songs"].remove(song)

    for song in parsed.get("disliked_songs", []):
        if song and song not in feedback["disliked_songs"]:
            feedback["disliked_songs"].append(song)
        if song in feedback["liked_songs"]:
            feedback["liked_songs"].remove(song)

    for artist in parsed.get("liked_artists", []):
        if artist:
            feedback["artist_boosts"][artist] = feedback["artist_boosts"].get(artist, 0) + 1

    for artist in parsed.get("disliked_artists", []):
        if artist:
            feedback["artist_boosts"][artist] = feedback["artist_boosts"].get(artist, 0) - 1

    return feedback


# --- helpers ---

def _parse_feedback_subject(subject: str):
    """
    Parse 'SHAZAM-FEEDBACK: Wavy by Karan Aujla | LIKE' ->
    ('Wavy by Karan Aujla', 'LIKE')
    """
    match = re.match(r"SHAZAM-FEEDBACK:\s*(.+?)\s*\|\s*(LIKE|DISLIKE)", subject, re.IGNORECASE)
    if match:
        return match.group(1).strip(), match.group(2).upper()
    return None


def _extract_artist_from_song_str(song_str: str) -> str:
    """Extract artist from 'Song Title by Artist'"""
    parts = song_str.split(" by ", 1)
    return parts[1].strip() if len(parts) == 2 else ""


def _decode_header_value(value: str) -> str:
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _extract_email_body(msg) -> str:
    """Extract plain text body from an email message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body += payload.decode("utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode("utf-8", errors="replace")
    # Strip quoted reply content (lines starting with >)
    lines = [l for l in body.splitlines() if not l.startswith(">")]
    return "\n".join(lines).strip()
