-- Migration: Add unique constraint to prevent double-booking
-- Applies for PostgreSQL / MySQL. For SQLite, follow the note below.

-- PostgreSQL / MySQL
ALTER TABLE appointment
ADD CONSTRAINT uq_appointment_date_service UNIQUE (appointment_date, service_type);

-- Notes for SQLite:
-- SQLite does not support ALTER TABLE ADD CONSTRAINT for UNIQUE on existing tables.
-- Recommended approach for SQLite:
-- 1. Create a new table with desired constraints (including UNIQUE).
-- 2. Copy data: INSERT INTO new_appointment(col...) SELECT col... FROM appointment;
-- 3. DROP TABLE appointment;
-- 4. ALTER TABLE new_appointment RENAME TO appointment;

-- Before applying migration:
-- - Backup your DB
-- - Test the migration in a staging environment
-- - If using Alembic/Flask-Migrate, convert the SQL above into an Alembic revision
