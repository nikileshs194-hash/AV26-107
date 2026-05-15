-- JeevanSetu — Full Supabase Migration
-- Run this in: Supabase Dashboard → SQL Editor → New Query → Run All

-- ── Users ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.users (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone               VARCHAR(20) UNIQUE NOT NULL,
  full_name           VARCHAR(100),
  age                 INTEGER,
  gender              VARCHAR(20),
  latitude            FLOAT,
  longitude           FLOAT,
  push_token          TEXT,
  location_updated_at TIMESTAMPTZ,
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ── OTP sessions ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.otp_sessions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone       VARCHAR(20) NOT NULL,
  otp         VARCHAR(6)  NOT NULL,
  expires_at  TIMESTAMPTZ NOT NULL,
  verified    BOOLEAN DEFAULT FALSE,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── SOS requests ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.sos_requests (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone           VARCHAR(20),
  name            TEXT,
  age             INTEGER,
  latitude        FLOAT,
  longitude       FLOAT,
  address         TEXT,
  google_maps_url TEXT,
  severity        TEXT,
  status          TEXT DEFAULT 'active',
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Alerts log ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.alerts (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source      TEXT,
  severity    TEXT,
  title       TEXT,
  description TEXT,
  latitude    FLOAT,
  longitude   FLOAT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── User-saved alerts (Alerts tab) ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.user_alerts (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone        TEXT,
  alert_id     TEXT,
  title        TEXT,
  description  TEXT,
  severity     TEXT,
  source       TEXT,
  location     TEXT,
  icon         TEXT,
  icon_bg      TEXT,
  icon_color   TEXT,
  border_color TEXT,
  when_text    TEXT,
  when_color   TEXT,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (phone, alert_id)
);

-- ── Emergency shelters ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.shelters (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name         TEXT,
  latitude     FLOAT,
  longitude    FLOAT,
  capacity     INTEGER,
  address      TEXT
);

-- ── Chat messages ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.chat_messages (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone      TEXT,
  role       TEXT,
  content    TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_otp_phone        ON public.otp_sessions  (phone);
CREATE INDEX IF NOT EXISTS idx_users_phone      ON public.users          (phone);
CREATE INDEX IF NOT EXISTS idx_sos_phone        ON public.sos_requests   (phone);
CREATE INDEX IF NOT EXISTS idx_sos_status       ON public.sos_requests   (status);
CREATE INDEX IF NOT EXISTS idx_user_alerts_phone ON public.user_alerts   (phone);
CREATE INDEX IF NOT EXISTS idx_chat_phone       ON public.chat_messages  (phone);

-- ── Disable RLS (service key access only) ────────────────────────────────────
ALTER TABLE public.users          DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.otp_sessions   DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.sos_requests   DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.alerts         DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_alerts    DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.shelters       DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages  DISABLE ROW LEVEL SECURITY;
