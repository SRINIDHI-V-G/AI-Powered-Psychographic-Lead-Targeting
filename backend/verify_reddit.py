"""
Reddit credential verifier — validates the full Reddit discovery pipeline
end-to-end using Application-Only OAuth before starting the backend.

WHAT THIS SCRIPT DOES
---------------------
1. Checks that CLIENT_ID, CLIENT_SECRET, and USER_AGENT are configured.
2. Initialises a PRAW Reddit instance (Application-Only OAuth).
3. Fetches a live subreddit title to confirm the OAuth token works.
4. Searches r/yoga for "yoga mat" and retrieves 3 post authors.
5. Collects the most recent 3 posts/comments for one of those authors.
6. Prints a summary of discovered data.
7. Exits 0 on success, 1 on failure.

CREDENTIALS SETUP (takes ~90 seconds)
--------------------------------------
1. Log in to reddit.com as your Reddit account (e.g. Own_Green4956).
2. Go to: https://www.reddit.com/prefs/apps
3. Click "create another app" at the bottom.
4. Fill in:
     name:         PsychographicLeads
     type:         ● script          ← select this radio button
     description:  Psychographic lead research
     redirect uri: http://localhost:8080
5. Click "create app".
6. In the new app card:
     - The short string directly under "personal use script" is CLIENT_ID
     - The "secret" field value is CLIENT_SECRET
7. Add to backend/.env:
     REDDIT_CLIENT_ID=<CLIENT_ID>
     REDDIT_CLIENT_SECRET=<CLIENT_SECRET>
     REDDIT_USER_AGENT=python:PsychographicLeads:1.0 (by u/Own_Green4956)

RUN
---
  cd backend
  venv\\Scripts\\python verify_reddit.py

USERNAME and PASSWORD are NOT required — this uses Application-Only
OAuth (client credentials grant), not a user account login.
"""
from __future__ import annotations

import sys
import os
import time
import logging

sys.path.insert(0, ".")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from dotenv import load_dotenv
load_dotenv(".env")
from app.config import settings


def _bar(label: str, value: str, ok: bool = True) -> None:
    tick = "✓" if ok else "✗"
    print(f"  [{tick}] {label}: {value}")


def _section(title: str) -> None:
    print()
    print("=" * 62)
    print(f"  {title}")
    print("=" * 62)


# ── Step 1: Check configuration ───────────────────────────────────────────────

_section("Step 1 — Credential Check")

missing: list[str] = []
if not settings.REDDIT_CLIENT_ID:
    missing.append("REDDIT_CLIENT_ID")
    _bar("REDDIT_CLIENT_ID", "NOT SET", ok=False)
else:
    _bar("REDDIT_CLIENT_ID", f"{settings.REDDIT_CLIENT_ID[:4]}...{settings.REDDIT_CLIENT_ID[-4:]}")

if not settings.REDDIT_CLIENT_SECRET:
    missing.append("REDDIT_CLIENT_SECRET")
    _bar("REDDIT_CLIENT_SECRET", "NOT SET", ok=False)
else:
    _bar("REDDIT_CLIENT_SECRET", f"{settings.REDDIT_CLIENT_SECRET[:4]}...{settings.REDDIT_CLIENT_SECRET[-4:]}")

if not settings.REDDIT_USER_AGENT:
    missing.append("REDDIT_USER_AGENT")
    _bar("REDDIT_USER_AGENT", "NOT SET", ok=False)
elif "project_owner" in settings.REDDIT_USER_AGENT:
    missing.append("REDDIT_USER_AGENT (still set to default)")
    _bar("REDDIT_USER_AGENT", "STILL DEFAULT — update with your Reddit username", ok=False)
else:
    _bar("REDDIT_USER_AGENT", settings.REDDIT_USER_AGENT)

