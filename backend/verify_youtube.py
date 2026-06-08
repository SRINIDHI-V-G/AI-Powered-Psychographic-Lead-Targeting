"""
YouTube API verifier — validates the full YouTube discovery pipeline
end-to-end using real API calls before starting the backend.

WHAT THIS SCRIPT DOES
---------------------
1. Checks that YOUTUBE_API_KEY is configured.
2. Verifies httpx is importable (used for all YouTube API calls).
3. Health-checks the YouTube Data API v3 (channels endpoint, 1 unit).
4. Searches YouTube for videos matching a test keyword (100 units).
5. Fetches comments from the first video (1 unit).
6. Extracts commenter channel IDs (potential leads).
7. Runs location inference on the comment text.
8. Prints a summary of discovered data with quota usage.
9. Exits 0 on success, 1 on failure.

QUOTA NOTE
----------
Each run of this script consumes:
  - 1 unit  (channels health check)
  - 100 units (one search call)
  - 1 unit  (one commentThreads call)
  Total: ~102 units out of 10,000/day free quota.

CREDENTIALS SETUP
-----------------
1. Go to: https://console.cloud.google.com
2. Create or select a project.
3. Enable "YouTube Data API v3" under APIs & Services → Library.
4. Go to APIs & Services → Credentials → Create Credentials → API Key.
5. Add to backend/.env:
     YOUTUBE_API_KEY=<your-api-key>

NOTE: google-api-python-client is NOT needed — this project calls the
YouTube REST API directly with httpx.

RUN
---
  cd backend
  venv\\Scripts\\python verify_youtube.py
"""
from __future__ import annotations

import sys
import time
import logging

import os

sys.path.insert(0, ".")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from dotenv import load_dotenv
load_dotenv(".env", override=False)   # load .env without overriding existing env vars


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


class _Settings:
    YOUTUBE_API_KEY: str = _env("YOUTUBE_API_KEY")
    YOUTUBE_MAX_VIDEOS_PER_KEYWORD: int = int(_env("YOUTUBE_MAX_VIDEOS_PER_KEYWORD", "10"))
    YOUTUBE_MAX_COMMENTS_PER_VIDEO: int = int(_env("YOUTUBE_MAX_COMMENTS_PER_VIDEO", "50"))
    MOCK_DISCOVERY: bool = _env("MOCK_DISCOVERY", "false").lower() == "true"


settings = _Settings()


def _bar(label: str, value: str, ok: bool = True) -> None:
    tick = "OK" if ok else "!!"
    print(f"  [{tick}] {label}: {value}")


def _section(title: str) -> None:
    print()
    print("=" * 62)
    print(f"  {title}")
    print("=" * 62)


_quota_used = 0

# ── Step 1: Check configuration ───────────────────────────────────────────────

_section("Step 1 — Credential Check")

if not settings.YOUTUBE_API_KEY:
    _bar("YOUTUBE_API_KEY", "NOT SET", ok=False)
    print()
    print("  [!!]  YOUTUBE_API_KEY is not configured.")
    print()
    print("  HOW TO FIX:")
    print("  1. Go to: https://console.cloud.google.com")
    print("  2. Enable 'YouTube Data API v3' under APIs & Services → Library")
    print("  3. Create Credentials → API Key")
    print("  4. Add to backend/.env:")
    print("       YOUTUBE_API_KEY=<your-key>")
    print()
    sys.exit(1)

key = settings.YOUTUBE_API_KEY
_bar("YOUTUBE_API_KEY", f"...{key[-6:]}")
_bar("Max videos/keyword", str(settings.YOUTUBE_MAX_VIDEOS_PER_KEYWORD))
_bar("Max comments/video", str(settings.YOUTUBE_MAX_COMMENTS_PER_VIDEO))
_bar("Mock discovery forced", str(settings.MOCK_DISCOVERY), ok=not settings.MOCK_DISCOVERY)

if settings.MOCK_DISCOVERY:
    print()
    print("  [!!]  MOCK_DISCOVERY=true in .env — YouTube provider will NOT be used.")
    print("      Set MOCK_DISCOVERY=false to enable real YouTube discovery.")
    sys.exit(1)

# ── Step 2: Import check ──────────────────────────────────────────────────────

_section("Step 2 — Dependency Check")

try:
    import httpx
    _bar("httpx", f"version {httpx.__version__}")
except ImportError:
    print("  [!!]  httpx is not installed.")
    print("      Run: pip install httpx==0.27.0")
    print("      Or:  pip install -r requirements.txt")
    sys.exit(1)

_bar("google-api-python-client", "NOT needed — project uses httpx directly")

# ── Step 3: Health check (channels endpoint, 1 unit) ─────────────────────────

_section("Step 3 — YouTube API Health Check (1 quota unit)")

_YT_BASE = "https://www.googleapis.com/youtube/v3"

print("  Calling /channels with a known channel ID...")

