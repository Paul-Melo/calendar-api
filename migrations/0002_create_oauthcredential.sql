-- Migration: Create table OAuthCredential to persist OAuth tokens
-- SQL compatible with PostgreSQL / MySQL. Adjust types for SQLite if needed.

CREATE TABLE IF NOT EXISTS oauth_credential (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(200),
    token TEXT NOT NULL,
    refresh_token TEXT,
    token_uri VARCHAR(200),
    scopes TEXT,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now(),
    user_id INTEGER
);

-- Add foreign key to users (if using Postgres/MySQL)
-- ALTER TABLE oauth_credential
-- ADD CONSTRAINT fk_oauth_user FOREIGN KEY (user_id) REFERENCES "user" (id);

-- Note for SQLite: SERIAL is not supported; use INTEGER PRIMARY KEY AUTOINCREMENT.
-- If using Alembic/Flask-Migrate, convert the SQL into an Alembic revision.
