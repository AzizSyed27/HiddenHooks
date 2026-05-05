-- Phase 1 candidates cover only the Rouge test bbox with no fmz_zone.
-- Truncate before adding the NOT NULL column (empty table avoids the
-- need for a DEFAULT or backfill). CASCADE clears any child rows that
-- reference candidates via parent_candidate_id (none exist yet).
TRUNCATE candidates RESTART IDENTITY CASCADE;

ALTER TABLE candidates
    ADD COLUMN fmz_zone TEXT NOT NULL
    CHECK (fmz_zone IN ('FMZ16', 'FMZ17'));

CREATE INDEX candidates_fmz_zone_idx ON candidates (fmz_zone);
