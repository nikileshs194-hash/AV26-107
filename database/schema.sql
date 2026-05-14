-- USERS TABLE
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT,
    phone TEXT,
    latitude FLOAT,
    longitude FLOAT,
    status TEXT
);

-- FLOOD_ZONES TABLE
CREATE TABLE flood_zones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    area_name TEXT,
    risk_level TEXT,
    coordinates JSONB
);

-- SOS_REQUESTS TABLE
CREATE TABLE sos_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    latitude FLOAT,
    longitude FLOAT,
    severity TEXT,
    status TEXT
);

-- SHELTERS TABLE
CREATE TABLE shelters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shelter_name TEXT,
    latitude FLOAT,
    longitude FLOAT,
    capacity INTEGER
);
