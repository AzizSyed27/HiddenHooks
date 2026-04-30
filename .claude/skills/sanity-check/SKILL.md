---
name: sanity-check
description: Connect to the database and report row counts, geometry validity, CRS, and recent schema changes for each layer.
allowed-tools: Bash, Read
---

Connect to the project database and produce a health report covering:

1. **Row counts** — for every layer/table, report the number of rows
2. **Geometry validity** — run ST_IsValid() checks and report any invalid geometries with their IDs
3. **CRS** — report the SRID / coordinate reference system for each geometry column
4. **Recent schema changes** — check information_schema or pg_stat_user_tables for any tables/columns added or altered recently (last 7 days if possible)

Format the output as a clear, scannable table or sections per layer. Flag anything that looks wrong or unexpected.