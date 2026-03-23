# YouTube OAuth2 Social Account Service — FastAPI

Python + FastAPI + asyncpg service for verifying YouTube account ownership via Google OAuth2, storing tokens in PostgreSQL.

---

## Project Structure

```
app/
├── main.py                          # FastAPI app, middleware, lifespan
├── config.py                        # Settings via pydantic-settings
├── db/
│   ├── pool.py                      # asyncpg pool + async query helpers
│   └── migrate.py                   # Migration runner
├── models/
│   └── schemas.py                   # Pydantic v2 request/response models
├── services/
│   ├── google_oauth.py              # Google API calls (auth URL, token exchange, etc.)
│   ├── social_account_repository.py # All DB operations for social_accounts
│   └── token_refresh.py             # Automatic token refresh logic
├── routes/
│   └── social_accounts.py           # FastAPI router with all endpoints
└── middleware/
    └── auth.py                      # requireAuth FastAPI dependency

migrations/
└── 001_create_social_accounts.sql   # social_accounts + oauth_states tables
```

---

## Setup

### 1. Google Cloud Console

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. **APIs & Services** → **Enable APIs** → enable **YouTube Data API v3**
3. **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
4. Application type: **Web application**
5. Add authorized redirect URI: `http://localhost:8000/auth/youtube/callback`
6. Copy **Client ID** and **Client Secret**

### 2. Environment

```bash
cp .env.example .env
# Fill in: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, DATABASE_URL, SESSION_SECRET_KEY

# Generate a session secret:
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Database

```bash
psql -U postgres -c "CREATE DATABASE sentiment_app;"
python -m app.db.migrate
```

### 4. Install & Run

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Development (with auto-reload)
uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Browse the interactive docs at **http://localhost:8000/docs**

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | — | DB health check |
| `GET` | `/social-accounts` | ✓ | List connected accounts |
| `GET` | `/social-accounts/youtube/connect` | ✓ | Start OAuth → redirects to Google |
| `GET` | `/auth/youtube/callback` | — | Google callback (do not call directly) |
| `DELETE` | `/social-accounts/{id}` | ✓ | Disconnect + revoke account |

### `GET /social-accounts`
```json
{
  "success": true,
  "count": 1,
  "data": [{
    "id": "uuid",
    "platform": "youtube",
    "platform_username": "@mychannel",
    "platform_email": "user@gmail.com",
    "avatar_url": "https://...",
    "is_active": true,
    "connected_at": "2024-01-01T00:00:00Z"
  }]
}
```

### `DELETE /social-accounts/{id}`
```json
{ "success": true, "message": "Social account disconnected successfully." }
```

---

## Token Refresh

### On-demand (inside a request)
```python
from app.services.token_refresh import get_valid_access_token

# Auto-refreshes if expired or expiring within 5 minutes
token = await get_valid_access_token(account_id, user_id)
```

### Scheduled (background task / cron)
```python
from app.services.token_refresh import refresh_expiring_tokens

# Run every 30 min via APScheduler, Celery Beat, or similar
await refresh_expiring_tokens(all_active_accounts)
```

---

## Database Schema

```sql
social_accounts
├── id                UUID PK
├── user_id           UUID FK → users(id)
├── platform          VARCHAR        -- 'youtube'
├── platform_user_id  VARCHAR        -- YouTube channel ID
├── platform_username VARCHAR        -- @handle or display name
├── platform_email    VARCHAR        -- Google account email
├── avatar_url        TEXT
├── access_token      TEXT           -- ⚠ Encrypt at rest in production
├── refresh_token     TEXT           -- ⚠ Encrypt at rest in production
├── token_type        VARCHAR        -- 'Bearer'
├── scope             TEXT           -- Space-separated granted scopes
├── expires_at        TIMESTAMPTZ
├── is_active         BOOLEAN
├── connected_at      TIMESTAMPTZ
├── last_refreshed_at TIMESTAMPTZ
└── disconnected_at   TIMESTAMPTZ

oauth_states                         -- CSRF protection (10-min TTL)
├── state   VARCHAR PK
├── user_id UUID FK
└── expires_at TIMESTAMPTZ
```

---

## Security Checklist

| Concern | Solution |
|---|---|
| CSRF on OAuth | `oauth_states` table — one-time, 10-min TTL |
| Token storage | Encrypt with `cryptography` / AWS KMS before storing |
| Expired tokens | Auto-refresh within 5-min buffer; error prompts reconnect |
| Disconnect | Revoke with Google + wipe from DB atomically |
| Session fixation | `SessionMiddleware` with `https_only=True` + `same_site=lax` in prod |
| Token exposure | `SocialAccountInternal` never returned from API endpoints |
