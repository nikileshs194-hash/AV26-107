-- Migration 004: user_alerts table
-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS user_alerts (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  phone       TEXT        NOT NULL,
  alert_id    TEXT        NOT NULL,
  title       TEXT,
  description TEXT,
  severity    TEXT,
  source      TEXT,
  location    TEXT,
  icon        TEXT,
  icon_bg     TEXT,
  icon_color  TEXT,
  border_color TEXT,
  when_text   TEXT,
  when_color  TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(phone, alert_id)
);

-- Index for fast lookup per phone
CREATE INDEX IF NOT EXISTS idx_user_alerts_phone ON user_alerts(phone);

-- Allow Row Level Security (keep service key bypass)
ALTER TABLE user_alerts ENABLE ROW LEVEL SECURITY;

NOTIFY pgrst, 'reload schema';
