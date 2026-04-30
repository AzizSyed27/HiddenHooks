CREATE TABLE roads (
    id      bigserial PRIMARY KEY,
    osm_id  text,
    name    text,
    highway text,
    geom    geometry(Geometry, 3161) NOT NULL
);

CREATE INDEX roads_geom_gist ON roads USING GIST (geom);
