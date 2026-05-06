-- Migration: Add drift detection fields to confluence_pages table
-- Run once against the live database (Render PostgreSQL)
--
-- Usage:
--   psql $DATABASE_URL -f scripts/migrate_add_confluence_drift_fields.sql
--
-- Safe to run multiple times — IF NOT EXISTS guards prevent errors on re-run.

ALTER TABLE confluence_pages
    ADD COLUMN IF NOT EXISTS drift_risk         VARCHAR(10),
    ADD COLUMN IF NOT EXISTS last_activity_date TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS confluence_topics  TEXT[];

-- Index drift_risk for fast "show me all outdated docs" queries
CREATE INDEX IF NOT EXISTS idx_confluence_drift_risk
    ON confluence_pages (drift_risk)
    WHERE drift_risk IS NOT NULL;
