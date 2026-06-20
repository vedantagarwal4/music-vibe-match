"""
STEP 2 - Test YouTube Music Connection
========================================
Run this to confirm ytmusicapi can read your playlists and history.

What it does:
  - Connects to YouTube Music using your browser headers
  - Prints the first 5 songs from each of your playlists (PLAYLIST_IDS)
  - Prints your 5 most recent history items
  - Shows your top artists (used for AI taste scoring)

Run:
  cd "Shazam AI"
  python3 tests/step2_test_ytmusic.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv()

from ytmusic_handler import build_ytmusic, get_all_playlist_tracks, get_history, build_taste_profile

def main():
    headers_json = os.getenv("YTMUSIC_HEADERS", "").strip()
    playlist_ids_raw = os.getenv("PLAYLIST_IDS", "").strip()

    missing = []
    if not headers_json:
        missing.append("YTMUSIC_HEADERS")
    if not playlist_ids_raw:
        missing.append("PLAYLIST_IDS")

    if missing:
        print(f"\nERROR: Missing env vars: {', '.join(missing)}")
        print("See SETUP.md for how to set these up.")
        sys.exit(1)

    playlist_ids = [p.strip() for p in playlist_ids_raw.split(",") if p.strip()]

    print("\nStep 2: Testing YouTube Music connection...")
    print("=" * 50)

    try:
        ytm = build_ytmusic(headers_json)
        print("Connected to YouTube Music.")
    except Exception as e:
        print(f"\nFAILED to build YTMusic client: {e}")
        print("Check that YTMUSIC_HEADERS is valid JSON.")
        sys.exit(1)

    # Test each playlist individually first
    from ytmusic_handler import get_playlist_tracks
    all_tracks = []
    for pid in playlist_ids:
        print(f"\nFetching playlist {pid}...")
        try:
            tracks = get_playlist_tracks(ytm, pid, debug=True)
            print(f"  First 5 songs:")
            for t in tracks[:5]:
                print(f"    {t['title']} - {t['artist']}")
            all_tracks.extend(tracks)
        except Exception as e:
            print(f"  FAILED: {e}")
            print(f"  Check that {pid} is correct and your account has access.")
            sys.exit(1)

    print(f"\nCombined total across {len(playlist_ids)} playlist(s): {len(all_tracks)} songs")

    # Test history
    print("\nFetching listening history...")
    try:
        history = get_history(ytm, debug=True)
        print(f"Your 5 most recent plays:")
        for t in history[:5]:
            print(f"  {t['title']} - {t['artist']}")
    except Exception as e:
        print(f"WARNING: Could not fetch history: {e}")
        print("This is non-fatal - taste profile will use playlists only.")
        history = []

    # Build taste profile preview
    print("\nBuilding taste profile...")
    taste_profile = build_taste_profile(all_tracks, history)
    top = taste_profile["top_artists"][:10]
    print(f"Your top 10 artists by play count: {', '.join(top)}")

    print("\nStep 2 passed. Move on to step 3.")


if __name__ == "__main__":
    main()
