-- Make sure users table has location columns for "Call Nearby People" feature
ALTER TABLE users ADD COLUMN IF NOT EXISTS latitude  DOUBLE PRECISION;
ALTER TABLE users ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;
ALTER TABLE users ADD COLUMN IF NOT EXISTS location_updated_at TIMESTAMPTZ;

-- Also make sure sos_requests has created_at for time display
ALTER TABLE sos_requests ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

NOTIFY pgrst, 'reload schema';
