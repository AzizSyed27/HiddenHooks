-- Expand the region_type check constraint to allow 'lakes_mask'.
-- The original constraint was defined inline in 004_regions.sql with an
-- auto-generated name, so we find and drop it dynamically.
DO $$
DECLARE
    con_name TEXT;
BEGIN
    SELECT conname INTO con_name
    FROM pg_constraint
    WHERE conrelid = 'regions'::regclass
      AND contype = 'c'
      AND conname LIKE '%region_type%';

    IF con_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE regions DROP CONSTRAINT %I', con_name);
    END IF;
END $$;

ALTER TABLE regions
    ADD CONSTRAINT regions_region_type_check
    CHECK (region_type IN ('fmz', 'land_mask', 'lakes_mask'));
