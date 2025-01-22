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
    title TEXT NOT NULL,
    price NUMERIC NOT NULL,
    rooms_count INTEGER NOT NULL,
    city VARCHAR(255) NOT NULL,
    insert_time TIMESTAMP,
    image_url TEXT,
    address TEXT,
    square_feet INTEGER,
    floor INTEGER,
    total_floors INTEGER,
    description TEXT,
    resource_url TEXT
);

CREATE TABLE IF NOT EXISTS user_filters (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    property_type VARCHAR(50),
    city VARCHAR(255),
    rooms_count INTEGER[] NOT NULL,
    price_min NUMERIC,
    price_max NUMERIC,
    listing_date VARCHAR(50)
);
