-- Migration: 002_create_sentiment_tables.sql
-- All tables needed for YouTube sentiment analysis
-- Run AFTER 001_create_social_accounts.sql

-- ─────────────────────────────────────────────────────────────────────────────
-- ANALYSIS JOBS
-- Tracks each sentiment analysis run requested by a user
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TYPE analysis_status AS ENUM (
  'pending',
  'running',
  'completed',
  'failed',
  'cancelled'
);

CREATE TABLE IF NOT EXISTS analysis_jobs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  social_account_id UUID NOT NULL REFERENCES social_accounts(id) ON DELETE CASCADE,

  -- What to analyse
  target_type       VARCHAR(50) NOT NULL,   -- 'channel', 'video', 'playlist'
  target_id         VARCHAR(255) NOT NULL,  -- YouTube video/channel/playlist ID
  target_title      TEXT,                   -- Human-readable label (fetched from YT)

  -- Job lifecycle
  status            analysis_status NOT NULL DEFAULT 'pending',
  started_at        TIMESTAMPTZ,
  completed_at      TIMESTAMPTZ,
  error_message     TEXT,

  -- Config
  max_comments      INT NOT NULL DEFAULT 500,
  language_filter   VARCHAR(10),            -- e.g. 'en', NULL = all languages

  -- Aggregate results (denormalised for fast dashboard queries)
  total_comments    INT,
  positive_count    INT,
  neutral_count     INT,
  negative_count    INT,
  avg_sentiment     NUMERIC(5, 4),          -- -1.0000 to 1.0000
  sentiment_label   VARCHAR(20),            -- 'positive', 'neutral', 'negative'

  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_user_id    ON analysis_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_account_id ON analysis_jobs(social_account_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status     ON analysis_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON analysis_jobs(created_at DESC);

CREATE TRIGGER update_analysis_jobs_updated_at
  BEFORE UPDATE ON analysis_jobs
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ─────────────────────────────────────────────────────────────────────────────
-- YOUTUBE COMMENTS
-- Raw comments fetched during an analysis job
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS youtube_comments (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id              UUID NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,

  -- YouTube data
  youtube_comment_id  VARCHAR(255) NOT NULL,
  author_name         VARCHAR(255),
  author_channel_id   VARCHAR(255),
  text_original       TEXT NOT NULL,         -- Raw comment text from YouTube
  text_cleaned        TEXT,                  -- Cleaned/normalised version
  like_count          INT NOT NULL DEFAULT 0,
  reply_count         INT NOT NULL DEFAULT 0,
  is_reply            BOOLEAN NOT NULL DEFAULT FALSE,
  parent_comment_id   VARCHAR(255),          -- YouTube parent comment ID (if reply)
  published_at        TIMESTAMPTZ,

  -- Sentiment scores
  sentiment_score     NUMERIC(5, 4),         -- -1.0 (very negative) to 1.0 (very positive)
  sentiment_label     VARCHAR(20),           -- 'positive', 'neutral', 'negative'
  sentiment_confidence NUMERIC(4, 3),        -- 0.000 to 1.000

  -- Detected topics / keywords (array of strings)
  topics              TEXT[],

  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comments_job_id        ON youtube_comments(job_id);
CREATE INDEX IF NOT EXISTS idx_comments_sentiment     ON youtube_comments(job_id, sentiment_label);
CREATE INDEX IF NOT EXISTS idx_comments_yt_id         ON youtube_comments(youtube_comment_id);
CREATE INDEX IF NOT EXISTS idx_comments_published_at  ON youtube_comments(published_at DESC);   