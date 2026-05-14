-- Run this in Supabase SQL Editor

-- Extend sos_requests with full victim details
ALTER TABLE sos_requests ADD COLUMN IF NOT EXISTS phone            TEXT;
ALTER TABLE sos_requests ADD COLUMN IF NOT EXISTS name             TEXT;
ALTER TABLE sos_requests ADD COLUMN IF NOT EXISTS age              INTEGER;
ALTER TABLE sos_requests ADD COLUMN IF NOT EXISTS address          TEXT;
ALTER TABLE sos_requests ADD COLUMN IF NOT EXISTS google_maps_url  TEXT;
ALTER TABLE sos_requests ADD COLUMN IF NOT EXISTS notified_count   INTEGER DEFAULT 0;

-- Add Expo push token to users (for receiving SOS notifications)
ALTER TABLE users ADD COLUMN IF NOT EXISTS push_token TEXT;

-- Reload PostgREST schema cache
NOTIFY pgrst, 'reload schema';
