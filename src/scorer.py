"""
scorer.py

Uses Gemini 2.5 Flash (free tier) to score newly Shazam-detected songs
against the user's complete taste profile.

Free tier limits:
  - 15 RPM (requests per minute)
  - 1,000,000 TPM (tokens per minute)  <- no longer a bottleneck
  - 1,500 RPD (requests per day)

Scoring rubric (total /10):
  - Artist affinity   (0-3): actual song count in library
  - Vibe match        (0-3): does this song fit alongside the user's songs
  - Track quality     (0-2): standout production or generic filler
  - Discovery fit     (0-2): would this expand taste in a welcome direction
"""

import time
from google import genai
from google.genai import types

GEMINI_MODEL = "gemini-2.5-flash"


def build_gemini_client(api_key: str):
    return genai.Client(api_key=api_key)


# Keep old Groq alias so nothing else breaks
build_groq_client = build_gemini_client


def build_taste_summary(taste_profile: dict, feedback: dict = None) -> str:
    """
    Build a comprehensive taste profile for the AI scorer.

    Gemini 2.5 Flash free tier: 1M TPM - no token budget constraints.
    We pass 700 artist-frequency-weighted songs + explicit artist count table.

    Song sampling: sort playlist by artist frequency (descending), then take
    every Nth song. Frequent artists get proportionally more slots; all artists
    including house/eclectic ones with 1 song still appear.
    """
    feedback                = feedback or {}
    playlist_artist_counts  = taste_profile.get("playlist_artist_counts", {})
    all_songs               = taste_profile.get("all_songs", [])
    recent_sample           = taste_profile.get("recent_sample", [])
    history_sample          = taste_profile.get("history_sample", [])
    total_songs             = taste_profile.get("total_songs", 0)

    # Sort artists by raw playlist count for affinity display
    sorted_artists = sorted(
        playlist_artist_counts.items(),
        key=lambda x: x[1],
        reverse=True
    )

    def affinity_label(count: int) -> str:
        if count >= 7:
            return "CORE (affinity 3/3)"
        if count >= 3:
            return "STRONG (affinity 2/3)"
        if count >= 1:
            return "KNOWN (affinity 1/3)"
        return ""

    artist_lines = "\n".join(
        f"  {a}: {c} songs - {affinity_label(c)}"
        for a, c in sorted_artists[:50]
        if c >= 1
    )

    # Pass all songs - Gemini 2.5 Flash has 1M token context, no cap needed.
    # Still sort by artist frequency so most-loved artists appear first.
    freq_map = {a: c for a, c in playlist_artist_counts.items()}
    def song_freq(song_str: str) -> int:
        parts = song_str.split(" by ", 1)
        artist = parts[1].strip() if len(parts) == 2 else ""
        return freq_map.get(artist, 0)
    sampled_songs = sorted(all_songs, key=song_freq, reverse=True)

    songs_block = "\n".join(f"  {s}" for s in sampled_songs)

    history_str = (
        "\n".join(f"  {s}" for s in history_sample[:30])
        if history_sample else "  (not available)"
    )

    shazam_str = (
        "\n".join(f"  {s}" for s in recent_sample[:30])
        if recent_sample else "  (none)"
    )

    liked_songs    = feedback.get("liked_songs", [])
    disliked_songs = feedback.get("disliked_songs", [])
    artist_boosts  = feedback.get("artist_boosts", {})

    feedback_block = ""
    if liked_songs or disliked_songs or artist_boosts:
        liked_str    = "\n".join(f"  + {s}" for s in liked_songs)    or "  (none yet)"
        disliked_str = "\n".join(f"  - {s}" for s in disliked_songs) or "  (none yet)"
        boost_str    = "\n".join(
            f"  {a}: {v:+d} (loved)" if v > 0
            else f"  {a}: {v:+d} (disliked)"
            for a, v in sorted(artist_boosts.items(), key=lambda x: x[1], reverse=True)
        ) or "  (none yet)"
        feedback_block = f"""

--- EXPLICIT USER FEEDBACK (HIGHEST SIGNAL - override everything else) ---
Songs this user has explicitly LIKED after listening:
{liked_str}

Songs this user has explicitly DISLIKED:
{disliked_str}

Artist feedback (net score from likes/dislikes):
{boost_str}"""

    return f"""=== USER TASTE PROFILE ===
Total curated songs: {total_songs}
{feedback_block}

--- COMPLETE PLAYLIST (every song this user has consciously saved) ---
Use this as your primary reference. Judge vibe, energy, mood, and genre diversity from this list.
{songs_block}

--- YOUTUBE MUSIC RECENT PLAYS ---
Songs the user actively chose to listen to recently:
{history_str}

--- AUTO-SHAZAM CONTEXT (passive detections - low reliability) ---
Detected by phone automatically. Does NOT mean the user likes these songs.
{shazam_str}

--- ARTIST AFFINITY TABLE (raw playlist counts - use for rubric scoring) ---
{artist_lines}

=== SCORING INSTRUCTIONS ===
1. Use the COMPLETE PLAYLIST above to understand this user's full taste range.
   They are eclectic - do not assume genre boundaries. House, hip-hop, Bollywood,
   afrobeat, pop - all coexist. Judge by vibe and quality, not genre labels.
2. Use the ARTIST AFFINITY TABLE for the artist affinity rubric score.
   Apply counts directly: 7+ songs = 3pts, 3-6 = 2pts, 1-2 = 1pt, 0 = 0pts.
3. For artists NOT in the table, use your knowledge of whether they sound like
   artists the user has many songs from.
4. If the user has provided explicit feedback, weight it above everything else."""


