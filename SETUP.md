# Setup — developer does this ONCE (~15 min)

The app itself needs zero config. It just needs one Google file: `client_secret.json`.

## 1. Create the Google file

1. Go to https://console.cloud.google.com → sign in with YOUR Google account
2. Top bar → project dropdown → **New Project** → name it `grandma-uploads` → Create
3. Menu ☰ → **APIs & Services → Library** → search **YouTube Data API v3** → click → **Enable**
4. **APIs & Services → OAuth consent screen** (left sidebar)
   - User type: **External** → Create
   - App name: `Grandma Uploads`, your email → Save
   - Skip scopes/pages, add yourself as **Test user** → Save
5. **APIs & Services → Credentials → + Create Credentials → OAuth client ID**
   - Type: **Web application**
   - Authorized redirect URIs: add `http://localhost:8000/callback`
   - **Download** the JSON → rename to `client_secret.json` → put it in this folder (next to `app.py`)

## 2. Run

```bash
pip3 install -r requirements.txt
python3 app.py
```

Open http://localhost:8000 → Sign in → upload.

## 3. While in "Testing" mode (first 7 days)

Consent screen in Testing mode = only listed test users can sign in, and refresh tokens die after 7 days. Fixes:
- Add each elder's Google account as a **Test user** (consent screen → Test users), OR
- **Publish** the app (consent screen → Publish to production). It shows "unverified" warning — click "Advanced → Go to app" — fine for <100 users.

## 4. Make uploads go PUBLIC (not locked private) — free, one form

New API projects lock API uploads to private until audited. Submit:
https://support.google.com/youtube/contact/yt_api_form

- Describe: "Web tool for channel owners to upload their own videos to their own channels via the YouTube Data API."
- Takes ~4–10 days. Until then uploads may land as "locked private" — re-upload later or publish via Studio.

## Files

```
app.py              the whole app
client_secret.json  you create this (step 1)
tokens/             saved logins, one per channel (auto)
uploads_log.json    upload history (auto)
```