if missing:
    print()
    print("  ✗  MISSING CREDENTIALS:")
    for m in missing:
        print(f"       {m}")
    print()
    print("  HOW TO FIX:")
    print("  1. Go to: https://www.reddit.com/prefs/apps")
    print("  2. Log in as your Reddit account")
    print("  3. Click 'create another app' → type: script")
    print("     redirect uri: http://localhost:8080")
    print("  4. Copy client_id (short string under app name) + secret")
    print("  5. Add to backend/.env:")
    print("       REDDIT_CLIENT_ID=<value>")
    print("       REDDIT_CLIENT_SECRET=<value>")
    print("       REDDIT_USER_AGENT=python:PsychographicLeads:1.0 (by u/YourUsername)")
    print()
    sys.exit(1)

# ── Step 2: Import PRAW ───────────────────────────────────────────────────────

_section("Step 2 — PRAW Import Check")

try:
    import praw
    import prawcore
    _bar("praw", f"version {praw.__version__}")
except ImportError:
    print("  ✗  praw is not installed. Run: pip install praw==7.7.1")
    sys.exit(1)

# ── Step 3: Initialise PRAW (Application-Only OAuth) ─────────────────────────

_section("Step 3 — OAuth Token Acquisition")

print(f"  Connecting to Reddit API with client_id={settings.REDDIT_CLIENT_ID[:6]}...")

try:
    reddit = praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent=settings.REDDIT_USER_AGENT,
    )
    # Accessing reddit.auth.limits triggers the OAuth token request.
    # We use a cheap subreddit fetch to confirm the token actually works.
    t0 = time.time()
    sub = reddit.subreddit("redditdev")
    title = sub.title   # this makes the actual HTTP request
    elapsed = time.time() - t0
    _bar("OAuth token", f"acquired in {elapsed:.2f}s")
    _bar("Test subreddit", f"r/redditdev — title={title!r}")
except prawcore.exceptions.ResponseException as exc:
    print(f"  ✗  OAuth failed: HTTP {exc.response.status_code}")
    if exc.response.status_code == 401:
        print("      → CLIENT_ID or CLIENT_SECRET is wrong.")
        print("        Check reddit.com/prefs/apps for the correct values.")
    elif exc.response.status_code == 403:
        print("      → App credentials rejected. Ensure the app type is 'script'.")
    sys.exit(1)
except Exception as exc:
    print(f"  ✗  Connection failed: {type(exc).__name__}: {exc}")
    print("      → Is the network reachable? Try: curl https://www.reddit.com")
    sys.exit(1)

# ── Step 4: Subreddit search ──────────────────────────────────────────────────

_section("Step 4 — Live Subreddit Search")

TEST_SUBREDDIT = "yoga"
TEST_KEYWORD   = "yoga mat"

print(f"  Searching r/{TEST_SUBREDDIT} for '{TEST_KEYWORD}'...")

authors: list[str] = []
try:
    t0 = time.time()
    subreddit = reddit.subreddit(TEST_SUBREDDIT)
    count = 0
    for submission in subreddit.search(TEST_KEYWORD, limit=5, sort="relevance"):
        count += 1
        if submission.author:
            authors.append(str(submission.author.name))
            print(f"    Post: [{submission.score:4d}↑] {submission.title[:60]!r}")
            print(f"          Author: u/{submission.author.name}")
    elapsed = time.time() - t0
    _bar("Posts found", f"{count} posts in {elapsed:.2f}s")
    _bar("Authors collected", f"{len(authors)} unique authors")
except Exception as exc:
    print(f"  ✗  Search failed: {type(exc).__name__}: {exc}")
    sys.exit(1)

if not authors:
    print("  ✗  No post authors found — search returned posts but all have deleted authors.")
    print("      Try a different keyword or subreddit.")
    sys.exit(1)

# ── Step 5: User profile fetch ────────────────────────────────────────────────

_section("Step 5 — User Profile Retrieval")

test_user = authors[0]
print(f"  Fetching profile for u/{test_user}...")