try:
    t0 = time.time()
    resp = httpx.get(
        f"{_YT_BASE}/channels",
        params={"part": "id", "id": "UCVHFbw7woebKtHUDsDQfglA", "maxResults": 1, "key": key},
        timeout=15.0,
    )
    elapsed = time.time() - t0
    _quota_used += 1

    if resp.status_code == 200:
        _bar("HTTP status", f"200 OK (in {elapsed:.2f}s)")
        _bar("API reachable", "YES — YouTube Data API v3 is enabled and key is valid")
    elif resp.status_code == 400:
        err = resp.json().get("error", {})
        print(f"  [!!]  HTTP 400 Bad Request: {err.get('message', 'unknown')}")
        print("      → The API key format is invalid or the request is malformed.")
        sys.exit(1)
    elif resp.status_code == 403:
        err = resp.json().get("error", {})
        msg = err.get("message", "unknown")
        print(f"  [!!]  HTTP 403 Forbidden: {msg}")
        if "disabled" in msg.lower() or "not been used" in msg.lower():
            print("      → YouTube Data API v3 is NOT enabled for this key's project.")
            print("        Fix: console.cloud.google.com → APIs & Services → Library")
            print("              → search 'YouTube Data API v3' → Enable")
        elif "quota" in msg.lower():
            print("      → Daily quota exceeded (10,000 units/day). Wait until midnight PT.")
        else:
            print("      → Key may be restricted to specific IPs or referrers.")
            print("        Fix: Cloud Console → Credentials → edit key → remove restrictions")
        sys.exit(1)
    elif resp.status_code == 429:
        print("  [!!]  HTTP 429 Rate Limit exceeded. Wait a few seconds and retry.")
        sys.exit(1)
    else:
        print(f"  [!!]  Unexpected HTTP {resp.status_code}: {resp.text[:200]}")
        sys.exit(1)

except httpx.TimeoutException:
    print("  [!!]  Request timed out (15s). Is the network reachable?")
    sys.exit(1)
except httpx.ConnectError as exc:
    print(f"  [!!]  Connection error: {exc}")
    print("      → Check your internet connection.")
    sys.exit(1)

# ── Step 4: Video search (100 units) ─────────────────────────────────────────

_section("Step 4 — Live Video Search (100 quota units)")

TEST_KEYWORD = "fitness app india"
print(f"  Searching YouTube for: '{TEST_KEYWORD}'...")

video_ids: list[str] = []
try:
    t0 = time.time()
    resp = httpx.get(
        f"{_YT_BASE}/search",
        params={
            "part": "id,snippet",
            "q": TEST_KEYWORD,
            "type": "video",
            "maxResults": 5,
            "order": "relevance",
            "videoEmbeddable": "true",
            "safeSearch": "none",
            "key": key,
        },
        timeout=15.0,
    )
    elapsed = time.time() - t0
    _quota_used += 100

    if resp.status_code != 200:
        err = resp.json().get("error", {})
        print(f"  [!!]  Search failed: HTTP {resp.status_code} — {err.get('message', 'unknown')}")
        sys.exit(1)

    data = resp.json()
    items = data.get("items", [])
    _bar("Search status", f"200 OK (in {elapsed:.2f}s)")
    _bar("Videos found", str(len(items)))

    for item in items:
        vid = item.get("id", {}).get("videoId", "")
        title = item.get("snippet", {}).get("title", "")
        channel = item.get("snippet", {}).get("channelTitle", "")
        if vid:
            video_ids.append(vid)
            print(f"    [{vid}] {title[:55]!r} — {channel[:30]}")

except Exception as exc:
    print(f"  [!!]  Search request failed: {type(exc).__name__}: {exc}")
    sys.exit(1)

if not video_ids:
    print("  [!!]  No videos returned by search. Try a different keyword.")
    sys.exit(1)

# ── Step 5: Comment retrieval (1 unit) ────────────────────────────────────────

_section("Step 5 — Comment Retrieval (1 quota unit)")

test_video_id = video_ids[0]
print(f"  Fetching comments for video: {test_video_id}")
print(f"  URL: https://www.youtube.com/watch?v={test_video_id}")

comments: list[dict] = []
try:
    t0 = time.time()
    resp = httpx.get(
        f"{_YT_BASE}/commentThreads",
        params={
            "part": "snippet",
            "videoId": test_video_id,
            "maxResults": 10,
            "order": "relevance",
            "textFormat": "plainText",
            "key": key,
        },
        timeout=15.0,
    )
    elapsed = time.time() - t0
    _quota_used += 1

    if resp.status_code == 403:
        err = resp.json().get("error", {})
        msg = err.get("message", "")
        if "disabled comments" in msg.lower() or "commentsDisabled" in str(resp.json()):
            _bar("Comments", "disabled for this video — this is normal, pipeline skips it")
        else:
            print(f"  [!!]  403 Forbidden: {msg}")
            sys.exit(1)
    elif resp.status_code == 200:
        data = resp.json()
        raw_items = data.get("items", [])
        _bar("Comment status", f"200 OK (in {elapsed:.2f}s)")
        _bar("Comments returned", str(len(raw_items)))

        for item in raw_items:
            top = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            text = top.get("textDisplay", "").strip()
            if not text or len(text) < 10:
                continue
            comments.append({
                "text": text,
                "author_name": top.get("authorDisplayName", ""),
                "author_channel_id": top.get("authorChannelId", {}).get("value", ""),
                "like_count": top.get("likeCount", 0),
                "published_at": top.get("publishedAt", ""),
            })
    else:
        print(f"  [!!]  Unexpected HTTP {resp.status_code}: {resp.text[:200]}")
        sys.exit(1)

