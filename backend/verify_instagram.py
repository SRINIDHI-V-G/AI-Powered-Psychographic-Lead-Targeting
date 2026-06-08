"""
Instagram provider verification — tests the full Instagram discovery pipeline.

Discovery strategy (no hashtag APIs required):
  Strategy 1 — search_users(keyword)         → users matching keyword in name/bio
  Strategy 2 — seed account comment harvest  → commenters on competitor account posts
  Strategy 3 — profile expansion             → captions + commenters from found users

Run:
  cd backend
  python verify_instagram.py

To use seed account harvesting (highly recommended), set competitor/niche accounts:
  INSTAGRAM_SEED_ACCOUNTS=woodenstreet,urbanladder,pepperfry python verify_instagram.py

Or pass a seed account directly to the discovery call below.
"""
import asyncio
import os
import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")

SEP = "=" * 60


async def main():
    print(SEP)
    print("INSTAGRAM PROVIDER VERIFICATION")
    print(SEP)

    from app.config import settings

    # ── [1] Config ────────────────────────────────────────────────────────────
    print("\n[1] Config")
    print(f"  instagram_credentials_configured(): {settings.instagram_credentials_configured()}")
    print(f"  INSTAGRAM_USERNAME: {settings.INSTAGRAM_USERNAME}")
    pwd_display = "*" * len(settings.INSTAGRAM_PASSWORD) if settings.INSTAGRAM_PASSWORD else "(not set)"
    print(f"  INSTAGRAM_PASSWORD: {pwd_display}")
    print(f"  INSTAGRAM_SESSION_ID: {'set' if settings.INSTAGRAM_SESSION_ID else '(not set)'}")
    print(f"  INSTAGRAM_SESSION_FILE: {settings.INSTAGRAM_SESSION_FILE}")
    print(f"  Session file exists: {os.path.exists(settings.INSTAGRAM_SESSION_FILE)}")
    seed_env = os.environ.get("INSTAGRAM_SEED_ACCOUNTS", "")
    print(f"  INSTAGRAM_SEED_ACCOUNTS: {seed_env or '(not set)'}")

    # ── [2] Network connectivity ──────────────────────────────────────────────
    print("\n[2] Network connectivity")
    try:
        r = httpx.get(
            "https://www.instagram.com/",
            headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"},
            timeout=10, follow_redirects=True,
        )
        print(f"  instagram.com: HTTP {r.status_code}")
    except Exception as e:
        print(f"  instagram.com: ERROR {e}")

    try:
        r2 = httpx.get(
            "https://i.instagram.com/api/v1/accounts/login/",
            headers={"User-Agent": "Instagram 269.0.0.18.75 Android"},
            timeout=10, follow_redirects=True,
        )
        print(f"  i.instagram.com (mobile API): HTTP {r2.status_code}")
    except Exception as e:
        print(f"  i.instagram.com (mobile API): ERROR {e}")

    # ── [3] Provider initialization ───────────────────────────────────────────
    print("\n[3] Provider initialization")
    try:
        from app.ml.discovery.instagram_provider import InstagramProvider
        p = InstagramProvider()
        print("  OK: InstagramProvider initialized")
    except RuntimeError as e:
        print(f"  FAIL: {e}")
        _print_troubleshoot()
        return
    except Exception as e:
        print(f"  FAIL ({type(e).__name__}): {e}")
        _print_troubleshoot()
        return

    # ── [4] Health check ──────────────────────────────────────────────────────
    print("\n[4] Health check")
    health = await p.health_check()
    icon = "OK" if health["ok"] else "FAIL"
    print(f"  {icon}: {health['detail']}")

    if not health["ok"]:
        _print_troubleshoot()
        return

    # ── [5] Strategy 1: Keyword user search ───────────────────────────────────
    print("\n[5] Strategy 1 — Keyword user search")
    print("  Calling search_users('interior design') ...")
    try:
        raw_search = p._api_call(p._client.search_users_v1, "interior design", count=5)
        print(f"  Found {len(raw_search)} accounts")
        for u in raw_search[:3]:
            print(f"    @{u.username} (pk={u.pk})")
        search_ok = len(raw_search) > 0
    except Exception as e:
        print(f"  FAIL: {e}")
        search_ok = False

    # ── [6] Strategy 2: Seed account comment harvesting ──────────────────────
    print("\n[6] Strategy 2 — Seed account comment harvesting")
    seed_account = "woodenstreet"  # change to a real niche account if needed
    print(f"  Looking up seed account @{seed_account} ...")
    seed_ok = False
    try:
        seed_info = p._api_call(p._client.user_info_by_username, seed_account)
        print(f"  Seed: @{seed_info.username} (pk={seed_info.pk}, followers={seed_info.follower_count})")
        medias = p._api_call(p._client.user_medias, seed_info.pk, amount=2)
        print(f"  Recent posts: {len(medias)}")
        total_commenters = 0
        for media in medias:
            caption = (getattr(media, "caption_text", None) or "")[:60]
            comments = p._api_call(p._client.media_comments, media.pk, amount=10)
            total_commenters += len(comments)
            print(f"    post pk={media.pk} caption={repr(caption)!r} comments={len(comments)}")
        print(f"  Total commenters collected: {total_commenters}")
        seed_ok = total_commenters > 0
    except Exception as e:
        print(f"  FAIL: {e}")
        print(f"  (Set INSTAGRAM_SEED_ACCOUNTS=<your_niche_account> to use a different seed)")

    # ── [7] Full discover_users call ──────────────────────────────────────────
    print("\n[7] Full discover_users (keywords + seed accounts)")
    search_config = {}
    if seed_env:
        search_config["seed_accounts"] = [s.strip() for s in seed_env.split(",") if s.strip()]
    elif seed_ok:
        search_config["seed_accounts"] = [seed_account]

    try:
        users = await p.discover_users(
            keywords=["interior design", "home decor", "luxury sofa"],
            target_city="Chennai",
            max_users=5,
            search_config=search_config,
        )
        print(f"  Discovered: {len(users)} users")
        for u in users[:5]:
            method = u.raw_profile.get("discovery_method", "?")
            print(f"    @{u.username} | method={method} | followers={u.follower_count}")
            if u.bio:
                print(f"      bio: {u.bio[:80]}")
    except Exception as e:
        print(f"  FAIL ({type(e).__name__}): {e}")
        users = []

    # ── [8] Content collection ────────────────────────────────────────────────
    if users:
        print(f"\n[8] Content collection for @{users[0].username}")
        try:
            items = await p.collect_content(users[0], max_items=8)
            print(f"  Collected: {len(items)} items")
            for it in items[:5]:
                print(f"    [{it.content_type}] {repr(it.content_text[:80])}")
        except Exception as e:
            print(f"  FAIL: {e}")
            items = []
    else:
        items = []
        print("\n[8] Content collection — skipped (no users discovered)")

    # ── [9] Pipeline integration summary ─────────────────────────────────────
    print(f"\n{SEP}")
    print("VERIFICATION REPORT")
    print(SEP)
    print(f"  Authentication:          {'PASS' if health['ok'] else 'FAIL'}")
    print(f"  Strategy 1 (search):     {'PASS' if search_ok else 'FAIL/EMPTY'}")
    print(f"  Strategy 2 (seed/comments): {'PASS' if seed_ok else 'FAIL/SKIPPED'}")
    print(f"  Users discovered:        {len(users)}")
    print(f"  Content items collected: {len(items)}")

    if users:
        captions = sum(len(u.raw_profile.get("post_captions", [])) for u in users)
        comments = sum(len(u.raw_profile.get("comment_texts", [])) for u in users)
        bios = sum(1 for u in users if u.bio)
        print(f"  Post captions stored:    {captions}")
        print(f"  Comment texts stored:    {comments}")
        print(f"  Bios collected:          {bios}")
        print()
        print("  NLP/OCEAN pipeline: these users feed directly into")
        print("  → NLP processor (content analysis)")
        print("  → OCEAN scorer (personality profiling)")
        print("  → Lead generator (matching against product OCEAN)")
        print("  → Dashboard (leads tab)")

    print(f"\n{SEP}")
    print("MANUAL TESTING COMMANDS")
    print(SEP)
    print("""
  # Verify provider health:
  cd backend && python verify_instagram.py

  # Verify user discovery with seed accounts:
  INSTAGRAM_SEED_ACCOUNTS=woodenstreet,urbanladder python verify_instagram.py

  # Trigger full pipeline via API (backend must be running):
  curl -s -X POST http://localhost:8000/api/v1/products/<product_id>/pipeline/run \\
    -H "X-API-Key: <your_api_key>" | python -m json.tool

  # Check pipeline status:
  curl -s http://localhost:8000/api/v1/products/<product_id>/pipeline/status \\
    -H "X-API-Key: <your_api_key>" | python -m json.tool

  # Check discovered users:
  curl -s "http://localhost:8000/api/v1/products/<product_id>/leads" \\
    -H "X-API-Key: <your_api_key>" | python -m json.tool

  # Dashboard: open http://localhost:3000 → Leads tab
""")

    _print_troubleshoot()


