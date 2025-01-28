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
    city VARCHAR(255) NOT NULL,
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
    city VARCHAR(255),
    rooms_count INTEGER[] NOT NULL,
    price_min NUMERIC,
    price_max NUMERIC
);

-- Add the unique constraint so that ON CONFLICT(user_id) works
ALTER TABLE user_filters
  ADD CONSTRAINT user_filters_user_id_unique UNIQUE (user_id);