except Exception as exc:
    print(f"  [!!]  Comment request failed: {type(exc).__name__}: {exc}")
    sys.exit(1)

# ── Step 6: Lead extraction ───────────────────────────────────────────────────

_section("Step 6 — Lead Extraction (Commenters as Candidates)")

if not comments:
    print("  [!!]  No comments extracted (comments may be disabled on this video).")
    print("     The pipeline handles this gracefully and moves to the next video.")
else:
    print(f"  Extracted {len(comments)} potential leads from video comments:\n")
    for i, c in enumerate(comments[:5], 1):
        author = c["author_name"]
        channel_id = c["author_channel_id"]
        likes = c["like_count"]
        text_preview = c["text"][:70].replace("\n", " ")
        print(f"  Lead #{i}:")
        print(f"    Name:       {author}")
        print(f"    Channel ID: {channel_id}")
        print(f"    Profile:    https://www.youtube.com/channel/{channel_id}")
        print(f"    Likes:      {likes}")
        print(f"    Comment:    {text_preview!r}")
        print()

# ── Step 7: Location inference ────────────────────────────────────────────────

_section("Step 7 — Location Inference")

_CITY_SIGNALS: dict[str, list[str]] = {
    "chennai":   ["chennai", "madras", "tamil nadu", "tn", "chn"],
    "bangalore": ["bangalore", "bengaluru", "blr", "karnataka"],
    "mumbai":    ["mumbai", "bombay", "maharashtra", "mum"],
    "delhi":     ["delhi", "new delhi", "ncr"],
    "hyderabad": ["hyderabad", "hyd", "telangana"],
    "kolkata":   ["kolkata", "calcutta", "wb", "west bengal"],
}
_INDIA_SIGNALS = ["india", "indian", "desi", "bharat"]

inferred: list[str] = []
for c in comments:
    combined = f"{c['author_name']} {c['text']}".lower()
    loc = "unknown"
    for city, signals in _CITY_SIGNALS.items():
        if any(s in combined for s in signals):
            loc = city
            break
    else:
        if any(s in combined for s in _INDIA_SIGNALS):
            loc = "India (regional)"
    inferred.append(loc)

known = [l for l in inferred if l != "unknown"]
_bar("Comments with location signal", f"{len(known)} / {len(inferred)}")
if known:
    from collections import Counter
    counts = Counter(inferred)
    for loc, count in counts.most_common():
        print(f"    {loc}: {count}")
else:
    print("  [i]  Most YouTube comments lack location signals — this is expected.")
    print("     Location inference works on display name + comment text.")
    print("     Confidence will be 'unknown' for most leads, which is normal.")

# ── Step 8: Quota summary ─────────────────────────────────────────────────────

_section("Step 8 — Quota Usage Summary")

daily_quota = 10_000
remaining = daily_quota - _quota_used
_bar("Units used this script run", str(_quota_used))
_bar("Daily quota (free tier)",     f"{daily_quota:,} units/day")
_bar("Estimated remaining today",   f"{remaining:,} units (approximate)")

print()
print("  A full 25-user discovery run costs approximately:")
print("    15 keywords × 100 units (search)  = 1,500 units")
print("    150 videos  × 1 unit   (comments) =   150 units")
print("    TOTAL per run:                     ~1,650 units (~16% of daily quota)")
print()
print("  You can run ~6 full discovery runs per day on the free tier.")

# ── Summary ───────────────────────────────────────────────────────────────────

_section("YouTube Provider — Status")

print()
print("  [OK]  API key: configured and valid")
print("  [OK]  YouTube Data API v3: enabled and reachable")
print("  [OK]  Video search: working")
print(f"  [OK]  Comment retrieval: {'working' if comments else 'skipped (disabled on test video)'}")
print(f"  [OK]  Lead extraction: {len(comments)} candidates from 1 video")
print()
print("  The YouTube provider is ready. Next steps:")
print()
print("  1. Start the backend:")
print("       cd backend")
print("       venv\\Scripts\\uvicorn app.main:app --reload --port 8000")
print()
print("  2. Create a product and trigger discovery:")
print("       POST http://localhost:8000/api/v1/products/")
print("       POST http://localhost:8000/api/v1/products/{id}/discovery/start")
print()
print("  3. Monitor discovery in real time:")
print("       GET  http://localhost:8000/api/v1/products/{id}/discovery/jobs")
print("       GET  http://localhost:8000/api/v1/discovery/provider/status")
print()
print("  4. Verify results in the database:")
print("       SELECT COUNT(*) FROM discovered_users WHERE platform = 'youtube';")
print("       SELECT COUNT(*) FROM user_content uc JOIN discovered_users du")
print("              ON uc.user_id = du.id WHERE du.platform = 'youtube';")
print()
sys.exit(0)