def score_song(
    model,
    song_title: str,
    song_artist: str,
    taste_summary: str,
    debug: bool = False,
) -> dict:
    """
    Score a single song against the user's taste profile.
    """
    prompt = f"""{taste_summary}

=== SONG TO EVALUATE ===
Title:  "{song_title}"
Artist: {song_artist}

=== YOUR TASK ===
Score this song for this specific user using the rubric below.
Use your knowledge of this song and artist to answer accurately.

RUBRIC (assign points, then sum for final score):

1. ARTIST AFFINITY (0-3 pts)
   - 3 pts: Artist has 7+ songs in the user's library (use the affinity table above)
   - 2 pts: Artist has 3-6 songs OR sounds nearly identical to a core artist
   - 1 pt:  Artist has 1-2 songs OR is stylistically similar to someone the user loves
         OR is a completely new artist whose sound clearly fits the playlist vibe
   - 0 pts: Artist is unknown AND their sound is genuinely foreign to this user's taste

2. VIBE & ENERGY MATCH (0-3 pts)
   - Compare this song's mood, energy, tempo, and emotional tone against the full playlist
   - 3 pts: Would slot perfectly alongside their most loved songs
   - 2 pts: Fits the library's overall vibe even if not a perfect match
   - 1 pt:  Some overlap but would feel slightly out of place
   - 0 pts: Would feel jarring or completely out of place

3. TRACK QUALITY (0-2 pts)
   - Judge production, songwriting, memorability
   - 2 pts: Well-produced, memorable, something people seek out and replay
   - 1 pt:  Filler-level, generic, or poorly produced
   - 0 pts: Below average, grating, or extremely low effort

4. DISCOVERY FIT (0-2 pts)
   - The PURPOSE of this system is discovery. Reward new artists generously if the fit is there.
   - 2 pts: New artist or sound that fits the user's taste - this is exactly what we want to surface
   - 1 pt:  Artist already well-known to the user (already in their library) - less discovery value
   - 0 pts: Completely outside their world with no obvious bridge

Respond in this EXACT format (no extra text):
GENRE: <concise description of this song's actual sound>
ARTIST_AFFINITY: <0-3>
VIBE_MATCH: <0-3>
TRACK_QUALITY: <0-2>
DISCOVERY_FIT: <0-2>
SCORE: <sum of above, 0-10>
REASON: <2-3 sentences referencing specific songs from their playlist that this reminds you of>"""

    if debug:
        print(f"[Scorer] Scoring: {song_title} by {song_artist}")

    estimated_tokens = len(prompt) // 3
    print(f"         [tokens] estimated prompt size: ~{estimated_tokens:,} tokens", flush=True)

    text = None
    for attempt in range(3):
        try:
            response = model.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=500,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            text = response.text.strip()
            usage = response.usage_metadata
            print(
                f"         [tokens] prompt={usage.prompt_token_count} "
                f"completion={usage.candidates_token_count} "
                f"total={usage.total_token_count}",
                flush=True,
            )
            break
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower() or "rate" in err.lower() or "resource_exhausted" in err.lower():
                wait = 60 * (attempt + 1)
                print(f"[Scorer] Rate limit hit: {err[:200]}", flush=True)
                print(f"[Scorer] Waiting {wait}s before retry {attempt+1}/3...", flush=True)
                time.sleep(wait)
            elif "503" in err or "unavailable" in err.lower():
                wait = 15 * (attempt + 1)
                print(f"[Scorer] Gemini overloaded (503) - waiting {wait}s before retry {attempt+1}/3...", flush=True)
                time.sleep(wait)
            else:
                print(f"[Scorer] Gemini error for '{song_title}': {e}")
                return _fallback_result(song_title, song_artist)

    if text is None:
        print(f"[Scorer] Failed after 3 retries: {song_title}")
        return _fallback_result(song_title, song_artist)

    parsed = _parse_response(text)

    if debug:
        print(f"[Scorer]   -> Score: {parsed['score']}/10 | {parsed['genre']}")
        print(f"[Scorer]      Breakdown: artist={parsed['artist_affinity']} "
              f"vibe={parsed['vibe_match']} quality={parsed['track_quality']} "
              f"discovery={parsed['discovery_fit']}")
        print(f"[Scorer]      Reason: {parsed['reasoning']}")

    return {
        "title":           song_title,
        "artist":          song_artist,
        "score":           parsed["score"],
        "reasoning":       parsed["reasoning"],
        "genre":           parsed["genre"],
        "breakdown": {
            "artist_affinity": parsed["artist_affinity"],
            "vibe_match":      parsed["vibe_match"],
            "track_quality":   parsed["track_quality"],
            "discovery_fit":   parsed["discovery_fit"],
        },
        "yt_search_link":  _yt_search_link(song_title, song_artist),
    }


