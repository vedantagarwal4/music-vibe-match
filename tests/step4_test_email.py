"""
STEP 4 - Test Email Sending
=============================
Sends a test email with fake song data so you can see exactly
what the digest looks like - two sections, recommended + skipped.

Run:
  cd "Shazam AI"
  python3 tests/step4_test_email.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv()

from email_sender import send_digest

# Songs that made the cut (above threshold)
MOCK_WORTHY = [
    {
        "title": "Naina",
        "artist": "Arijit Singh",
        "score": 9,
        "genre": "Bollywood ballad with Indian classical influences",
        "reasoning": "Arijit Singh is a core artist with 9 songs in your library. This track has the emotional depth and production quality that matches your existing favourites like 'Tu Hi' and 'Brown Munde'.",
        "breakdown": {"artist_affinity": 3, "vibe_match": 3, "track_quality": 2, "discovery_fit": 1},
        "yt_search_link": "https://music.youtube.com/search?q=Naina+Arijit+Singh",
    },
    {
        "title": "Miracle",
        "artist": "Hugel, INNA",
        "score": 8,
        "genre": "Deep house / Eurodance",
        "reasoning": "Hugel is a core artist with 11 songs in your library. This track's tribal house energy sits perfectly alongside 'Losing It' by Fisher and your other house picks.",
        "breakdown": {"artist_affinity": 3, "vibe_match": 3, "track_quality": 1, "discovery_fit": 1},
        "yt_search_link": "https://music.youtube.com/search?q=Miracle+Hugel+INNA",
    },
    {
        "title": "Softly",
        "artist": "Karan Aujla",
        "score": 7,
        "genre": "Punjabi hip-hop / trap",
        "reasoning": "Stylistically close to AP Dhillon and Diljit Dosanjh, both of whom you deeply love. High production quality with a sound that would fit naturally in your All Time playlist.",
        "breakdown": {"artist_affinity": 1, "vibe_match": 3, "track_quality": 2, "discovery_fit": 1},
        "yt_search_link": "https://music.youtube.com/search?q=Softly+Karan+Aujla",
    },
]

# Songs that didn't make the cut (below threshold) - still listed for reference
MOCK_SKIPPED = [
    {
        "title": "Old Town Road",
        "artist": "Lil Nas X",
        "score": 3,
        "genre": "Country-trap fusion",
        "reasoning": "Genre mismatch - country elements clash with your library's vibe.",
        "breakdown": {"artist_affinity": 1, "vibe_match": 1, "track_quality": 1, "discovery_fit": 0},
        "yt_search_link": "https://music.youtube.com/search?q=Old+Town+Road+Lil+Nas+X",
    },
    {
        "title": "Anti-Hero",
        "artist": "Taylor Swift",
        "score": 2,
        "genre": "Mainstream pop",
        "reasoning": "Nothing in common with your library - wrong energy, wrong world entirely.",
        "breakdown": {"artist_affinity": 0, "vibe_match": 1, "track_quality": 1, "discovery_fit": 0},
        "yt_search_link": "https://music.youtube.com/search?q=Anti-Hero+Taylor+Swift",
    },
    {
        "title": "Take Me to Church",
        "artist": "Hozier",
        "score": 4,
        "genre": "Soulful indie rock",
        "reasoning": "Quality track but the folk/indie rock vibe doesn't align with your electronic and hip-hop lean.",
        "breakdown": {"artist_affinity": 1, "vibe_match": 2, "track_quality": 1, "discovery_fit": 0},
        "yt_search_link": "https://music.youtube.com/search?q=Take+Me+to+Church+Hozier",
    },
]

def main():
    gmail_address = os.getenv("GMAIL_ADDRESS", "").strip()
    gmail_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()
    to_email = os.getenv("TO_EMAIL", gmail_address).strip()

    missing = []
    if not gmail_address:
        missing.append("GMAIL_ADDRESS")
    if not gmail_password:
        missing.append("GMAIL_APP_PASSWORD")

    if missing:
        print(f"\nERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    print("\nStep 4: Testing email sending...")
    print("=" * 50)
    print(f"Sending to: {to_email}")
    print("This will send a REAL email with fake test data.\n")

    try:
        send_digest(
            gmail_address=gmail_address,
            gmail_app_password=gmail_password,
            to_address=to_email,
            scored_songs=MOCK_WORTHY,
            skipped_songs=MOCK_SKIPPED,
            all_processed_count=14,
            duplicate_count=8,
            score_threshold=6,
            debug=True,
        )
    except PermissionError as e:
        print(f"\nFAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    print(f"\nSUCCESS: Check your inbox at {to_email}.")
    print("You should see two sections: recommended songs and skipped songs.")
    print("\nStep 4 passed. Move on to step 5 (full dry run).")


if __name__ == "__main__":
    main()
