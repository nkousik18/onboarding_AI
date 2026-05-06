-- Migration: Add drift detection fields to decisions table
-- Run once against the live database (Render PostgreSQL)
--
-- Usage:
--   psql $DATABASE_URL -f scripts/migrate_add_drift_fields.sql
--
-- Safe to run multiple times — IF NOT EXISTS guards prevent errors on re-run.

ALTER TABLE decisions
    ADD COLUMN IF NOT EXISTS last_reinforced_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS drift_risk         VARCHAR(10);

-- Optional: index drift_risk for fast filtered queries ("show me all high-risk decisions")
CREATE INDEX IF NOT EXISTS idx_decisions_drift_risk
    ON decisions (drift_risk)
    WHERE drift_risk IS NOT NULL;
