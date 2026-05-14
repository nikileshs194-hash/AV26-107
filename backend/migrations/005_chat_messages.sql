-- Run in Supabase SQL Editor → SQL Editor → New query

-- Chat messages table (one row per message, cleared every day at midnight IST)
CREATE TABLE IF NOT EXISTS public.chat_messages (
  id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  phone      VARCHAR(20)  NOT NULL,
  role       VARCHAR(10)  NOT NULL,          -- 'user' | 'assistant'
  content    TEXT         NOT NULL,
  created_at TIMESTAMPTZ  DEFAULT NOW()
);

-- Fast lookups by phone + date
CREATE INDEX IF NOT EXISTS idx_chat_phone_date
  ON public.chat_messages (phone, created_at DESC);

-- No RLS — service key only, same pattern as other tables
ALTER TABLE public.chat_messages DISABLE ROW LEVEL SECURITY;