def _print_troubleshoot():
    print(f"""
{SEP}
TROUBLESHOOTING
{SEP}

  'login_required' on ANY endpoint:
    → Your session was loaded but is stale or browser-derived.
    → Delete instagram_session.json and restart.
    → OR get a fresh session from the Instagram mobile app:
      1. Log in on Instagram app
      2. Proxy the traffic (e.g. Proxyman / Charles)
      3. Copy the sessionid cookie value
      4. Set INSTAGRAM_SESSION_ID=<value> in .env

  'login_required' only on hashtag_medias_recent_v1 (old strategy):
    → This is expected — Instagram has blocked hashtag feeds for most sessions.
    → The new strategy (search_users + seed accounts) does NOT use hashtag APIs.
    → This error should NOT appear with the current implementation.

  'IP blacklisted' / 'change your IP':
    → Your server IP is banned by Instagram's mobile API.
    → Deploy to Railway (cloud IPs are usually clean).
    → OR use a residential VPN.

  'ChallengeRequired':
    → Instagram wants phone/email verification for this IP.
    → Log in manually on Instagram app from the same IP (or approve the login).
    → OR use a different dedicated account.

  Strategy 2 (seed accounts) finds 0 commenters:
    → The seed account may have comments disabled or very low engagement.
    → Set INSTAGRAM_SEED_ACCOUNTS to a high-engagement niche account.
    → Examples: woodenstreet, urbanladder, pepperfry (Indian furniture brands)
""")


if __name__ == "__main__":
    asyncio.run(main())
