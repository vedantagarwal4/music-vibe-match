"""
ytmusic_handler.py

Handles all YouTube Music interactions via ytmusicapi.

PLAYLIST_IDS (comma-separated in .env) - all playlists to check for duplicates
AND to build your taste profile from. Typically your "All Time" and "House" playlists.

Listening history is also pulled to strengthen the taste profile.

One-time auth setup:
  1. Open https://music.youtube.com in Chrome (must be logged in)
  2. Open DevTools (F12) -> Application tab -> Cookies
  3. Copy the Cookie values and compute SAPISIDHASH (see SETUP.md)
  4. Put the resulting JSON into YTMUSIC_HEADERS env var
"""

import json
import os
from typing import Optional
from ytmusicapi import YTMusic


def build_ytmusic(headers_json: str) -> YTMusic:
    """
    Build a YTMusic client from a JSON string of browser headers.
    `headers_json` is the content of the file produced by ytmusicapi setup.
    """
    headers = json.loads(headers_json)
    return YTMusic(auth=headers)


def get_playlist_tracks(ytm: YTMusic, playlist_id: str, debug: bool = False) -> list[dict]:
    """
    Fetch all tracks from a playlist.
    Returns list of dicts: {title, artist, video_id}
    """
    if debug:
        print(f"[YTMusic] Fetching playlist {playlist_id}...")

    try:
        result = ytm.get_playlist(playlist_id, limit=None)
    except Exception as e:
        raise RuntimeError(f"[YTMusic] Failed to fetch playlist {playlist_id}: {e}")

    tracks = result.get("tracks", [])

    if debug:
        print(f"[YTMusic] Playlist has {len(tracks)} tracks")
        if tracks:
            print(f"[YTMusic] Sample: {tracks[0].get('title')} - {_extract_artist(tracks[0])}")

    return [_normalise_yt_track(t) for t in tracks if t]


def get_liked_songs(ytm: YTMusic, limit: int = 200, debug: bool = False) -> list[dict]:
    """
    Fetch the user's liked songs from YouTube Music.
    """
    if debug:
        print(f"[YTMusic] Fetching up to {limit} liked songs...")

    try:
        result = ytm.get_liked_songs(limit=limit)
    except Exception as e:
        raise RuntimeError(f"[YTMusic] Failed to fetch liked songs: {e}")

    tracks = result.get("tracks", [])

    if debug:
        print(f"[YTMusic] Got {len(tracks)} liked songs")

    return [_normalise_yt_track(t) for t in tracks if t]


def get_history(ytm: YTMusic, debug: bool = False) -> list[dict]:
    """
    Fetch the user's YouTube Music listening history.
    """
    if debug:
        print("[YTMusic] Fetching listening history...")

    try:
        result = ytm.get_history()
    except Exception as e:
        raise RuntimeError(f"[YTMusic] Failed to fetch history: {e}")

    if debug:
        print(f"[YTMusic] Got {len(result)} history items")

    return [_normalise_yt_track(t) for t in result if t]


def is_in_playlist(song_title: str, song_artist: str, playlist_tracks: list[dict]) -> bool:
    """
    Check if a song (by title + artist) already exists in a list of tracks.
    Case-insensitive, partial match on title.
    """
    title_lower = song_title.lower().strip()
    artist_lower = song_artist.lower().strip()

    for t in playlist_tracks:
        t_title = t.get("title", "").lower().strip()
        t_artist = t.get("artist", "").lower().strip()

        # Match if title is close AND artist is close
        if _fuzzy_match(title_lower, t_title) and _fuzzy_match(artist_lower, t_artist):
            return True

    return False


