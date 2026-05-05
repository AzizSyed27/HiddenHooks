-- Apply manually: docker exec -i hiddenhooks_db psql -U hiddenhooks -d hiddenhooks < docker/initdb/009_species_values.sql

CREATE TABLE species_values (
    species_name TEXT  PRIMARY KEY,
    weight       FLOAT NOT NULL,
    notes        TEXT
);
