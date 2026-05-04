CREATE TABLE IF NOT EXISTS regions (
    id          bigserial PRIMARY KEY,
    name        text NOT NULL,
    region_type text NOT NULL CHECK (region_type IN ('fmz', 'land_mask')),
    geom        geometry(MultiPolygon, 3161) NOT NULL
);

CREATE INDEX regions_geom_gist ON regions USING GIST (geom);
CREATE UNIQUE INDEX regions_name_type_uidx ON regions (name, region_type);
