-- init.sql

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    free_until TIMESTAMP,
    subscription_until TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ads (
    id SERIAL PRIMARY KEY,
    external_id VARCHAR(255) UNIQUE NOT NULL,
    property_type VARCHAR(50) NOT NULL,
    price NUMERIC NOT NULL,
    rooms_count INTEGER NOT NULL,
    city BIGINT NOT NULL,
    insert_time TIMESTAMP,
    address TEXT,
    square_feet NUMERIC,
    floor INTEGER,
    total_floors INTEGER,
    description TEXT,
    resource_url TEXT
);

CREATE TABLE IF NOT EXISTS ad_images (
  id SERIAL PRIMARY KEY,
  ad_id BIGINT REFERENCES ads(id) ON DELETE CASCADE,
  image_url TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS user_filters (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    property_type VARCHAR(50) NOT NULL,
    city BIGINT,
    rooms_count INTEGER[] NOT NULL,
    price_min NUMERIC,
    price_max NUMERIC,
    is_paused BOOLEAN NOT NULL DEFAULT FALSE
);

-- Add the unique constraint so that ON CONFLICT(user_id) works
ALTER TABLE user_filters
  ADD CONSTRAINT user_filters_user_id_unique UNIQUE (user_id);

CREATE TABLE subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    property_type VARCHAR(50),
    city BIGINT,
    rooms_count INTEGER[],
    price_min NUMERIC,
    price_max NUMERIC,
    created_at TIMESTAMP DEFAULT NOW()
);


CREATE TABLE favorite_ads (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    ad_id BIGINT REFERENCES ads(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Possibly you add a unique constraint so user cannot favorite the same ad multiple times
ALTER TABLE favorite_ads
  ADD CONSTRAINT unique_favorite_per_user UNIQUE (user_id, ad_id);


CREATE TABLE IF NOT EXISTS ad_phones (
    id SERIAL PRIMARY KEY,
    ad_id BIGINT REFERENCES ads(id) ON DELETE CASCADE,
    phone TEXT,          -- For phone numbers (e.g., "tel: +380663866058")
    viber_link TEXT      -- For a Viber chat link if available
);

-- High-priority indexes
CREATE INDEX IF NOT EXISTS idx_ads_resource_url ON ads (resource_url);
CREATE INDEX IF NOT EXISTS idx_ad_images_ad_id ON ad_images (ad_id);
CREATE INDEX IF NOT EXISTS idx_ad_phones_ad_id ON ad_phones (ad_id);
CREATE INDEX IF NOT EXISTS idx_ads_insert_time ON ads (insert_time DESC);
CREATE INDEX IF NOT EXISTS idx_favorite_ads_created_at ON favorite_ads (user_id, created_at DESC);

-- Query-specific indexes
CREATE INDEX IF NOT EXISTS idx_ads_filter_query ON ads (city, property_type, price, rooms_count, insert_time DESC);
CREATE INDEX IF NOT EXISTS idx_user_filters_active ON user_filters (user_id, city, property_type)
WHERE is_paused = FALSE;