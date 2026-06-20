"""
Test scoring for specific songs against your real taste profile.
Run: python3 tests/test_specific_songs.py
"""

import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv()
import os

from ytmusic_handler import build_ytmusic, get_all_playlist_tracks, get_history, build_taste_profile
from scorer import build_gemini_client, build_taste_summary, score_song

SONGS = [
    ("Kya Mai Yaha", "Encore ABJ and DL91 Era"),
    ("Farzi Cheema", "Y and Gur Sidhu"),
    ("It's About Time", "Naam Sujal, Siyaahi and Dhanji"),
    ("Cheetah Print", "Drake and Sexyy Red"),
    ("30 Shooter", "Talha Anjum and Umair"),
    ("Magnetic", "The Bausa"),
    ("Don't Start Now", "Dua Lipa"),
    ("Don't Blame Me", "Taylor Swift"),
    ("Girls", "The Kid LAROI"),
]

def main():
    print("\nLoading your taste profile from YouTube Music...")

    ytm = build_ytmusic(os.getenv("YTMUSIC_HEADERS"))
    playlist_ids = [p.strip() for p in os.getenv("PLAYLIST_IDS", "").split(",") if p.strip()]
    playlist_tracks = get_all_playlist_tracks(ytm, playlist_ids, debug=False)
    print(f"Playlists: {len(playlist_tracks)} songs")

    try:
        history_tracks = get_history(ytm, debug=False)
        print(f"History: {len(history_tracks)} items")
    except Exception:
        history_tracks = []
        print("History: unavailable (non-fatal)")

    taste_profile = build_taste_profile(playlist_tracks, history_tracks, recent_shazam_songs=[])
    taste_summary = build_taste_summary(taste_profile)

    groq = build_gemini_client(os.getenv("GEMINI_API_KEY"))

    print(f"\nScoring {len(SONGS)} songs...\n")
    print("=" * 65)

    results = []
    for i, (title, artist) in enumerate(SONGS):
        if i > 0:
            time.sleep(9)
        r = score_song(groq, title, artist, taste_summary, debug=False)
        results.append(r)

    results.sort(key=lambda x: x["score"], reverse=True)

    for r in results:
        b = r["breakdown"]
        print(f"\n{r['score']}/10 | {r['title']} - {r['artist']}")
        print(f"  Genre:     {r['genre']}")
        print(f"  Breakdown: artist={b['artist_affinity']}/3  vibe={b['vibe_match']}/3  quality={b['track_quality']}/2  discovery={b['discovery_fit']}/2")
        print(f"  Reason:    {r['reasoning']}")

    print("\n" + "=" * 65)
    print(f"Threshold 6+: {sum(1 for r in results if r['score'] >= 6)} recommended  |  {sum(1 for r in results if r['score'] < 6)} skipped")

if __name__ == "__main__":
    main()
