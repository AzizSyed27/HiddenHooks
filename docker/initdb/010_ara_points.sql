-- Apply manually: docker exec -i hiddenhooks_db psql -U hiddenhooks -d hiddenhooks < docker/initdb/010_ara_points.sql

CREATE TABLE ara_points (
    ara_id               TEXT    PRIMARY KEY,
    geom                 geometry(Point, 3161) NOT NULL,
    survey_date          DATE,
    fish_species_summary TEXT,
    fmz_zone             TEXT    NOT NULL CHECK (fmz_zone IN ('FMZ16', 'FMZ17')),
    snapped_candidate_id BIGINT  REFERENCES candidates(id) ON DELETE SET NULL,
    snap_distance_m      FLOAT,
    CONSTRAINT snap_fields_check CHECK (
        (snapped_candidate_id IS NULL AND snap_distance_m IS NULL)
        OR (snapped_candidate_id IS NOT NULL AND snap_distance_m IS NOT NULL AND snap_distance_m >= 0)
    )
);

CREATE INDEX ara_points_geom_gist     ON ara_points USING GIST (geom);
CREATE INDEX ara_points_candidate_idx ON ara_points (snapped_candidate_id);
CREATE INDEX ara_points_fmz_zone_idx  ON ara_points (fmz_zone);
