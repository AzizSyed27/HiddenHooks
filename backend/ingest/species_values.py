"""Ingest data/species_values.csv into the species_values table."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL, REPO_ROOT

SPECIES_CSV = REPO_ROOT / "data" / "species_values.csv"

UPSERT_SQL = text("""
    INSERT INTO species_values (species_name, weight, notes)
    VALUES (:species_name, :weight, :notes)
    ON CONFLICT (species_name) DO UPDATE SET
        weight = EXCLUDED.weight,
        notes  = EXCLUDED.notes
""")


def ingest(engine) -> None:
    df = pd.read_csv(SPECIES_CSV, comment="#")
    print(f"  loaded from CSV:                 {len(df):,} rows")

    rows = [
        {
            "species_name": row["species_name"].strip().lower(),
            "weight":       float(row["weight"]),
            "notes":        row["notes"] if pd.notna(row["notes"]) else None,
        }
        for _, row in df.iterrows()
    ]

    with engine.begin() as conn:
        conn.execute(UPSERT_SQL, rows)
    print(f"  upserted:                        {len(rows):,}")


if __name__ == "__main__":
    engine = create_engine(DATABASE_URL)
    ingest(engine)
