"""
Reddit provider verification — tests the full Reddit discovery pipeline.

Architecture: Public JSON API (httpx) — NO CLIENT_ID or CLIENT_SECRET needed.
Only REDDIT_USER_AGENT is required.

If www.reddit.com returns 403 from your IP, deploy to Railway/Render or use a VPN.

Run:
  cd backend
  python verify_reddit.py
"""
import asyncio, sys
import httpx

sys.stdout.reconfigure(encoding='utf-8')


async def main():
    print("=" * 60)
    print("REDDIT PROVIDER VERIFICATION (public JSON API)")
    print("=" * 60)

    from app.config import settings

    # 1. Config
    print(f"\n[1] Config")
    print(f"  reddit_credentials_configured(): {settings.reddit_credentials_configured()}")
    print(f"  REDDIT_USER_AGENT: {settings.REDDIT_USER_AGENT}")
    print(f"  CLIENT_ID/SECRET: NOT required (public JSON API)")

    # 2. Network connectivity
    print(f"\n[2] Network connectivity")
    ua = settings.REDDIT_USER_AGENT or "python:test:1.0"
    test_urls = [
        ("Public JSON", "https://www.reddit.com/r/india/new.json", {"limit": 1}),
        ("Subreddit search", "https://www.reddit.com/r/fitness/search.json",
         {"q": "workout", "restrict_sr": "1", "limit": 1}),
        ("User about", "https://www.reddit.com/user/reddit/about.json", {}),
    ]
    network_ok = False
    for name, url, params in test_urls:
        try:
            r = httpx.get(url, params=params,
                headers={"User-Agent": ua}, timeout=10, follow_redirects=True)
            if r.status_code == 200:
                data = r.json()
                print(f"  OK  {name}: HTTP {r.status_code}")
                network_ok = True
            else:
                print(f"  BLOCKED {name}: HTTP {r.status_code} (IP blocked by Reddit CDN)")
        except Exception as e:
            print(f"  ERROR {name}: {e}")

    if not network_ok:
        print("""
  DIAGNOSIS: Reddit is blocking this IP address.
  This is a network restriction, NOT a code or credential error.

  The public JSON API works from:
    - Home/residential ISP connections (most reliable)
    - US/EU cloud servers (Railway, Render, DigitalOcean)

  Solutions:
    1. Deploy to Railway (recommended — uses clean IPs)
    2. Use a residential VPN
    3. Enable YouTube provider (YOUTUBE_API_KEY) as alternative
    4. The mock provider will be used automatically as fallback
""")
        return

    # 3. Provider health check
    print(f"\n[3] Provider health check")
    from app.ml.discovery.reddit_provider import RedditProvider
    p = RedditProvider()
    health = await p.health_check()
    icon = "OK" if health["ok"] else "FAIL"
    print(f"  {icon}: {health['detail']}")

    # 4. User discovery
    print(f"\n[4] User discovery (keywords: fitness, workout)")
    users = await p.discover_users(
        keywords=["fitness app", "workout tracker", "weight loss"],
        target_city=None,
        max_users=5,
        search_config={},
    )
    print(f"  Discovered: {len(users)} users")
    for u in users[:3]:
        print(f"    @{u.username} | karma={u.follower_count} | via=r/{u.discovered_via}")
        if u.bio:
            print(f"    bio: {u.bio[:80]}")

    # 5. Content collection
    if users:
        print(f"\n[5] Content collection for @{users[0].username}")
        items = await p.collect_content(users[0], max_items=5)
        print(f"  Collected: {len(items)} items")
        for it in items[:3]:
            print(f"    [{it.content_type}] engagement={it.engagement} | {repr(it.content_text[:80])}")

    print("\n" + "=" * 60)
    print("RESULT: Reddit public JSON API is working from this IP.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
