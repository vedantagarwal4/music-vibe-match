"""
shazam_fetcher.py

Fetches your Shazam library using Firebase authentication + Firestore.

How it works:
  1. Uses your Firebase refresh token to get a fresh ID token automatically
     (the refresh token never expires - no manual re-auth needed)
  2. Queries your Shazam tags from Firestore (users/{uid}/tags collection)
  3. Looks up each song's title/artist/genre from Shazam's public track API

Required env vars:
  FIREBASE_API_KEY        Shazam's Firebase project API key
  FIREBASE_REFRESH_TOKEN  Your refresh token (permanent, captured once)
  FIREBASE_USER_ID        Your Firebase user ID
  FIREBASE_PROJECT        Firebase project ID
"""

import requests
import time
from datetime import datetime, timezone

FIREBASE_TOKEN_URL = "https://securetoken.googleapis.com/v1/token"
FIRESTORE_BASE     = "https://firestore.googleapis.com/v1"
RAPIDAPI_SHAZAM_URL = "https://shazam-core.p.rapidapi.com/v1/tracks/details"


def get_fresh_id_token(api_key: str, refresh_token: str) -> str:
    """
    Exchange a Firebase refresh token for a fresh ID token.
    Called automatically before every run - no manual steps needed.
    """
    resp = requests.post(
        f"{FIREBASE_TOKEN_URL}?key={api_key}",
        json={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=15,
    )
    if resp.status_code != 200:
        raise PermissionError(
            f"[Firebase] Token refresh failed ({resp.status_code}): {resp.text[:300]}\n"
            "Check that FIREBASE_REFRESH_TOKEN and FIREBASE_API_KEY are correct."
        )
    data = resp.json()
    if "id_token" not in data:
        raise PermissionError(f"[Firebase] Unexpected response: {resp.text[:300]}")
    return data["id_token"]


def get_firestore_tags(
    id_token: str,
    user_id: str,
    project: str,
    debug: bool = False,
) -> list[dict]:
    """
    Fetch all Shazam tag documents from Firestore.
    Each document has: trackKey, tagTime, type (AUTO/SYNC), location, created.
    """
    url = (
        f"{FIRESTORE_BASE}/projects/{project}/databases/(default)"
        f"/documents/users/{user_id}/tags"
    )
    headers = {"Authorization": f"Bearer {id_token}"}

    all_docs = []
    page_token = None
    page = 1

    while True:
        params: dict = {"pageSize": 100, "orderBy": "tagTime desc"}
        if page_token:
            params["pageToken"] = page_token

        if debug:
            print(f"[Shazam] Fetching Firestore tags page {page}...")

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
        except requests.RequestException as e:
            raise ConnectionError(f"[Shazam] Network error fetching tags: {e}")

        if resp.status_code == 403:
            raise PermissionError(
                "[Shazam] Firestore returned 403. "
                "The refresh token may have been revoked. "
                "Re-capture it from shazam.com (see SETUP.md Step 1)."
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"[Shazam] Firestore error {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        docs = data.get("documents", [])
        all_docs.extend(docs)

        if debug:
            print(f"[Shazam] Page {page}: {len(docs)} tags")

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        page += 1

    if debug:
        print(f"[Shazam] Total tags in Firestore: {len(all_docs)}")

    return all_docs


def get_track_details(track_key: str, rapidapi_key: str = "", debug: bool = False) -> dict:
    """
    Fetch title, artist, and genre via RapidAPI Shazam Core.
    Works from any IP including GitHub Actions (unlike shazam.com which blocks datacenters).
    Free tier: 500 requests/month at rapidapi.com/tipsters/api/shazam-core
    """
    import os
    key = rapidapi_key or os.getenv("RAPIDAPI_KEY", "")
    if not key:
        if debug:
            print(f"[Shazam] No RAPIDAPI_KEY set - skipping enrichment for {track_key}")
        return _unknown_track(track_key)

    try:
        resp = requests.get(
            RAPIDAPI_SHAZAM_URL,
            params={"track_id": track_key},
            headers={
                "X-RapidAPI-Key":  key,
                "X-RapidAPI-Host": "shazam-core.p.rapidapi.com",
            },
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"[Shazam] Track {track_key} returned {resp.status_code}")
            return _unknown_track(track_key)

        data = resp.json()
        return {
            "title":      data.get("title", "").strip(),
            "artist":     data.get("subtitle", "").strip(),
            "genre":      data.get("genres", {}).get("primary", ""),
            "shazam_key": track_key,
        }
    except Exception as e:
        print(f"[Shazam] Could not get details for track {track_key}: {e}")
        return _unknown_track(track_key)


def _filter_raw_tags_since(raw_tags: list[dict], since_iso: str) -> list[dict]:
    """Filter raw Firestore docs to those detected after since_iso (before enrichment)."""
    if not since_iso:
        return raw_tags
    try:
        cutoff = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
    except ValueError:
        return raw_tags

    filtered = []
    for doc in raw_tags:
        ts = doc.get("fields", {}).get("tagTime", {}).get("timestampValue", "")
        if not ts:
            filtered.append(doc)
            continue
        try:
            if datetime.fromisoformat(ts.replace("Z", "+00:00")) >= cutoff:
                filtered.append(doc)
        except ValueError:
            filtered.append(doc)
    return filtered


def _enrich_tags(raw_tags: list[dict], rapidapi_key: str = "", debug: bool = False) -> list[dict]:
    """Enrich a pre-filtered list of raw Firestore docs with title/artist/genre."""
    import os
    key = rapidapi_key or os.getenv("RAPIDAPI_KEY", "")
    songs = []
    for i, doc in enumerate(raw_tags):
        fields    = doc.get("fields", {})
        track_key = fields.get("trackKey", {}).get("stringValue", "")
        tag_time  = fields.get("tagTime",  {}).get("timestampValue", "")
        tag_type  = fields.get("type",     {}).get("stringValue", "")

        if not track_key:
            continue

        if debug:
            print(f"[Shazam] Enriching song {i+1}/{len(raw_tags)} (key={track_key})...")

        details = get_track_details(track_key, rapidapi_key=key, debug=debug)
        details["detected_at"] = tag_time
        details["tag_type"]    = tag_type

        songs.append(details)

        if i < len(raw_tags) - 1:
            time.sleep(0.3)

    return songs


def get_shazam_library(
    api_key: str,
    refresh_token: str,
    user_id: str,
    project: str,
    since_iso: str = "",
    limit: int = None,
    rapidapi_key: str = "",
    debug: bool = False,
) -> list[dict]:
    """
    Full pipeline:
      1. Refresh Firebase auth token
      2. Pull all Firestore tags (paginated)
      3. Filter to tags since last run  ← before enrichment
      4. Apply limit                    ← before enrichment
      5. Enrich only the final small set with title/artist/genre

    Returns list of dicts:
      {title, artist, genre, shazam_key, detected_at, tag_type}
    """
    if debug:
        print("[Shazam] Refreshing Firebase ID token...")
    id_token = get_fresh_id_token(api_key, refresh_token)
    if debug:
        print("[Shazam] Token OK.")

    raw_tags = get_firestore_tags(id_token, user_id, project, debug=debug)
    if debug:
        print(f"[Shazam] {len(raw_tags)} total tags in Firestore.")

    if since_iso:
        raw_tags = _filter_raw_tags_since(raw_tags, since_iso)
        if debug:
            print(f"[Shazam] {len(raw_tags)} tags after date filter.")

    if limit:
        raw_tags = raw_tags[:limit]
        if debug:
            print(f"[Shazam] Limited to {limit} for this run.")

    songs = _enrich_tags(raw_tags, rapidapi_key=rapidapi_key, debug=debug)
    if debug:
        print(f"[Shazam] Enriched {len(songs)} songs.")

    # Filter out unknown tracks (enrichment failed)
    known = [s for s in songs if not s["title"].startswith("Unknown track")]
    if len(known) < len(songs):
        print(f"[Shazam] {len(songs) - len(known)} tracks could not be enriched and were skipped.")
    return known


def get_recent_shazam_taste(
    api_key: str,
    refresh_token: str,
    user_id: str,
    project: str,
    days: int = 60,
    limit: int = 60,
    debug: bool = False,
) -> list[dict]:
    """
    Fetch recently Auto-Shazamed songs to use as a current-taste signal.

    These songs were playing around you recently = what you're into right now.
    Far more reliable than historical playlist counts for scoring new songs.

    Uses a cached token if called after get_shazam_library in the same run.
    """
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    if debug:
        print(f"[Shazam] Fetching recent taste: last {days} days, max {limit} songs...")

    id_token = get_fresh_id_token(api_key, refresh_token)
    raw_tags = get_firestore_tags(id_token, user_id, project, debug=False)

    # Only AUTO tags (Auto Shazam) - these are passive detections while listening
    auto_tags = [
        doc for doc in raw_tags
        if doc.get("fields", {}).get("type", {}).get("stringValue", "") == "AUTO"
    ]

    recent = _filter_raw_tags_since(auto_tags, since)
    recent = recent[:limit]

    if debug:
        print(f"[Shazam] {len(recent)} recent AUTO tags found.")

    return _enrich_tags(recent, debug=debug)


# Keep for backward compatibility
def filter_songs_since(songs: list[dict], since_iso: str) -> list[dict]:
    """Deprecated: filtering now happens before enrichment inside get_shazam_library."""
    return songs


def _unknown_track(track_key: str) -> dict:
    return {
        "title":      f"Unknown track ({track_key})",
        "artist":     "",
        "genre":      "",
        "shazam_key": track_key,
    }