def score_songs_batch(
    model,
    songs: list[dict],
    taste_summary: str,
    min_score: int = 6,
    delay_seconds: float = 9.0,
    debug: bool = False,
) -> list[dict]:
    results = []
    total   = len([s for s in songs if s.get("title")])

    for i, song in enumerate(songs):
        title  = song.get("title", "")
        artist = song.get("artist", "")

        if not title:
            continue

        print(f"  [{i+1}/{total}] Scoring: {title} by {artist}...", flush=True)
        result = score_song(model, title, artist, taste_summary, debug=debug)
        results.append(result)
        print(f"         -> {result['score']}/10 | {result['genre']}", flush=True)

        if i < total - 1:
            time.sleep(delay_seconds)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# --- helpers ---

def _parse_response(text: str) -> dict:
    genre           = ""
    score           = 5
    reasoning       = ""
    artist_affinity = 0
    vibe_match      = 0
    track_quality   = 0
    discovery_fit   = 0

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("GENRE:"):
            genre = line[6:].strip()
        elif line.startswith("SCORE:"):
            try:
                score = int(line[6:].strip().split()[0])
                score = max(0, min(10, score))
            except (ValueError, IndexError):
                score = 5
        elif line.startswith("REASON:"):
            reasoning = line[7:].strip()
        elif line.startswith("ARTIST_AFFINITY:"):
            try:
                artist_affinity = int(line[16:].strip().split()[0])
            except (ValueError, IndexError):
                pass
        elif line.startswith("VIBE_MATCH:"):
            try:
                vibe_match = int(line[11:].strip().split()[0])
            except (ValueError, IndexError):
                pass
        elif line.startswith("TRACK_QUALITY:"):
            try:
                track_quality = int(line[14:].strip().split()[0])
            except (ValueError, IndexError):
                pass
        elif line.startswith("DISCOVERY_FIT:"):
            try:
                discovery_fit = int(line[14:].strip().split()[0])
            except (ValueError, IndexError):
                pass

    return {
        "genre":           genre,
        "score":           score,
        "reasoning":       reasoning,
        "artist_affinity": artist_affinity,
        "vibe_match":      vibe_match,
        "track_quality":   track_quality,
        "discovery_fit":   discovery_fit,
    }


def _fallback_result(title: str, artist: str) -> dict:
    return {
        "title":     title,
        "artist":    artist,
        "score":     5,
        "reasoning": "Could not score - API error.",
        "genre":     "Unknown",
        "breakdown": {
            "artist_affinity": 0,
            "vibe_match":      0,
            "track_quality":   0,
            "discovery_fit":   0,
        },
        "yt_search_link": _yt_search_link(title, artist),
    }


def _yt_search_link(title: str, artist: str) -> str:
    from urllib.parse import quote_plus
    query = quote_plus(f"{title} {artist}")
    return f"https://music.youtube.com/search?q={query}"
