"""
main.py - Shazam Taste Filter

Orchestrates the full pipeline:
  1. Read any like/dislike feedback from Gmail
  2. Fetch new Shazam songs since last run
  3. Cross-reference against YouTube Music playlists (remove duplicates)
  4. Score remaining songs against full taste profile using Groq 70B
  5. Email digest with like/dislike buttons for future learning

Flags:
  --dry-run     Run the full pipeline but print results instead of sending email
  --debug       Verbose logging for every step
  --limit N     Only process the N most recent Shazam songs (for quick testing)
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

from shazam_fetcher import get_shazam_library, get_recent_shazam_taste, filter_songs_since
from ytmusic_handler import (
    build_ytmusic,
    get_all_playlist_tracks,
    get_history,
    is_in_playlist,
    build_taste_profile,
)
from scorer import build_gemini_client, build_taste_summary, score_songs_batch
from email_sender import send_digest
from feedback_handler import fetch_and_process_feedback, load_feedback

STATE_FILE = Path(__file__).parent.parent / "state.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_run": ""}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_config() -> dict:
    missing = []
    config  = {}

    required = {
        "FIREBASE_API_KEY":       "Shazam's Firebase API key",
        "FIREBASE_REFRESH_TOKEN": "Firebase refresh token",
        "FIREBASE_USER_ID":       "Your Firebase user ID",
        "FIREBASE_PROJECT":       "Firebase project ID",
        "YTMUSIC_HEADERS":        "YouTube Music browser headers JSON",
        "PLAYLIST_IDS":           "Comma-separated YouTube Music playlist IDs",
        "GEMINI_API_KEY":          "Gemini API key from aistudio.google.com/app/apikey (free)",
        "GMAIL_ADDRESS":          "Your Gmail address",
        "GMAIL_APP_PASSWORD":     "Gmail App Password",
    }

    for key, description in required.items():
        val = os.getenv(key, "").strip()
        if not val:
            missing.append(f"  {key} - {description}")
        else:
            config[key] = val

    if missing:
        print("\n[Config] Missing environment variables:\n")
        print("\n".join(missing))
        print("\nCopy .env.example to .env and fill in all values.")
        sys.exit(1)

    config["SCORE_THRESHOLD"] = int(os.getenv("SCORE_THRESHOLD", "5"))
    config["TO_EMAIL"]        = os.getenv("TO_EMAIL", config["GMAIL_ADDRESS"])

    return config


def run(dry_run: bool = False, debug: bool = False, limit: int = None) -> None:
    load_dotenv()
    config = load_config()
    state  = load_state()

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Shazam Taste Filter - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # --- Step 0: Load feedback from Gmail ---
    print("\n[0/5] Loading feedback from previous digests...")
    groq_client = build_gemini_client(config["GEMINI_API_KEY"])
    try:
        feedback = fetch_and_process_feedback(
            gmail_address=config["GMAIL_ADDRESS"],
            app_password=config["GMAIL_APP_PASSWORD"],
            groq_client=groq_client,
            debug=debug,
        )
        liked_count = len(feedback.get("liked_songs", []))
        disliked_count = len(feedback.get("disliked_songs", []))
        print(f"      Feedback loaded: {liked_count} liked, {disliked_count} disliked songs")
    except Exception as e:
        print(f"      WARNING: Could not load feedback: {e} (non-fatal)")
        feedback = load_feedback()

    # --- Step 1: Fetch Shazam library ---
    last_run = state.get("last_run", "")
    print("\n[1/5] Fetching Shazam library...")
    print(f"      Last run: {last_run or 'never'}")
    new_songs = get_shazam_library(
        api_key=config["FIREBASE_API_KEY"],
        refresh_token=config["FIREBASE_REFRESH_TOKEN"],
        user_id=config["FIREBASE_USER_ID"],
        project=config["FIREBASE_PROJECT"],
        since_iso=last_run,
        limit=limit,
        debug=debug,
    )
    print(f"      {len(new_songs)} new song(s) to process{f' (limit={limit})' if limit else ''}")

    print("      Fetching recent Auto-Shazam taste signal (last year)...")
    try:
        recent_shazam_songs = get_recent_shazam_taste(
            api_key=config["FIREBASE_API_KEY"],
            refresh_token=config["FIREBASE_REFRESH_TOKEN"],
            user_id=config["FIREBASE_USER_ID"],
            project=config["FIREBASE_PROJECT"],
            days=365,
            limit=50,
            debug=debug,
        )
        print(f"      Recent taste: {len(recent_shazam_songs)} Auto-Shazam songs")
    except Exception as e:
        print(f"      WARNING: Could not fetch recent taste: {e} (non-fatal)")
        recent_shazam_songs = []

    if not new_songs:
        print("\n      Nothing new to process. Done.")
        return

    # --- Step 2: Load YouTube Music data ---
    print("\n[2/5] Loading YouTube Music data...")
    ytm = build_ytmusic(config["YTMUSIC_HEADERS"])

    playlist_ids = [p.strip() for p in config["PLAYLIST_IDS"].split(",") if p.strip()]
    print(f"      Fetching {len(playlist_ids)} playlist(s)...")
    all_playlist_tracks = get_all_playlist_tracks(ytm, playlist_ids, debug=debug)
    print(f"      Combined playlists: {len(all_playlist_tracks)} unique songs")

    print("      Fetching listening history...")
    try:
        history_tracks = get_history(ytm, debug=debug)
        print(f"      History: {len(history_tracks)} items")
    except Exception as e:
        print(f"      WARNING: Could not fetch history: {e} (non-fatal)")
        history_tracks = []

    # --- Step 3: Cross-reference (remove duplicates) ---
    print("\n[3/5] Cross-referencing against your playlists...")
    unique_songs    = []
    duplicate_count = 0

    for song in new_songs:
        if is_in_playlist(song["title"], song["artist"], all_playlist_tracks):
            if debug:
                print(f"      [DUPE] {song['title']} by {song['artist']}")
            duplicate_count += 1
        else:
            unique_songs.append(song)

    print(f"      {duplicate_count} duplicates removed, {len(unique_songs)} songs to score")

    if not unique_songs:
        print("\n      All new Shazam songs are already in your playlist. Done.")
        return

    # --- Step 4: AI scoring ---
    print(f"\n[4/5] Scoring {len(unique_songs)} songs with Gemini 2.5 Flash...")
    print(f"      Building taste profile from {len(all_playlist_tracks)} playlist songs...")
    taste_profile = build_taste_profile(all_playlist_tracks, history_tracks, recent_shazam_songs)
    taste_summary = build_taste_summary(taste_profile, feedback=feedback)

    if debug:
        token_estimate = len(taste_summary) // 3
        print(f"      Taste summary: ~{token_estimate:,} tokens")

    all_scored = score_songs_batch(
        groq_client,
        unique_songs,
        taste_summary,
        min_score=config["SCORE_THRESHOLD"],
        debug=debug,
    )

    worthy  = [s for s in all_scored if s["score"] >= config["SCORE_THRESHOLD"]]
    skipped = [s for s in all_scored if s["score"] <  config["SCORE_THRESHOLD"]]

    print(f"      {len(worthy)} recommended | {len(skipped)} below threshold")

    # --- Step 5: Send email (or print if dry run) ---
    if dry_run:
        print("\n[5/5] DRY RUN - would send this email:")
        print("\n  WORTH YOUR TIME:")
        print("-" * 60)
        if not worthy:
            print("  None tonight.")
        for s in worthy:
            b = s.get("breakdown", {})
            print(f"  {s['score']}/10 | {s['title']} by {s['artist']}")
            print(f"         Genre:     {s['genre']}")
            print(f"         Breakdown: artist={b.get('artist_affinity')}/3 "
                  f"vibe={b.get('vibe_match')}/3 quality={b.get('track_quality')}/2 "
                  f"discovery={b.get('discovery_fit')}/2")
            print(f"         Why:       {s['reasoning']}")
            print(f"         Link:      {s['yt_search_link']}")
            print()
        print("\n  NOT WORTH IT:")
        print("-" * 60)
        for s in skipped:
            print(f"  {s['score']}/10 | {s['title']} by {s['artist']}")
    else:
        print(f"\n[5/5] Sending email digest to {config['TO_EMAIL']}...")
        send_digest(
            gmail_address=config["GMAIL_ADDRESS"],
            gmail_app_password=config["GMAIL_APP_PASSWORD"],
            to_address=config["TO_EMAIL"],
            scored_songs=worthy,
            skipped_songs=skipped,
            all_processed_count=len(new_songs),
            duplicate_count=duplicate_count,
            score_threshold=config["SCORE_THRESHOLD"],
            debug=debug,
        )
        print("      Email sent.")

    # --- Update state ---
    if not dry_run:
        state["last_run"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        print(f"\n      State updated. Next run will only process songs after {state['last_run']}")

    print("\nDone.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Shazam Taste Filter")
    parser.add_argument("--dry-run", action="store_true", help="Print results instead of sending email")
    parser.add_argument("--debug",   action="store_true", help="Verbose output")
    parser.add_argument("--limit",   type=int, default=None, help="Only process N most recent songs")
    args = parser.parse_args()

    run(dry_run=args.dry_run, debug=args.debug, limit=args.limit)
