# Pending External Credentials

This document lists all external service credentials that must be configured
by the **project owner or team** before the corresponding features will work.

These credentials were intentionally left unconfigured during development
(intern handover). The system gracefully falls back to mock/simulated
behaviour when credentials are absent — no feature breaks.

---

## 1. Reddit API Credentials

**Required for:** Real Reddit user discovery (Phase B1)

**Current state:** System uses `MockDiscoveryProvider` automatically when
these are absent. The discovery pipeline, DB tables, and API endpoints are
fully implemented and tested. Only the Reddit connection itself requires credentials.

### What to do

1. Create a shared Reddit account for the project (e.g., `psycholead_bot`).
   Use a team/company email — **not a personal account**.

2. Log in to that account and go to:
   https://www.reddit.com/prefs/apps

3. Click **"create an app"** and fill in:
   - **Name:** PsychographicLeads
   - **App type:** `script`
   - **Description:** Lead intelligence platform for psychographic targeting
   - **About URL:** *(leave blank)*
   - **Redirect URI:** `http://localhost` *(required by form, not used)*

4. Click **"create app"**. You will see:
   - A 14-character string under the app name → this is `REDDIT_CLIENT_ID`
   - A string labeled "secret" → this is `REDDIT_CLIENT_SECRET`

5. Add to `backend/.env`:
   ```
   REDDIT_CLIENT_ID=your_14_char_id_here
   REDDIT_CLIENT_SECRET=your_secret_here
   REDDIT_USER_AGENT=python:PsychographicLeads:1.0 (by u/psycholead_bot)
   ```

6. Restart the server. The startup log will confirm:
   ```
   ✓ Reddit credentials configured (client_id=abc123...)
   ```

### Technical details

- Authentication type: **Application-Only OAuth** (RFC 6749 client credentials)
- No end-user Reddit login is required at any point
- Rate limit: 60 requests/minute (PRAW enforces this automatically)
- Access: public content only (same as an unauthenticated browser)
- Cost: **Free**
- Review process: None required for `script` app type

### Data accessed

With these credentials the system can read:
- Public subreddit posts and search results
- Public user profiles (bio, karma score)
- Public post and comment history of users

It cannot access:
- Private subreddits
- Direct messages
- Any content not visible to an unauthenticated browser

---

## 2. YouTube Data API (Phase B2 — Future)

**Required for:** YouTube discovery provider

**Current state:** Not yet implemented.

**Setup when ready:**
- Create a project at https://console.cloud.google.com
- Enable YouTube Data API v3
- Create an API key (server-side, no OAuth needed)
- Add `YOUTUBE_API_KEY=your_key` to `.env`
- Free quota: 10,000 units/day

---

## 3. No Other Credentials Required

The following were explicitly excluded from this project:
- Twitter/X: cost-prohibitive ($100+/month for any meaningful volume)
- LinkedIn: API partner program only, high legal risk
- Facebook: severely restricted post-2018, not feasible
- Instagram: deferred to future evaluation

---

## How to verify credential status

At any time, call the unauthenticated endpoint:

```
GET http://localhost:8000/api/v1/discovery/provider/status
```

Response when unconfigured (mock mode):
```json
{
  "ok": true,
  "provider": "mock",
  "detail": "Mock provider — no external credentials required",
  "mock_mode": true,
  "credentials_configured": false
}
```

Response when configured (real Reddit):
```json
{
  "ok": true,
  "provider": "reddit",
  "detail": "Reddit API responsive, rate limits: {...}",
  "mock_mode": false,
  "credentials_configured": true
}
```
