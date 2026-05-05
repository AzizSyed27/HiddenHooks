-- Apply manually: docker exec -i hiddenhooks_db psql -U hiddenhooks -d hiddenhooks < docker/initdb/007_add_is_active.sql
ALTER TABLE candidates ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- Used by DEACTIVATE_SEGMENTED_SQL (EXISTS subquery), Part 4 connectivity graph,
-- and Part 7 scoring to navigate parent→child relationships efficiently.
CREATE INDEX candidates_parent_idx ON candidates (parent_candidate_id)
    WHERE parent_candidate_id IS NOT NULL;
