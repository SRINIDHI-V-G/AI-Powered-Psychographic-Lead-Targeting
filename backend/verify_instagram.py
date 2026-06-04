"""
Instagram login verifier — handles Bloks push-notification challenge.

FIRST TIME SETUP
----------------
Instagram triggers a "Suspicious login" security challenge the first time
instagrapi (simulated Android device) logs in.  Instagram sends a push
notification to your Instagram app saying "New login from Android — was it you?"

Steps:
  1. Run this script.
  2. Immediately open your Instagram app.
  3. Go to  Settings → Security → Login Activity  (or tap the push notification).
  4. Find the recent Android login and tap  "It was me"  or  "Approve".
  5. Come back — the script retries automatically every 20 s for up to 2 min.
  6. Once approved, a session file is saved.  Future logins skip the challenge.

SUBSEQUENT RUNS
---------------
The saved  instagram_session.json  restores the trusted device fingerprint.
No challenge will appear until the session expires (~2 weeks).

Run:
  cd backend
  venv\\Scripts\\python.exe verify_instagram.py
"""
import sys
import os
import time
import logging

sys.path.insert(0, ".")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from dotenv import load_dotenv
load_dotenv(".env")
from app.config import settings

from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    ChallengeUnknownStep,
    LoginRequired,
)

# ── Helper: attempt one login ─────────────────────────────────────────────────

def _try_login(cl: Client) -> bool:
    """Return True on success, False if challenge is pending, raise on hard error."""
    try:
        cl.login(settings.INSTAGRAM_USERNAME, settings.INSTAGRAM_PASSWORD)
        return True
    except (ChallengeUnknownStep, ChallengeRequired):
        return False


def _save_and_report(cl: Client) -> None:
    info = cl.account_info()
    print(f"\n✓  LOGIN SUCCESS")
    print(f"   Username  : @{info.username}")
    print(f"   Full name : {info.full_name}")
    print(f"   pk        : {info.pk}")
    cl.dump_settings(settings.INSTAGRAM_SESSION_FILE)
    print(f"   Session saved → {settings.INSTAGRAM_SESSION_FILE}")
    print("\nInstagram provider is ready.")
    print("Start the backend server:  uvicorn app.main:app --reload --port 8000")


# ── Main ──────────────────────────────────────────────────────────────────────

print("=" * 62)
print("Instagram session setup")
print("=" * 62)
print(f"Account      : {settings.INSTAGRAM_USERNAME}")
print(f"Session file : {settings.INSTAGRAM_SESSION_FILE}")
print()

cl = Client()
cl.delay_range = [1, 3]

# ── Step 1: try loading an existing valid session ─────────────────────────────
if os.path.exists(settings.INSTAGRAM_SESSION_FILE):
    try:
        cl.load_settings(settings.INSTAGRAM_SESSION_FILE)
        print(f"Loaded saved session from {settings.INSTAGRAM_SESSION_FILE}")
    except Exception as e:
        print(f"Could not load existing session ({e}), starting fresh.")

print("Attempting login ...")
print()

if _try_login(cl):
    _save_and_report(cl)
    sys.exit(0)

# ── Step 2: challenge hit — wait for app approval ─────────────────────────────
print("=" * 62)
print("INSTAGRAM SECURITY CHALLENGE DETECTED")
print("=" * 62)
print()
print("Instagram requires you to approve this login in the Instagram")
print("app on your phone.  Steps:")
print()
print("  1. Open the Instagram app on your phone NOW.")
print("  2. Tap the notification  'New login from Android — was it you?'")
print("     OR go to  Settings (⚙) → Security → Login Activity.")
print("  3. Find the entry labelled 'Android' or 'Unknown device'.")
print("  4. Tap  'It was me'  or  'Approve'.")
print()
print("This script will retry automatically every 20 seconds.")
print("You have 2 minutes.")
print()

RETRY_INTERVAL = 20   # seconds between retries
MAX_WAIT = 120        # seconds total

start = time.time()
attempt = 0

while time.time() - start < MAX_WAIT:
    elapsed = int(time.time() - start)
    remaining = MAX_WAIT - elapsed
    attempt += 1
    print(f"[{elapsed:3d}s] Retry #{attempt} — {remaining}s remaining ...")

    # Fresh client with same device UUID so Instagram recognises the approved device
    cl2 = Client()
    cl2.delay_range = [1, 3]
    if os.path.exists(settings.INSTAGRAM_SESSION_FILE):
        try:
            cl2.load_settings(settings.INSTAGRAM_SESSION_FILE)
        except Exception:
            pass

    try:
        cl2.login(settings.INSTAGRAM_USERNAME, settings.INSTAGRAM_PASSWORD)
        _save_and_report(cl2)
        sys.exit(0)
    except (ChallengeUnknownStep, ChallengeRequired):
        pass  # Still waiting for app approval
    except LoginRequired as e:
        print(f"Login rejected (bad credentials?): {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {type(e).__name__}: {e}")

    time.sleep(RETRY_INTERVAL)

# ── Step 3: timed out ─────────────────────────────────────────────────────────
print()
print("=" * 62)
print("TIMED OUT — App approval not detected within 2 minutes.")
print("=" * 62)
print()
print("Please try again:")
print("  1. Open Instagram app → Settings → Security → Login Activity.")
print("  2. Approve the most recent 'Android' login entry.")
print("  3. Re-run this script immediately after approving.")
print()
print("If you do not have the Instagram app installed:")
print("  • Install Instagram on your phone and log in as @mbasuccessdesk.")
print("  • Then re-run this script.")
sys.exit(1)
