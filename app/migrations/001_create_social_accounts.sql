-- Migration: Create social_accounts table
-- Run this migration to set up YouTube OAuth token storage

CREATE TABLE IF NOT EXISTS social_accounts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

  -- Platform identification
  platform        VARCHAR(50) NOT NULL DEFAULT 'youtube',  -- 'youtube', 'twitter', etc.
  platform_user_id VARCHAR(255) NOT NULL,                  -- YouTube channel ID
  platform_username VARCHAR(255),                          -- YouTube display name
  platform_email  VARCHAR(255),                            -- Google account email
  avatar_url      TEXT,

  -- OAuth tokens (store encrypted in production)
  access_token    TEXT NOT NULL,
  refresh_token   TEXT,                                    -- NULL if not provided by platform
  token_type      VARCHAR(50) DEFAULT 'Bearer',
  scope           TEXT,                                    -- Space-separated granted scopes
  expires_at      TIMESTAMPTZ,                             -- When access_token expires

  -- Metadata
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  connected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_refreshed_at TIMESTAMPTZ,
  disconnected_at TIMESTAMPTZ,

  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Prevent duplicate platform accounts per user
  UNIQUE (user_id, platform, platform_user_id)
);

-- Index for fast lookups by user
CREATE INDEX IF NOT EXISTS idx_social_accounts_user_id
  ON social_accounts(user_id);

-- Index for finding by platform user ID (e.g. re-connecting)
CREATE INDEX IF NOT EXISTS idx_social_accounts_platform_user
  ON social_accounts(platform, platform_user_id);

-- Index for active accounts
CREATE INDEX IF NOT EXISTS idx_social_accounts_active
  ON social_accounts(user_id, platform, is_active)
  WHERE is_active = TRUE;

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_social_accounts_updated_at
  BEFORE UPDATE ON social_accounts
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- OAuth state table (CSRF protection for the OAuth flow)
CREATE TABLE IF NOT EXISTS oauth_states (
  state       VARCHAR(128) PRIMARY KEY,
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  platform    VARCHAR(50) NOT NULL DEFAULT 'youtube',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at  TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '10 minutes')
);

-- Clean up expired states automatically (run via cron or on each request)
CREATE INDEX IF NOT EXISTS idx_oauth_states_expires
  ON oauth_states(expires_at);
