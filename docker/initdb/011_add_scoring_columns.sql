-- Apply manually:
-- docker exec -i hiddenhooks_db psql -U hiddenhooks -d hiddenhooks < docker/initdb/011_add_scoring_columns.sql

ALTER TABLE candidates
    ADD COLUMN h_score                FLOAT   CHECK (h_score IS NULL OR (h_score >= 0 AND h_score <= 1)),
    ADD COLUMN a_score                FLOAT   CHECK (a_score IS NULL OR (a_score >= 0 AND a_score <= 1)),
    ADD COLUMN a_dist_to_trail_m      FLOAT   CHECK (a_dist_to_trail_m IS NULL OR a_dist_to_trail_m >= 0),
    ADD COLUMN a_dist_to_parking_m    FLOAT   CHECK (a_dist_to_parking_m IS NULL OR a_dist_to_parking_m >= 0),
    ADD COLUMN f_score                FLOAT   CHECK (f_score IS NULL OR (f_score >= 0 AND f_score <= 1)),
    ADD COLUMN f_confidence           TEXT    CHECK (f_confidence IN ('strong', 'plausible', 'speculative')),
    ADD COLUMN f_species              TEXT,
    ADD COLUMN f_inferred_from_ara_id TEXT,
    ADD COLUMN f_graph_distance       INTEGER CHECK (f_graph_distance IS NULL OR (f_graph_distance >= 0 AND f_graph_distance <= 5)),
    ADD COLUMN e_score                FLOAT   CHECK (e_score IS NULL OR (e_score >= 0 AND e_score <= 1));