try:
    t0 = time.time()
    redditor = reddit.redditor(test_user)
    # Access .id to trigger full profile fetch
    user_id       = str(redditor.id)
    link_karma    = getattr(redditor, "link_karma", 0)
    comment_karma = getattr(redditor, "comment_karma", 0)
    total_karma   = link_karma + comment_karma
    is_suspended  = getattr(redditor, "is_suspended", False)
    bio_text = ""
    try:
        sub_info = getattr(redditor, "subreddit", {})
        bio_text = (sub_info or {}).get("public_description", "") or ""
    except Exception:
        pass
    elapsed = time.time() - t0

    _bar("User ID",      user_id)
    _bar("Karma",        f"{total_karma:,} (link={link_karma:,} comment={comment_karma:,})")
    _bar("Suspended",    str(is_suspended))
    _bar("Bio",          (bio_text[:80] + "...") if len(bio_text) > 80 else (bio_text or "(empty)"))
    _bar("Fetch time",   f"{elapsed:.2f}s")

except Exception as exc:
    print(f"  ✗  Profile fetch failed: {type(exc).__name__}: {exc}")
    sys.exit(1)

# ── Step 6: Content collection ────────────────────────────────────────────────

_section("Step 6 — Content Collection (Posts + Comments)")

print(f"  Fetching recent posts/comments for u/{test_user}...")

content_count = 0
try:
    t0 = time.time()
    for item in redditor.new(limit=5):
        if hasattr(item, "title"):
            text = f"{item.title} {item.selftext or ''}".strip()
            ctype = "post"
        else:
            text = item.body or ""
            ctype = "comment"

        if not text or text in ("[deleted]", "[removed]"):
            continue

        content_count += 1
        preview = text[:70].replace("\n", " ")
        print(f"    [{ctype:7s}] score={item.score:4d}  {preview!r}")

    elapsed = time.time() - t0
    _bar("Content items", f"{content_count} items in {elapsed:.2f}s")

except Exception as exc:
    print(f"  ✗  Content fetch failed: {type(exc).__name__}: {exc}")
    sys.exit(1)

# ── Step 7: Rate limit check ──────────────────────────────────────────────────

_section("Step 7 — Rate Limit Status")

try:
    limits = reddit.auth.limits
    used      = limits.get("used",      "unknown")
    remaining = limits.get("remaining", "unknown")
    reset_ts  = limits.get("reset_timestamp")
    reset_str = f"{int(reset_ts - time.time())}s" if reset_ts else "unknown"
    _bar("Requests used (this window)", str(used))
    _bar("Requests remaining",          str(remaining))
    _bar("Window resets in",            reset_str)
    print()
    print(f"  Reddit allows 60 requests/minute for Application-Only OAuth.")
    print(f"  A 25-user discovery run uses approximately 50-100 requests.")
except Exception as exc:
    _bar("Rate limit info", f"unavailable ({exc})", ok=False)

# ── Summary ───────────────────────────────────────────────────────────────────

_section("Reddit Provider — Ready")

print()
print("  ✓  OAuth authentication: working")
print("  ✓  Subreddit search: working")
print(f"  ✓  Authors discovered: {len(authors)} from r/{TEST_SUBREDDIT}")
print(f"  ✓  User profile fetch: working (u/{test_user})")
print(f"  ✓  Content collection: {content_count} items")
print()
print("  The Reddit provider is ready. Next steps:")
print()
print("  1. Verify .env has the correct credentials:")
print(f"       REDDIT_CLIENT_ID={settings.REDDIT_CLIENT_ID}")
print(f"       REDDIT_USER_AGENT={settings.REDDIT_USER_AGENT}")
print()
print("  2. Start the backend:")
print("       uvicorn app.main:app --reload --port 8000")
print()
print("  3. Create a product and trigger discovery:")
print("       POST /api/v1/products/")
print("       POST /api/v1/products/{id}/discovery/start")
print()
sys.exit(0)
