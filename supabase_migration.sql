-- Run this in your Supabase SQL Editor (Dashboard → SQL Editor → New query)

-- Users table
CREATE TABLE IF NOT EXISTS public.users (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone       VARCHAR(20) UNIQUE NOT NULL,
  full_name   VARCHAR(100),
  age         INTEGER,
  gender      VARCHAR(20),
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- OTP sessions table
CREATE TABLE IF NOT EXISTS public.otp_sessions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone       VARCHAR(20) NOT NULL,
  otp         VARCHAR(6)  NOT NULL,
  expires_at  TIMESTAMPTZ NOT NULL,
  verified    BOOLEAN DEFAULT FALSE,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_otp_phone ON public.otp_sessions (phone);
CREATE INDEX IF NOT EXISTS idx_users_phone ON public.users (phone);

-- Allow public access via service key (RLS disabled for simplicity)
ALTER TABLE public.users         DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.otp_sessions  DISABLE ROW LEVEL SECURITY;
