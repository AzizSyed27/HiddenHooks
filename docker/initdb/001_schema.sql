CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TYPE candidate_type AS ENUM (
    'polygon',       -- OHN Waterbody (lake, pond, wide river)
    'reach_full',    -- OHN Watercourse as a whole (Phase 1)
    'reach_segment'  -- split portion of a reach (Phase 2, reserved)
);

CREATE TYPE ohn_dataset AS ENUM (
    'waterbody',
    'watercourse'
);

CREATE TABLE candidates (
    id                  bigserial PRIMARY KEY,
    ohn_id              text NOT NULL,
    source_dataset      ohn_dataset NOT NULL,
    candidate_type      candidate_type NOT NULL,
    parent_candidate_id bigint REFERENCES candidates(id),
    name                text,
    geom                geometry(Geometry, 3161) NOT NULL,
    area_m2             double precision,
    length_m            double precision,
    dist_to_road_meters double precision
);

CREATE INDEX candidates_geom_gist ON candidates USING GIST (geom);
CREATE INDEX candidates_candidate_type_idx ON candidates (candidate_type);
