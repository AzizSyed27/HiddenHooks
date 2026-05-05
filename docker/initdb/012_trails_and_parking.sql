-- Apply manually:
-- docker exec -i hiddenhooks_db psql -U hiddenhooks -d hiddenhooks < docker/initdb/012_trails_and_parking.sql

CREATE TABLE trails (
    id      bigserial PRIMARY KEY,
    osm_id  text,
    highway text,
    geom    geometry(LineString, 3161) NOT NULL
);
CREATE INDEX trails_geom_gist ON trails USING GIST (geom);

CREATE TABLE parking (
    id      bigserial PRIMARY KEY,
    osm_id  text,
    geom    geometry(Geometry, 3161) NOT NULL
);
CREATE INDEX parking_geom_gist ON parking USING GIST (geom);
