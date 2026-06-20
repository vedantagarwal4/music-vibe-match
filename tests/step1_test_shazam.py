"""
STEP 1 - Test Shazam Connection (Firebase + Firestore)
=======================================================
Confirms your Firebase credentials work and can read your Shazam library.

What it does:
  - Refreshes your Firebase ID token using the refresh token
  - Queries your Shazam tags from Firestore
  - Prints your 5 most recent Shazam songs (with title + artist)

Run:
  cd "Shazam AI"
  python3 tests/step1_test_shazam.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv()

from shazam_fetcher import get_fresh_id_token, get_firestore_tags, get_track_details

def main():
    api_key       = os.getenv("FIREBASE_API_KEY", "").strip()
    refresh_token = os.getenv("FIREBASE_REFRESH_TOKEN", "").strip()
    user_id       = os.getenv("FIREBASE_USER_ID", "").strip()
    project       = os.getenv("FIREBASE_PROJECT", "").strip()

    missing = [k for k, v in {
        "FIREBASE_API_KEY": api_key,
        "FIREBASE_REFRESH_TOKEN": refresh_token,
        "FIREBASE_USER_ID": user_id,
        "FIREBASE_PROJECT": project,
    }.items() if not v]

    if missing:
        print(f"\nERROR: Missing in .env: {', '.join(missing)}")
        sys.exit(1)

    print("\nStep 1: Testing Shazam/Firebase connection...")
    print("=" * 50)

    # Test 1: Token refresh
    print("\n[1/3] Refreshing Firebase ID token...")
    try:
        id_token = get_fresh_id_token(api_key, refresh_token)
        print("      Token refreshed successfully.")
    except PermissionError as e:
        print(f"\nFAILED: {e}")
        sys.exit(1)

    # Test 2: Firestore tags
    print("\n[2/3] Fetching your Shazam tags from Firestore...")
    try:
        tags = get_firestore_tags(id_token, user_id, project, debug=True)
    except Exception as e:
        print(f"\nFAILED: {e}")
        sys.exit(1)

    if not tags:
        print("\nWARNING: 0 tags found. Have you used Auto Shazam yet?")
        sys.exit(1)

    print(f"\n      Found {len(tags)} total tags in your Shazam account.")

    # Test 3: Track details for top 5
    print("\n[3/3] Looking up details for your 5 most recent songs...")
    for doc in tags[:5]:
        fields    = doc.get("fields", {})
        track_key = fields.get("trackKey", {}).get("stringValue", "")
        tag_time  = fields.get("tagTime",  {}).get("timestampValue", "")
        tag_type  = fields.get("type",     {}).get("stringValue", "")

        if not track_key:
            continue

        details = get_track_details(track_key)
        print(f"\n  [{tag_type}] {details['title']} - {details['artist']}")
        print(f"        Genre: {details['genre'] or 'unknown'}")
        print(f"        Detected: {tag_time}")

    print("\nStep 1 passed. Move on to step 2.")

if __name__ == "__main__":
    main()
