-- Apply manually: docker exec -i hiddenhooks_db psql -U hiddenhooks -d hiddenhooks < docker/initdb/008_candidate_edges.sql

CREATE TABLE candidate_edges (
    from_candidate_id BIGINT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    to_candidate_id   BIGINT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    edge_type         TEXT   NOT NULL CHECK (edge_type IN ('touches', 'snapped')),
    distance_m        FLOAT  NOT NULL,
    PRIMARY KEY (from_candidate_id, to_candidate_id),
    CHECK (from_candidate_id < to_candidate_id),
    CONSTRAINT edge_type_distance_check CHECK (
        (edge_type = 'touches' AND distance_m = 0)
        OR (edge_type = 'snapped' AND distance_m > 0)
    )
);

-- PK (from, to) covers from_candidate_id lookups as the leading column.
-- This index covers the reverse direction for undirected traversal.
CREATE INDEX candidate_edges_to_idx ON candidate_edges (to_candidate_id);
