"""
STEP 3 - Test AI Scoring
=========================
Tests the Groq (Llama 3) multi-dimensional scoring engine.

Scoring rubric (out of 10):
  Artist affinity  0-3  (how much the user already loves this artist)
  Vibe match       0-3  (does this feel at home in their library)
  Track quality    0-2  (is this a standout track or generic filler)
  Discovery fit    0-2  (does it expand their taste in a good direction)

Expected results:
  - Hugel / Fisher type songs    -> HIGH (8-10)
  - Quality Bollywood (Naina)    -> HIGH (7-9) -- user confirmed they love it
  - Generic desi hip-hop         -> MID-LOW (3-5) -- genre alone isn't enough
  - Country / Folk               -> LOW (1-3)

Run:
  cd "Shazam AI"
  python3 tests/step3_test_scorer.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv()

from scorer import build_gemini_client, build_taste_summary, score_song

# Simulates what build_taste_profile() would return from real YTMusic data
MOCK_TASTE_PROFILE = {
    "total_songs": 1598,
    "artist_counts": {
        # 7+ = core artists (3 pts affinity)
        "J. Cole": 18, "Drake": 15, "Fred again..": 12, "Hugel": 11,
        "AP Dhillon": 10, "Arijit Singh": 9, "Diljit Dosanjh": 8,
        "Kid Francescoli": 7,
        # 3-6 = strong artists (2 pts affinity)
        "Disclosure": 6, "Fisher": 6, "Divine": 5, "Chris Lake": 5,
        "Claptone": 4, "Badshah": 4, "Raftaar": 3, "Jasleen Royal": 3,
        # 1-2 = occasional (1 pt affinity)
        "Hozier": 2, "Lil Nas X": 1,
    },
    # Diverse playlist sample
    "sample_songs": [
        "DID IT AGAIN by Fred again.., Travy, Elzzz",
        "Tu Hi by Sultaan, Avvy Sra",
        "Lonely at the Top by J. Cole",
        "Farzi by Cheema Y, Gur Sidhu",
        "Moon (And It Went Like) by Kid Francescoli, Julia Minkin",
        "Understanding by Rivière Monk",
        "Ma Tnsani (Yalla Habibi) by Vanco, AYA",
        "How Deep Is Your Love by WITH U, Merlin",
        "Free Your Mind by Prospa, Cloonee",
        "Brown Munde by AP Dhillon",
        "No Role Modelz by J. Cole",
        "Losing It by Fisher",
        "Miracle by Hugel, INNA",
        "Naina by Arijit Singh",
        "CAPS LOCK by Badshah",
        "By Your Side by Claptone",
        "Mere Gully Mein by Divine, Naezy",
        "Once in a While by Disclosure",
    ],
    "history_sample": [],
    "liked_songs": [],
}

# Test songs with expected score ranges
TEST_SONGS = [
    # --- Core artist, quality track ---
    {"title": "Softly",             "artist": "Karan Aujla",          "expect": "HIGH (7-9) - similar vibe to AP Dhillon, Punjabi hip-hop"},
    {"title": "Pasoori",            "artist": "Ali Sethi, Shae Gill",  "expect": "MID-HIGH (6-8) - South Asian, melodic, quality track"},
    {"title": "Tum Kya Mile",       "artist": "Arijit Singh, Shreya Ghoshal", "expect": "HIGH (7-9) - core artist, emotional ballad"},
    # --- Same genre, mediocre track ---
    {"title": "Hookah Bar",         "artist": "Akshay Kumar",          "expect": "LOW (1-3) - desi but low quality Bollywood item song"},
    # --- Unknown artist, matches vibe ---
    {"title": "Rumble",             "artist": "Fred again.., Skrillex", "expect": "HIGH (8-10) - core artist collab, electronic"},
    # --- Mainstream pop, wrong world ---
    {"title": "Anti-Hero",          "artist": "Taylor Swift",          "expect": "LOW (1-3) - mainstream pop, nothing like this library"},
    {"title": "As It Was",          "artist": "Harry Styles",          "expect": "LOW (2-4) - indie pop, doesn't fit"},
    # --- Borderline ---
    {"title": "HUMBLE.",            "artist": "Kendrick Lamar",        "expect": "MID (5-7) - quality hip-hop but not their typical sound"},
]


def main():
    api_key = os.getenv("GROQ_API_KEY", "").strip()

    if not api_key:
        print("\nERROR: GROQ_API_KEY is not set in your .env file.")
        print("Get a free key at: https://console.groq.com")
        sys.exit(1)

    print("\nStep 3: Testing multi-dimensional AI scoring...")
    print("=" * 60)

    taste_summary = build_taste_summary(MOCK_TASTE_PROFILE)

    try:
        model = build_gemini_client(api_key)
        print("Groq client initialised.\n")
    except Exception as e:
        print(f"\nFAILED to connect to Groq: {e}")
        sys.exit(1)

    print("Scoring 5 test songs...\n")

    for song in TEST_SONGS:
        result = score_song(model, song["title"], song["artist"], taste_summary, debug=False)
        bar = "=" * result["score"] + "-" * (10 - result["score"])
        b   = result.get("breakdown", {})
        print(f"  [{bar}] {result['score']}/10 - {result['title']} by {result['artist']}")
        print(f"          Expected: {song['expect']}")
        print(f"          Genre:    {result['genre']}")
        print(f"          Breakdown: artist={b.get('artist_affinity','-')} "
              f"vibe={b.get('vibe_match','-')} "
              f"quality={b.get('track_quality','-')} "
              f"discovery={b.get('discovery_fit','-')}")
        print(f"          Reason:   {result['reasoning']}")
        print()

    print("Step 3 passed.")
    print("Naina should score high (user loves it). Generic country should score low.")
    print("\nMove on to step 4.")


if __name__ == "__main__":
    main()
