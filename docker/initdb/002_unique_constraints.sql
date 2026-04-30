-- Partial unique indexes for upsert keys.
-- Each index covers only the candidate_type it applies to, so Phase 2
-- reach_segment rows (same ohn_id, same source_dataset) are never in scope.

CREATE UNIQUE INDEX candidates_polygon_upsert_key
    ON candidates (ohn_id, source_dataset)
    WHERE candidate_type = 'polygon';

CREATE UNIQUE INDEX candidates_reach_full_upsert_key
    ON candidates (ohn_id, source_dataset)
    WHERE candidate_type = 'reach_full';
