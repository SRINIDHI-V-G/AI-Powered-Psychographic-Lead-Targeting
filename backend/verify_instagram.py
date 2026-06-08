"""
Instagram provider verification — tests the full Instagram discovery pipeline.

Architecture: instagrapi (Instagram private mobile API).
  No OAuth required. Uses username+password or session ID.

If you get "IP blacklisted", deploy to Railway or use a VPN.
To bypass IP blocks: get your session ID from your phone/browser and
set INSTAGRAM_SESSION_ID in .env.

Run:
  cd backend
  python verify_instagram.py
"""
import asyncio, sys, os
import httpx

sys.stdout.reconfigure(encoding='utf-8')


def get_session_id_instructions() -> str:
    return """
HOW TO GET YOUR INSTAGRAM SESSION ID:
  1. Open Instagram in Chrome/Firefox (logged in as mbasuccessdesk)
  2. Press F12 → Application tab → Cookies → www.instagram.com
  3. Find the cookie named 'sessionid'
  4. Copy the value (long string like 'XXXXXXX%3AYYYYYYY%3AZ')
  5. Set INSTAGRAM_SESSION_ID=<that value> in backend/.env
  6. Restart backend and run verify_instagram.py again
"""


async def main():
    print("=" * 60)
    print("INSTAGRAM PROVIDER VERIFICATION (instagrapi)")
    print("=" * 60)

    from app.config import settings

    # 1. Config
    print(f"\n[1] Config")
    print(f"  instagram_credentials_configured(): {settings.instagram_credentials_configured()}")
    print(f"  INSTAGRAM_USERNAME: {settings.INSTAGRAM_USERNAME}")
    print(f"  INSTAGRAM_PASSWORD: {'*' * len(settings.INSTAGRAM_PASSWORD) if settings.INSTAGRAM_PASSWORD else '(not set)'}")
    print(f"  INSTAGRAM_SESSION_ID: {'set' if settings.INSTAGRAM_SESSION_ID else '(not set)'}")
    print(f"  INSTAGRAM_SESSION_FILE: {settings.INSTAGRAM_SESSION_FILE}")
    session_file_exists = os.path.exists(settings.INSTAGRAM_SESSION_FILE)
    print(f"  Session file exists: {session_file_exists}")

    # 2. Network connectivity
    print(f"\n[2] Network connectivity")
    try:
        r = httpx.get("https://www.instagram.com/",
            headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"},
            timeout=10, follow_redirects=True)
        print(f"  instagram.com: HTTP {r.status_code}")
        web_ok = r.status_code == 200
    except Exception as e:
        print(f"  instagram.com: ERROR {e}")
        web_ok = False

    # Test mobile API endpoint (what instagrapi uses)
    try:
        r2 = httpx.get("https://i.instagram.com/api/v1/accounts/login/",
            headers={"User-Agent": "Instagram 269.0.0.18.75 Android"},
            timeout=10, follow_redirects=True)
        print(f"  i.instagram.com (mobile API): HTTP {r2.status_code}")
        mobile_ok = r2.status_code in (200, 400, 405)
    except Exception as e:
        print(f"  i.instagram.com (mobile API): ERROR {e}")
        mobile_ok = False

    if web_ok and not mobile_ok:
        print(f"\n  DIAGNOSIS: Instagram web is accessible but mobile API is blocked.")
        print(f"  The instagrapi library uses the mobile API — it won't work from this IP.")
        print(get_session_id_instructions())

    # 3. Provider init
    print(f"\n[3] Provider initialization")
    try:
        from app.ml.discovery.instagram_provider import InstagramProvider
        p = InstagramProvider()
        print(f"  OK: InstagramProvider initialized")

        # 4. Health check
        print(f"\n[4] Health check")
        health = await p.health_check()
        icon = "OK" if health["ok"] else "FAIL"
        print(f"  {icon}: {health['detail']}")

        if health["ok"]:
            # 5. User discovery
            print(f"\n[5] User discovery (hashtags: interior, homedecor)")
            users = await p.discover_users(
                keywords=["interior design", "home decor", "luxury sofa"],
                target_city="Chennai",
                max_users=5,
                search_config={},
            )
            print(f"  Discovered: {len(users)} users")
            for u in users[:3]:
                print(f"    @{u.username} | followers={u.follower_count}")
                if u.bio:
                    print(f"    bio: {u.bio[:80]}")

            if users:
                print(f"\n[6] Content collection for @{users[0].username}")
                items = await p.collect_content(users[0], max_items=5)
                print(f"  Collected: {len(items)} items")
                for it in items[:3]:
                    print(f"    [{it.content_type}] {repr(it.content_text[:80])}")

    except RuntimeError as e:
        err = str(e)
        if "blacklist" in err.lower() or "ip" in err.lower():
            print(f"  IP BLOCKED: {err}")
            print(get_session_id_instructions())
        else:
            print(f"  ERROR: {err}")
    except Exception as e:
        print(f"  ERROR ({type(e).__name__}): {e}")

    print("\n" + "=" * 60)
    print("TROUBLESHOOTING GUIDE")
    print("=" * 60)
    print("""
  'IP blacklisted':
    → Your server's IP is banned by Instagram's mobile API
    → Deploy to Railway (recommended) or use a VPN
    → OR set INSTAGRAM_SESSION_ID from your phone browser

  'LoginRequired':
    → Session file is stale or browser-derived
    → Delete instagram_session.json and run again
    → OR set INSTAGRAM_SESSION_ID

  'ChallengeRequired':
    → Instagram wants verification (suspicious login from new IP)
    → Log in manually on Instagram app, approve the login
    → OR use a different dedicated account
""")


if __name__ == "__main__":
    asyncio.run(main())