def get_all_playlist_tracks(ytm: YTMusic, playlist_ids: list[str], debug: bool = False) -> list[dict]:
    """
    Fetch tracks from multiple playlists and merge them (deduped by video_id).
    Used for both duplicate checking and taste profiling.
    """
    seen_ids: set[str] = set()
    merged: list[dict] = []

    for pid in playlist_ids:
        tracks = get_playlist_tracks(ytm, pid, debug=debug)
        for t in tracks:
            vid = t.get("video_id", "")
            key = vid if vid else f"{t['title']}|{t['artist']}"
            if key not in seen_ids:
                seen_ids.add(key)
                merged.append(t)

    if debug:
        print(f"[YTMusic] Combined {len(playlist_ids)} playlists -> {len(merged)} unique tracks")

    return merged


def build_taste_profile(
    taste_tracks: list[dict],
    history_tracks: list[dict],
    recent_shazam_songs: Optional[list] = None,
) -> dict:
    """
    Build a comprehensive taste profile.

    Signal hierarchy:
      taste_tracks        - ALL curated playlist songs (passed in full to the AI)
      history_tracks      - YT Music recent plays (boosted in artist counts)
      recent_shazam_songs - Auto Shazam (context only, low weight)

    Raw playlist counts are tracked separately so the AI can correctly
    apply the affinity rubric (7+ songs = 3pts etc.) from real numbers.
    """
    recent_shazam_songs = recent_shazam_songs or []

    # Raw playlist counts - used for affinity rubric display to AI
    playlist_artist_counts: dict[str, int] = {}
    for t in taste_tracks:
        a = t.get("artist", "").strip()
        if a:
            playlist_artist_counts[a] = playlist_artist_counts.get(a, 0) + 1

    # Weighted counts for sorting top artists
    # Playlist: 2x, History: 3x (actively chose to play), Auto Shazam: 1x (passive)
    weighted_counts: dict[str, int] = {}
    for t in taste_tracks:
        a = t.get("artist", "").strip()
        if a:
            weighted_counts[a] = weighted_counts.get(a, 0) + 2
    for t in history_tracks:
        a = t.get("artist", "").strip()
        if a:
            weighted_counts[a] = weighted_counts.get(a, 0) + 3
    for t in recent_shazam_songs:
        a = t.get("artist", "").strip()
        if a:
            weighted_counts[a] = weighted_counts.get(a, 0) + 1

    top_artists = sorted(weighted_counts, key=lambda a: weighted_counts[a], reverse=True)

    # ALL playlist songs - passed in full to the AI (no sampling)
    all_songs = [
        f"{t['title']} by {t['artist']}"
        for t in taste_tracks
        if t.get("title") and t.get("artist")
    ]

    # Auto Shazam - context only
    recent_sample = [
        f"{t['title']} by {t['artist']}"
        for t in recent_shazam_songs
        if t.get("title") and t.get("artist") and "Unknown" not in t.get("title", "")
    ]

    # YouTube Music history
    history_sample = [
        f"{t['title']} by {t['artist']}"
        for t in history_tracks
        if t.get("title") and t.get("artist")
    ]

    return {
        "top_artists":             top_artists[:50],
        "artist_counts":           weighted_counts,
        "playlist_artist_counts":  playlist_artist_counts,
        "all_songs":               all_songs,
        "recent_sample":           recent_sample,
        "history_sample":          history_sample,
        "total_songs":             len(taste_tracks),
    }


# --- internal helpers ---

def _normalise_yt_track(t: dict) -> dict:
    return {
        "title": t.get("title", "").strip(),
        "artist": _extract_artist(t),
        "video_id": t.get("videoId", ""),
    }


def _extract_artist(track: dict) -> str:
    """ytmusicapi returns artists as a list of dicts [{name: ...}]"""
    artists = track.get("artists") or []
    if isinstance(artists, list):
        return ", ".join(a.get("name", "") for a in artists if a.get("name"))
    if isinstance(artists, str):
        return artists
    return ""


def _fuzzy_match(a: str, b: str) -> bool:
    """True if strings share significant overlap (handles minor typos/punctuation)."""
    if not a or not b:
        return False
    # Strip punctuation for comparison
    import re
    clean = lambda s: re.sub(r"[^\w\s]", "", s).strip()
    ca, cb = clean(a), clean(b)
    return ca == cb or ca in cb or cb in ca
