# HiddenHooks — Phase 2 Checklist

**Goal**: Move from "the pipes work" to "the pipes carry meaningful signal." Re-ingest at FMZ 16 scale with geometry simplification and proper filtering, segment watercourses into 200m reaches, build a connectivity graph, ingest ARA survey data, and compute a four-component score (Hiddenness, Accessibility, Fish potential, Ecology). Surface sub-scores and confidence tiers in the UI so the user can see *why* something ranks where it does.

**Deliverable**: A web page that displays scored candidates across the full FMZ 16 region, with sub-score breakdowns, three-tier confidence labels (Strong / Plausible / Speculative), and the ability to adjust component weights. The top-ranked candidates should look like real candidates worth investigating, not artifacts.

**Total time**: 4-6 weekends alongside other commitments. Phase 2 is bigger than Phase 1 by an order of magnitude — five distinct workstreams, each with their own design choices. Pace yourself.

**Working partner**: Claude Code. Discipline matters more than speed, and matters even more here than in Phase 1.

**Mindset**: Phase 1 produced a vertical slice that wasn't supposed to be useful. Phase 2's output should start to *feel* useful — not perfect, but at least defensible. If a top-ranked candidate is in Lake Ontario, you have a bug, not a "future feature will fix it."

---

## Part 0 — Working with Claude Code on a multi-workstream phase (read first, do not skip)

Phase 1 was one workstream done five different ways. Phase 2 is five workstreams that have to fit together. The failure mode is shipping all five components and finding out at the end that they don't integrate. This part is how you avoid that.

### Branch discipline

- [ ] Create a branch per workstream off `main`:
  - `phase-2/01-fmz-region`
  - `phase-2/02-reingest`
  - `phase-2/03-segmentation`
  - `phase-2/04-connectivity`
  - `phase-2/05-species-table`
  - `phase-2/06-ara-ingest`
  - `phase-2/07-scoring`
  - `phase-2/08-api-frontend`
- [ ] Each branch merges back to `main` only after its own sanity check passes (described in each Part below)
- [ ] No four-week-old branches. If a branch has been open more than a week, stop new work and integrate it.
- [ ] Tag `phase-2-complete` only after the integration smoke test in Part 9 passes

The point isn't ceremony. It's that small focused merges are easy to debug; one giant Phase-2 megamerge is not.

### Integration smoke test as forcing function

Part 9 is an end-to-end smoke test that exercises every workstream. It is not optional. Do not skip it. Do not run it for the first time after declaring Phase 2 done. Run it after Workstream 7 (scoring) merges, before the API/frontend updates, as a midpoint check. Run it again at the end.

### The "you might be wrong" prompt

In Phase 1 you used the "what's the case this approach is wrong, what would change at 100x scale, what edge cases haven't you considered" prompt. In Phase 2 you're literally going to 50x scale (full FMZ 16 vs Rouge bbox). Use the prompt more aggressively. Specifically apply it to:

- The simplification tolerance (1m might be wrong at FMZ 16 scale)
- The segmentation algorithm on edge-case geometries (very short reaches, MultiLineString)
- The connectivity graph tolerance (5m might over- or under-connect)
- The ARA snap tolerance (50m might miss real associations or create wrong ones)

### Slash commands worth setting up

In addition to Phase 1's slash commands, add these to `.claude/commands/`:

- [ ] `/integration-check` — Walk through the data path from raw shapefile to scored API response. For each layer, state row counts and a smoke check. Flag any obvious gaps.
- [ ] `/workstream-status` — Given the current branch, list what's done, what's verified, what's left, and what merges are blocking.
- [ ] `/score-explain` — Given a candidate ID, explain its scores component-by-component with raw inputs.

### Mid-phase fatigue protocol

Phase 2 will hit a wall around weekend 3-4. Symptoms: workstream merges feel harder than they should, you're tempted to skip sanity checks, you start writing code without Plan Mode. When this happens:

- [ ] Don't push through. Pause for a session.
- [ ] Run `/integration-check` and re-read this Part 0
- [ ] Look at the Phase 2 deliverable description at the top of this file. Are you still building toward it, or have you drifted?
- [ ] If the next workstream feels like it's getting too big, split it. The work is bounded by the deliverable, not by how much you can stomach in one weekend.

### Schema and data hygiene reminders from Phase 1

- [ ] OHN's `name` and `FISH_SPECIES_SUMMARY` fields can contain literal `"NaN"` strings, not just SQL NULL. Filter both in ingestion.
- [ ] Build the frontend regularly with `npm run build` — TypeScript build errors don't surface during dev mode.
- [ ] Roads must use a buffered bbox (FMZ 16 + 5km buffer) so candidates near the FMZ boundary aren't artificially "far from any road."

---

## Part 1 — FMZ 16 region polygon + land mask (2-3 hours)

This is the foundation for every filter in Phase 2. Do it first; everything else depends on it.

### Download FMZ 16 boundary

- [ ] Find the Ontario Fisheries Management Zone polygon dataset on https://geohub.lio.gov.on.ca/ (search "Fisheries Management Zone")
- [ ] Download the FMZ shapefile, clipped or filtered to FMZ 16 only (or download all FMZs and filter in QGIS — your call)
- [ ] Save to `data/fmz/`
- [ ] Open in QGIS, confirm it covers the area you expect (Toronto/Scarborough/Durham region, southern boundary on Lake Ontario)

### Download or derive a land mask

You need a polygon representing "land in Ontario" so you can filter out candidates whose geometry sits in Lake Ontario. Two options:

- **Option A**: Download a Great Lakes polygon dataset, treat the inverse as land. Cleanest semantically.
- **Option B**: Use the Ontario boundary polygon and assume anything inside it is "in Ontario," then check candidate geometries against `ST_Intersects(land_mask, candidate)` requiring at least *some* of the candidate to be on land.

Recommendation: **Option B** is simpler and good enough. Download the Ontario provincial boundary from GeoHub, save to `data/ontario_boundary/`.

### Create the regions table

**Plan Mode prompt**: "Create a `regions` table in the candidates database. Columns: id, name (text, e.g., 'FMZ 16'), region_type (text, 'fmz' or 'land_mask'), geom (geometry(MultiPolygon, 3161)). Spatial GIST index on geom. Also write an ingestion script `backend/ingest/regions.py` that reads the FMZ 16 polygon and the Ontario land mask polygon, reprojects to EPSG:3161, and inserts them. Idempotent on (name, region_type). Show me the SQL and Python plan before generating."

Verify in the plan:
- [ ] Geometry column is `MultiPolygon` (FMZ boundaries are often multipart)
- [ ] CRS is explicit and matches the rest of the project (3161)
- [ ] Spatial index exists
- [ ] Idempotency uses upsert on (name, region_type), not delete-and-reinsert

After implementation:
- [ ] Run the script
- [ ] `SELECT name, ST_Area(geom)/1e6 AS area_km2 FROM regions;` — verify FMZ 16 is in the right ballpark
- [ ] Visual check in QGIS: load the regions table, confirm both polygons render where expected

### Define the FMZ 16 working bbox

For driver-level filtering during shapefile reads, you still need a bounding box. Compute it from the FMZ polygon:

- [ ] In `backend/config.py`, replace `TEST_BBOX` with `FMZ16_BBOX` derived from the FMZ 16 polygon's envelope, in EPSG:4326. Add a comment explaining the source.
- [ ] Add `ROADS_BBOX` = FMZ16_BBOX expanded by 5km (to fix Phase 1's edge effect)
- [ ] Keep `TEST_BBOX` available as a fallback for fast iteration during scoring development — running the full scoring pipeline against FMZ 16 will not be quick

### Merge to main

- [ ] Branch sanity check: regions table populated, polygons render correctly in QGIS
- [ ] Merge `phase-2/01-fmz-region` to `main`

---

## Part 2 — Re-ingestion with simplification, land mask, and FMZ filter (4-6 hours)

This is the biggest single workstream. You're rewriting the Phase 1 ingest scripts to:
1. Apply geometry simplification to fix the 512s scoring problem
2. Filter to candidates whose centroid is in FMZ 16
3. Filter out candidates whose geometry doesn't intersect the land mask
4. Capture the `FISH_SPECIES_SUMMARY` field if present (likely it's not on OHN, but capture it anyway for robustness)
5. Use the buffered roads bbox

The schema doesn't change. You're going from ~2,888 candidates to a much larger number — likely 50,000-150,000 — so the scoring pipeline needs to handle that volume. Simplification is what makes it tractable.

### Decide whether to drop and re-ingest, or to migrate

- [ ] Recommendation: drop and re-ingest. The Phase 1 candidates table covers a tiny bbox; trying to add to it leaves stale rows. `TRUNCATE candidates RESTART IDENTITY CASCADE;` and re-run.
- [ ] If you've manually annotated anything in Phase 1, export it first. (You probably haven't.)

### Update the waterbody ingestion script

**Plan Mode prompt**: "Update `backend/ingest/ohn_waterbody.py` to:
1. Read OHN Waterbody at the FMZ16_BBOX driver-level filter (still use pyogrio bbox).
2. After loading, filter to features whose centroid is inside the FMZ 16 polygon (load FMZ 16 from regions table once at script start). This is centroid containment, not strict clipping.
3. After centroid filter, drop features whose geometry does not intersect the land mask polygon.
4. Apply `ST_SimplifyPreserveTopology(geom, 1.0)` before insert. Tolerance is 1m in EPSG:3161 — visually identical, much fewer vertices.
5. Capture FISH_SPECIES_SUMMARY column if it exists in the source (it's on ARA, but check OHN — defensive). Normalize literal 'NaN' strings to NULL.
6. Same idempotency, same area computation, same source_dataset='waterbody', candidate_type='polygon'.

Show me the updated script structure before generating."

Verify in the plan:
- [ ] FMZ 16 polygon is loaded once, not per-feature
- [ ] Centroid containment is computed in EPSG:3161 (after reprojection), not in source CRS
- [ ] Land mask intersection check uses the spatial index
- [ ] `ST_SimplifyPreserveTopology` is applied via PostGIS in the INSERT, not Python (faster, idempotent across runs)
- [ ] `"NaN"` string normalization is applied to all text fields, not just `name`
- [ ] Edge case: what if a polygon's centroid is in FMZ 16 but the polygon extends across the boundary? Plan should include this — keep the original geometry, don't clip.

After implementation:
- [ ] Run the script. Note the elapsed time.
- [ ] `SELECT COUNT(*) FROM candidates WHERE source_dataset='waterbody';` — should be in the thousands, not tens of thousands. Big lakes are sparse.
- [ ] QGIS sanity check: load the polygons, confirm they cover FMZ 16 land area, with no Lake Ontario candidates and no obvious holes

### Update the watercourse ingestion script

**Plan Mode prompt**: Mirror the waterbody changes for `backend/ingest/ohn_watercourse.py`. Same FMZ centroid filter, same land mask intersection, same simplification, same FISH_SPECIES_SUMMARY capture (likely still empty for watercourses). `candidate_type='reach_full'` and `source_dataset='watercourse'` unchanged. Show me the diff from the waterbody script — call out anything that's different beyond file paths and type/length-vs-area.

Verify in the plan:
- [ ] MultiLineString handling is preserved (do NOT explode to LineStrings here — segmentation in Part 3 will handle that)
- [ ] Length is computed in EPSG:3161 after simplification
- [ ] Centroid containment for linestrings: PostGIS `ST_Centroid` works for linestrings; the centroid of a long winding stream might be in surprising places, but it's still a defensible filter

After implementation:
- [ ] Run the script. Note the elapsed time.
- [ ] `SELECT candidate_type, COUNT(*) FROM candidates GROUP BY candidate_type;` — watercourse count should substantially exceed waterbody count, as in Phase 1
- [ ] QGIS sanity check: watercourses connect to waterbodies, no orphan offshore lines

### Re-run the roads ingestion with the buffered bbox

- [ ] Update `backend/ingest/roads.py` to use `ROADS_BBOX` (FMZ + 5km buffer)
- [ ] Drop and re-ingest the roads table
- [ ] Verify count is meaningfully higher than Phase 1's 47,601

### Re-run the dist_to_road scoring with simplified geometry

This is the moment of truth for the simplification decision.

- [ ] Run `backend/scoring/dist_to_road.py` against the new candidates table
- [ ] **Note the elapsed time.** Phase 1 was 512s for 2,888 candidates. With simplification + larger candidate set + buffered roads, the per-candidate cost should drop sharply. If it's still painfully slow (>30 minutes), the simplification didn't take effect or there's a different bottleneck — debug before moving on.
- [ ] Spot check 5 candidates of each type in QGIS — do distance values still match eyeball estimates?

### Merge to main

- [ ] Branch sanity check: counts make sense, no Lake Ontario candidates, scoring runtime is reasonable
- [ ] Merge `phase-2/02-reingest` to `main`

---

## Part 3 — Reach segmentation (3-4 hours)

Take each `reach_full` row, walk its geometry, and emit `reach_segment` children at 200m intervals. The schema already supports this (`parent_candidate_id`, `candidate_type='reach_segment'`).

### Add the segmentation config parameter

- [ ] In `backend/config.py`, add `SEGMENT_LENGTH_M = 200` with a comment explaining this is tunable
- [ ] Anywhere you reference segment length downstream, import from config — no magic numbers

### Write the segmentation script

**Plan Mode prompt**: "Write `backend/processing/segment_reaches.py` that reads each `reach_full` candidate from the database, splits its geometry at SEGMENT_LENGTH_M intervals using PostGIS `ST_LineSubstring` (or via Shapely's `substring` in Python), and inserts the resulting LineString segments as new candidates with `candidate_type='reach_segment'`, `parent_candidate_id` pointing to the original `reach_full`, `name` inherited from the parent, length computed for each segment, area NULL.

Handle MultiLineString parents by exploding to LineStrings first, then segmenting each part. The last segment of each LineString may be shorter than SEGMENT_LENGTH_M — keep it (don't merge with previous).

Idempotency: deleting all existing reach_segments for a parent before re-segmenting is fine here because they have no FKs pointing in yet (the connectivity graph in Part 4 will reference them). Implement as: DELETE FROM candidates WHERE parent_candidate_id IS NOT NULL; then re-run.

Show me the algorithm and SQL plan before generating, especially the MultiLineString handling and the boundary cases (segments shorter than SEGMENT_LENGTH_M, very short reach_full inputs)."

Verify in the plan:
- [ ] MultiLineString handling is explicit (explode to LineStrings, segment each, parent_id same for all)
- [ ] Last-segment-shorter-than-200m case is handled (kept, not dropped or merged)
- [ ] reach_full with length < SEGMENT_LENGTH_M is handled (becomes a single reach_segment, or stays as reach_full only — pick one and document)
- [ ] Name inheritance: child segments get parent's name (so "Willowgrove Creek" segments are still labeled "Willowgrove Creek" in the panel)
- [ ] OHN ID inheritance: store parent's OHN ID on segments too, for traceability

### Decide what reach_full rows do after segmentation

When a `reach_full` is segmented, do you keep it in the candidates table, or remove it from queries?

- Recommendation: **keep the `reach_full` row** (it's the parent record, has the OHN ID, useful for "the parent of this segment"), but **filter it out of API queries** when it has reach_segment children. The query is `WHERE NOT (candidate_type = 'reach_full' AND id IN (SELECT DISTINCT parent_candidate_id FROM candidates WHERE parent_candidate_id IS NOT NULL))` — or store a `is_active` boolean on candidates and update it during segmentation.
- [ ] Pick one approach. Document it. Apply it to the API query in Part 8.

### Sanity checks

After running the script:
- [ ] `SELECT candidate_type, COUNT(*) FROM candidates GROUP BY candidate_type;` — should now show reach_segment as a large number, reach_full unchanged (still in the table)
- [ ] `SELECT parent_candidate_id, SUM(length_m) AS total_segment_length, p.length_m AS parent_length FROM candidates c JOIN candidates p ON c.parent_candidate_id = p.id WHERE c.candidate_type='reach_segment' GROUP BY parent_candidate_id, p.length_m LIMIT 10;` — for each parent, the sum of segment lengths should be ≈ parent length (within rounding)
- [ ] Pick one named river you know (from the Phase 1 panel — say, Willowgrove Creek) and confirm it's been split into the expected number of segments
- [ ] QGIS visual: load reach_segments only, confirm they look like a continuous river rendered in alternating colors (you can color by `id % 2` to verify segmentation worked)

### Merge to main

- [ ] Merge `phase-2/03-segmentation` to `main`

---

## Part 4 — Connectivity graph (3-5 hours)

The graph is what lets fish observations at one ARA point inform candidates that have no ARA point of their own. It's the highest-leverage piece of Phase 2.

### Schema

**Plan Mode prompt**: "Add a `candidate_edges` table for the connectivity graph. Columns: from_candidate_id (FK to candidates), to_candidate_id (FK to candidates), edge_type (text: 'touches' or 'snapped'), distance_m (FLOAT, the gap that was bridged for snapped edges, 0 for touches). Primary key (from_candidate_id, to_candidate_id). Index on each FK column for fast graph traversal. Edges are stored undirected, but I'll insert each pair only once with from < to to avoid double-counting — do this via CHECK constraint or convention. Show me the SQL before generating."

Verify in the plan:
- [ ] Foreign keys with ON DELETE CASCADE so dropping candidates cleans up edges
- [ ] Indexes on both FK columns (graph traversal queries on either direction)
- [ ] Convention or constraint for undirected representation (from_id < to_id)

### Build the graph

**Plan Mode prompt**: "Write `backend/processing/build_connectivity.py` that populates the candidate_edges table. Algorithm:

1. For each candidate (polygon or reach_segment), find all *other* candidates within 5m using `ST_DWithin`. This is the snap tolerance — handles minor topology gaps in OHN data where a stream and a pond should connect but don't quite touch in the source geometry.
2. For each found pair, insert one edge (from_id, to_id) with from_id < to_id, edge_type='snapped' if distance > 0 else 'touches', distance_m as the actual gap.
3. Skip self-edges and duplicate edges.
4. Skip reach_full rows that have segmented children (use the same active-candidate filter from Part 3).
5. Do NOT create polygon-to-polygon edges unless they actually touch — two ponds 4m apart probably aren't connected. Restrict polygon-to-polygon edges to edge_type='touches' only.

Use ST_DWithin with the spatial index, not nested loops. Expected query pattern:

INSERT INTO candidate_edges (from_candidate_id, to_candidate_id, edge_type, distance_m)
SELECT c1.id, c2.id, ..., ST_Distance(c1.geom, c2.geom)
FROM candidates c1
JOIN candidates c2 ON c1.id < c2.id
WHERE ST_DWithin(c1.geom, c2.geom, 5)
  AND (c1.candidate_type IN ('polygon', 'reach_segment'))
  AND (c2.candidate_type IN ('polygon', 'reach_segment'))
  -- Plus the polygon-polygon constraint above

Estimate the runtime — this is a self-join with a spatial predicate. Show me the SQL plan and a runtime estimate before generating."

Verify in the plan:
- [ ] Self-edges and duplicates are excluded
- [ ] Polygon-polygon edges are restricted appropriately
- [ ] reach_full rows that have been segmented are excluded
- [ ] The `c1.id < c2.id` ordering enforces undirected uniqueness
- [ ] Spatial index is used (EXPLAIN should show Index Scan, not Seq Scan)

### Sanity checks

- [ ] `SELECT COUNT(*) FROM candidate_edges;` — should be much larger than candidate count (most candidates have multiple connections)
- [ ] `SELECT edge_type, COUNT(*) FROM candidate_edges GROUP BY edge_type;` — both types should appear
- [ ] Pick a named river (Willowgrove Creek again) and verify its segments are connected end-to-end in the edges table
- [ ] Pick a small isolated pond and verify it has zero or few edges (correct: it shouldn't connect to anything)
- [ ] **Connected components check**: write a one-off SQL or Python script (using networkx) that loads the edge list and computes connected components. The largest component should cover most of FMZ 16's water network. Many small components = something's wrong.

### Merge to main

- [ ] Merge `phase-2/04-connectivity` to `main`

---

## Part 5 — Species-value table (1-2 hours)

This is the values document that encodes "the aim are the bigger fish." It's a CSV you author, then ingest. Treat it seriously — the F-scoring depends on it entirely.

### Author the CSV

- [ ] Create `data/species_values.csv` with columns: `species_name`, `weight`, `notes`
- [ ] Use the species names exactly as they appear in ARA's `FISH_SPECIES_SUMMARY` field (case-sensitive — verify by querying ARA after Part 6, but you can start authoring now)
- [ ] Suggested starting weights (your call, override based on your fishing values):
  - Walleye, Northern Pike, Muskellunge, Smallmouth Bass, Largemouth Bass: **8-10**
  - Brook Trout, Brown Trout, Rainbow Trout, Lake Trout: **8-9**
  - Yellow Perch, Black Crappie, White Crappie: **5-6**
  - Pumpkinseed, Bluegill, Rock Bass: **4-5**
  - Channel Catfish, Brown Bullhead, Black Bullhead: **4-5**
  - Common Carp, White Sucker, Longnose Sucker, Redhorse species: **2-3**
  - Stonerollers, Dace species, Shiners, Chubs (small forage): **1-2**
  - Anything you don't recognize or care about: **1**
- [ ] Add notes per row explaining why. Future-you will want to know why hornyhead chub got the weight it did.
- [ ] Add a header comment at the top of the CSV documenting your weighting philosophy (your Phase 0 stance: avoid minnow streams, prioritize big-fish species)

### Schema and ingestion

**Plan Mode prompt**: "Create a `species_values` table: species_name TEXT PRIMARY KEY, weight FLOAT NOT NULL, notes TEXT. Write `backend/ingest/species_values.py` to read the CSV and upsert into the table. Idempotent on species_name. Show me the SQL and Python before generating."

After implementation:
- [ ] Run the script
- [ ] `SELECT COUNT(*) FROM species_values;` — matches your CSV row count
- [ ] `SELECT * FROM species_values ORDER BY weight DESC LIMIT 10;` — top of list should be the species you actually want to catch

### Merge to main

- [ ] Merge `phase-2/05-species-table` to `main`

---

## Part 6 — ARA ingestion + snap to candidates (3-4 hours)

ARA points are the empirical anchor for F-scoring. You ingest the survey points, then snap each one to its nearest candidate within 50m.

### Schema

**Plan Mode prompt**: "Create an `ara_points` table: ara_id TEXT PRIMARY KEY (the OHN/ARA source ID), geom geometry(Point, 3161) NOT NULL, survey_date DATE, fish_species_summary TEXT, snapped_candidate_id INTEGER REFERENCES candidates(id), snap_distance_m FLOAT. Spatial GIST index on geom, B-tree index on snapped_candidate_id (for fast 'find ARA points for this candidate' queries during F-scoring). Show me the SQL before generating."

### Ingest ARA points

**Plan Mode prompt**: "Write `backend/ingest/ara_points.py` that:
1. Reads the ARA Survey Point shapefile from `data/ara/`.
2. Filters to points whose geometry is inside the FMZ 16 polygon.
3. Reprojects to EPSG:3161.
4. Captures FISH_SPECIES_SUMMARY (handle 'NaN' string normalization) and survey date.
5. Inserts into ara_points table (snapped_candidate_id and snap_distance_m left NULL for now — separate snap step).

Same patterns as the OHN ingestion: GeoPandas, pyogrio bbox at driver level, idempotent upsert on ara_id."

Verify in the plan:
- [ ] FMZ 16 filter is on the point geometry, not centroid (centroid of a point is the point — but be explicit)
- [ ] Survey date column name in the source — confirm before assuming
- [ ] FISH_SPECIES_SUMMARY normalization handles 'NaN' string

After running:
- [ ] `SELECT COUNT(*) FROM ara_points;` — should be in the thousands or low tens of thousands for FMZ 16
- [ ] `SELECT COUNT(*) FROM ara_points WHERE fish_species_summary IS NOT NULL;` — what fraction is populated? This was the question we never answered. If it's <30%, F-scoring will lean heavily on connectivity inference.
- [ ] `SELECT fish_species_summary FROM ara_points WHERE fish_species_summary IS NOT NULL LIMIT 20;` — eyeball the format. Does it match what you saw in Phase 0 (comma-separated, no spaces after commas)? Are there species names with commas in them?
- [ ] `SELECT DISTINCT TRIM(unnest(string_to_array(fish_species_summary, ','))) AS species FROM ara_points WHERE fish_species_summary IS NOT NULL ORDER BY species;` — get the full species list. Compare to your species_values.csv. Anything missing? Anything with weird capitalization or whitespace?

### Snap ARA points to candidates

**Plan Mode prompt**: "Write `backend/processing/snap_ara_to_candidates.py` that updates each ara_points row with its nearest candidate within 50m, storing snapped_candidate_id and snap_distance_m. Use the KNN operator (`<->`) with LATERAL JOIN for efficiency:

UPDATE ara_points a
SET snapped_candidate_id = nearest.id,
    snap_distance_m = nearest.dist
FROM LATERAL (
  SELECT c.id, ST_Distance(a.geom, c.geom) AS dist
  FROM candidates c
  WHERE c.candidate_type IN ('polygon', 'reach_segment')  -- skip reach_full parents
    AND ST_DWithin(a.geom, c.geom, 50)
  ORDER BY a.geom <-> c.geom
  LIMIT 1
) nearest;

Some ARA points will not snap (no candidate within 50m). Leave them NULL — log the count after running."

Verify in the plan:
- [ ] KNN operator is used for efficiency (not nested loops)
- [ ] Polygon and reach_segment are eligible targets, reach_full is not
- [ ] Snap tolerance is the 50m we agreed on, exposed as a config parameter

### Sanity checks

- [ ] `SELECT COUNT(*) FILTER (WHERE snapped_candidate_id IS NOT NULL) AS snapped, COUNT(*) AS total FROM ara_points;` — fraction snapped tells you ARA spatial coverage in FMZ 16
- [ ] `SELECT AVG(snap_distance_m), MAX(snap_distance_m) FROM ara_points WHERE snapped_candidate_id IS NOT NULL;` — most snaps should be very small (point inside polygon = 0m, or very close to a stream segment); large average means tolerance is too generous
- [ ] QGIS visual: load ara_points, color by `snap_distance_m`. Most should be near-zero. Outliers near 50m deserve scrutiny.
- [ ] Pick 3 ARA points, look up their snapped candidates in QGIS, confirm spatial association is correct

### Merge to main

- [ ] Merge `phase-2/06-ara-ingest` to `main`

---

## Part 7 — Four-component scoring (5-7 hours)

This is where it all comes together. Four normalized sub-scores per candidate, stored as columns. Composite computed at API time. H, A, E can be computed in parallel; F depends on the connectivity graph and ARA snaps.

### Schema additions

**Plan Mode prompt**: "Add scoring columns to the candidates table:
- h_score FLOAT (normalized 0-1, hiddenness)
- a_score FLOAT (normalized 0-1, accessibility)
- a_dist_to_trail_m FLOAT (raw input)
- a_dist_to_parking_m FLOAT (raw input)
- f_score FLOAT (normalized 0-1, fish potential)
- f_confidence TEXT CHECK (f_confidence IN ('strong', 'plausible', 'speculative', NULL))
- f_species TEXT (comma-separated for display)
- f_inferred_from_ara_id TEXT (which ARA point provided the inference, NULL for speculative)
- f_graph_distance INT (hops in connectivity graph from nearest ARA-anchored candidate, NULL if direct or speculative)
- e_score FLOAT (normalized 0-1, ecology bonus)

Most are nullable — they get populated by the scoring scripts. Show me the migration before generating."

### H — Hiddenness score

**Plan Mode prompt**: "Write `backend/scoring/score_hiddenness.py`. Hiddenness is a function of:
1. dist_to_road_meters (already populated)
2. name is NULL or 'NaN' (small additive boost — unnamed water bodies are less likely to be in guidebooks)

Normalization: percentile-rank dist_to_road_meters across all active candidates (active = polygon, or reach_segment, or reach_full without segmented children) to get a 0-1 base score. Add 0.1 if name is NULL/NaN, clip to 1.0. Single UPDATE statement using window function for the percentile. Show SQL before generating."

Verify:
- [ ] Percentile ranking handles NULL dist_to_road_meters (shouldn't be any after Part 2 re-scoring, but defend)
- [ ] Active-candidate filter is applied (don't compute h_score for orphan reach_full rows)

### A — Accessibility score

**Plan Mode prompt**: "Accessibility means 'easy for an angler to physically get to.' Two raw inputs:
1. Distance to nearest trail (OSM ways with highway IN ('path', 'footway', 'cycleway', 'track'))
2. Distance to nearest parking (OSM nodes/ways with amenity='parking')

Write `backend/ingest/trails_and_parking.py` to ingest these from OSM (OSMnx or Overpass) into trails and parking tables. Use the buffered ROADS_BBOX. Then write `backend/scoring/score_accessibility.py` that:
- Updates a_dist_to_trail_m and a_dist_to_parking_m via spatial nearest-neighbor query (same KNN pattern as roads)
- Computes a_score = 1 - clip(min(dist_to_trail, dist_to_parking) / 2000, 0, 1)
  - At 0m from trail or parking: a_score = 1.0
  - At ≥2000m: a_score = 0.0
  - Linear in between
- 2000m threshold is in config.py as ACCESSIBILITY_DECAY_M

Show plan before generating, especially the OSM ingestion approach (cache, idempotent, etc.)."

Verify:
- [ ] OSM ingestion follows the same caching pattern as Phase 1's roads.py
- [ ] Threshold is configurable, not magic
- [ ] Edge case: candidates with no trail OR parking within any reasonable distance get a_score = 0 (not NULL)

### E — Ecology bonus

**Plan Mode prompt**: "Write `backend/ingest/landcover.py` to ingest SOLRIS landcover for FMZ 16, then `backend/scoring/score_ecology.py` that computes ecology score per candidate:
- Buffer each candidate by 100m
- Compute % of buffer area that is 'forested' or 'wetland' landcover (SOLRIS class codes — verify the codes during ingestion)
- e_score = forested_or_wetland_pct (already 0-1)

Buffer + intersection on tens of thousands of candidates × landcover polygons is expensive. Plan should propose: rasterize landcover to a single raster, then use raster summary statistics per candidate buffer. Or, if vector-only is preferred for simplicity, restrict to candidates above a certain size (small reach segments don't need ecology scoring, e_score = 0.5 default).

Make a recommendation and show the plan."

Verify:
- [ ] SOLRIS class codes are explicitly identified (don't assume)
- [ ] Performance approach is justified
- [ ] Default for skipped candidates is documented (don't leave NULL)

### F — Fish potential

This is the most complex of the four. It depends on ARA snaps + connectivity graph + species values.

**Plan Mode prompt**: "Write `backend/scoring/score_fish_potential.py`. Algorithm:

For each active candidate:
1. **Strong tier**: If the candidate has any ARA point snapped to it (via ara_points.snapped_candidate_id), parse its fish_species_summary, look up each species in species_values, sum the weights. Take the union across multiple ARA points if more than one is snapped (every species ever observed counts; track the most recent survey_date in metadata). Normalize the raw sum: divide by some 'max plausible' value (sum of weights of top 5 species in your CSV) and clip to 1.0. f_confidence = 'strong'. f_inferred_from_ara_id = the ARA ID with the most recent survey.

2. **Plausible tier**: If no ARA snapped directly, BFS the connectivity graph from this candidate, find the nearest ARA-anchored candidate, take its species list with a discount factor of 0.7^graph_distance (so 1 hop = 0.7x, 2 hops = 0.49x, etc.). f_confidence = 'plausible'. Cap graph_distance at 5 hops; beyond that, fall through to speculative.

3. **Speculative tier**: No graph path to any ARA-anchored candidate within 5 hops. f_score = candidate_type prior:
   - polygon (lake/pond): 0.3 (water bodies hold *some* fish on average)
   - reach_segment (stream): 0.2
   f_confidence = 'speculative'. f_species = NULL. f_inferred_from_ara_id = NULL.

Implementation: graph traversal in Python (networkx loaded from candidate_edges) is simpler than recursive CTEs in SQL for this. Show the algorithm + the data loading approach before generating."

Verify:
- [ ] Graph distance is computed correctly (BFS, not weighted)
- [ ] Discount factor 0.7^d is configurable (F_GRAPH_DISCOUNT in config)
- [ ] Species name matching is case-insensitive and trimmed (avoid "Walleye" vs "walleye " mismatches)
- [ ] Species not in species_values table get weight 0 (not NULL — defensive)
- [ ] Performance: pre-load species_values into a dict, pre-load ARA snaps into a dict keyed by candidate_id

### Sanity checks across all four components

- [ ] `SELECT candidate_type, AVG(h_score), AVG(a_score), AVG(f_score), AVG(e_score) FROM candidates GROUP BY candidate_type;` — averages should be in the 0.2-0.6 range, not all 0 or all 1
- [ ] `SELECT f_confidence, COUNT(*) FROM candidates GROUP BY f_confidence;` — distribution tells you graph coverage. If 90% are speculative, the graph isn't propagating signal. If 90% are strong, you've over-snapped.
- [ ] Pick the highest h_score candidate, the highest a_score, the highest f_score, the highest e_score. Look at each in QGIS. Do they make sense?
- [ ] Pick a candidate with strong f_confidence and look at f_species. Do the species match the species_values weights you set?

### Merge to main

- [ ] Branch sanity check: all four scores populated, no NULL contamination, distributions look right
- [ ] Merge `phase-2/07-scoring` to `main`
- [ ] **Run the integration smoke test from Part 9 NOW as a midpoint check, before frontend work starts**

---

## Part 8 — API + frontend updates (4-6 hours)

Surface sub-scores, confidence tiers, and weight controls in the UI.

### Update the API

**Plan Mode prompt**: "Update `backend/api/main.py`:

1. GET /candidates accepts query parameters w_h, w_a, w_f, w_e (each float, default 0.25). Validate they sum to ~1.0 (within 0.01 tolerance) or normalize.
2. Composite score computed at query time: composite = w_h*h_score + w_a*a_score + w_f*f_score + w_e*e_score
3. Rank by composite DESC NULLS LAST.
4. Response properties expand to include: h_score, a_score, f_score, e_score, f_confidence, f_species, a_dist_to_trail_m, a_dist_to_parking_m, dist_to_road_meters, composite, rank.
5. Filter out reach_full rows that have segmented children (use the active-candidates view from Part 3).
6. Add GET /health endpoint (simple, returns {status: ok}).

Update the Pydantic models accordingly. Show the diff before generating."

Verify:
- [ ] Weight validation is forgiving (normalize rather than 400-error on small float drift)
- [ ] Active-candidates filter is applied
- [ ] f_species is passed through as text (frontend will format)
- [ ] Response payload size is still reasonable — at FMZ 16 scale this might be 50k features and 50MB. Consider pagination or filtering by query bbox if it gets unwieldy. In Phase 2 you can ship without and add later if needed.

### Update the frontend panel

**Plan Mode prompt**: "Update CandidatePanel and CandidateDetail in `frontend/components/panel/`:

1. Detail card: show four horizontal score bars (H, A, F, E) with the composite at top. Bars colored by score (same rank-color expression we use on the map, applied per-component). Below the bars, show raw inputs: 'Distance from road: 1289m', 'Distance from trail: 320m', 'Forest cover within 100m: 47%', and 'Fish observed: Walleye, Northern Pike, Smallmouth Bass'.

2. Confidence tier displayed as a colored badge next to the candidate name: green for strong, amber for plausible, gray for speculative. Use shadcn Badge component.

3. List items: keep the rank badge, but add a tiny confidence indicator (small dot or letter, color-coded same as the badge) so users can see confidence at a glance without expanding.

4. Weight controls: add four sliders at the top of the panel (H, A, F, E), each 0-1, defaulting to 0.25. On change, re-fetch /candidates with the new weights (debounced 300ms). Show the current numeric values next to each slider.

5. Layout: panel is now denser; consider expanding the default width from 320 to 360px, and using collapsible sections (shadcn Collapsible) for the breakdown card.

Show the component diffs before generating, especially the slider state management — should weights be in URL params (so views are shareable)?"

Verify:
- [ ] Slider re-fetch is debounced (300ms is reasonable)
- [ ] Loading state during re-fetch is visible (subtle spinner or fade), not jarring
- [ ] Weight URL params is your call — for v2 it's a nice-to-have
- [ ] Color-coding for confidence is accessible (don't rely on color alone — also use letter or icon)
- [ ] **Run `npm run build` after every component change.** TypeScript build errors don't surface in dev mode (Phase 1 lesson).

### Map updates

- [ ] Color expression on map layers should now use the composite score, not normalizedRank. Expose composite as a feature property.
- [ ] On weight change, the map source data updates → layer recolors automatically (Mapbox handles this if `data` prop reference changes)
- [ ] Optional: tint reach_segments slightly differently from polygons so the panel and map agree on type at a glance

### Merge to main

- [ ] Branch sanity check: app loads, weights work, scores display
- [ ] Merge `phase-2/08-api-frontend` to `main`

---

## Part 9 — End-to-end integration smoke test (1-2 hours)

This is not a polish step. It's a verification step that everything still works together. **Run it at the midpoint (after Part 7) and again at the end (before tagging).**

- [ ] Stop everything. Restart Docker, restart backend, restart frontend.
- [ ] Open `http://localhost:3000`.
- [ ] Map loads with custom basemap, scoped to FMZ 16 region.
- [ ] No candidates in Lake Ontario. (If there are, Part 1 land mask broke. Stop and fix.)
- [ ] Both polygons and reach_segments visible on map.
- [ ] Side panel shows ranked list. Top 5 candidates visible.
- [ ] Click top candidate. Detail card opens. All four sub-scores display, raw inputs display, f_species shows actual species names from your CSV.
- [ ] Confidence badge displays correctly. Strong/Plausible/Speculative distribution is visible across the list.
- [ ] Adjust weight sliders. Top candidates change as expected. (Set w_f=1.0 and w_h=w_a=w_e=0; the top candidates should be the ARA-anchored ones with the most valuable species.)
- [ ] Pick one of your Phase 0 manual gem candidates (the ones you flagged in Scarborough/Rouge area). Search for it in the panel. Where does it rank? Does its rank match your intuition? If not — is the discrepancy informative or is something miscomputed?
- [ ] Walk through the full data path one more time, out loud or in writing: shapefile → ingestion → simplification → FMZ filter → segmentation → connectivity graph → ARA snap → species lookup → four-component scoring → API → frontend → pixel. You should be able to explain every hop without hesitating.
- [ ] Pick a candidate with `f_confidence='plausible'`. Look at f_inferred_from_ara_id. Find that ARA point in QGIS. Verify the candidate is actually graph-connected to it (segments along the same stream system, or polygon-reach connections that make sense).
- [ ] If anything fails: do not declare Phase 2 done. Open a fix branch off main, fix, re-run smoke test.

---

## Part 10 — Reflection and commit (45-60 min)

Same prompts as Phase 1, plus a few Phase-2-specific ones.

### Document

- [ ] Update `README.md` with current state
- [ ] Update `CLAUDE.md` with anything that changed about the architecture
- [ ] Create `docs/phase_2_reflection.md` answering:
  - What worked smoothly?
  - What took longer than expected, and why?
  - What surprised you about the data, the tooling, or the process?
  - What architectural decisions are you uncertain about?
  - **Looking at the top-ranked candidates with composite scoring: do they look like real candidates worth investigating? Compare to your Phase 0 manual gem list.**
  - **Which of the four components is doing the most work in the rankings? Which feels weakest?**
  - **Did the connectivity graph propagate enough signal, or did most candidates end up speculative?**
  - **What's the ratio of strong/plausible/speculative confidence? Does it match your intuition about ARA spatial coverage?**
  - **Is the species_values weighting producing the rankings you wanted, or do you need to revisit the weights?**
  - What did you learn about Claude Code's working pattern on a multi-workstream phase?
  - What's one thing you'd do differently starting Phase 2 over?

### Commit and tag

- [ ] `git add -A && git commit -m "Phase 2: four-component scoring at FMZ 16 scale"`
- [ ] Push to GitHub
- [ ] Tag: `git tag phase-2-complete && git push --tags`

---

## Done criteria

You're done with Phase 2 when:
- [ ] App loads, scoped to full FMZ 16, with both polygons and 200m reach segments
- [ ] All four sub-scores populated for active candidates
- [ ] Confidence tier (Strong/Plausible/Speculative) is visible per candidate
- [ ] Weight sliders work and re-rank the candidates
- [ ] Top-ranked candidates look defensible — none are in Lake Ontario, none are obviously absurd
- [ ] You can explain every component's computation out loud
- [ ] All five workstream branches are merged to main
- [ ] Integration smoke test passes
- [ ] Repo is committed, tagged, documented

You do **not** need to:
- Have a routing layer (Phase 3 territory)
- Have done the first ground-truth trip (Phase 4 territory)
- Have a multi-agent layer (Phase 5 territory)
- Have weight calibration from trip outcomes (Phase 6 territory)
- Have FMZ 17 / Kawarthas (Phase 6 territory)
- Have Information Value scoring (Phase 6 territory)
- Have private-land filtering, regulation overlays, or stocking integration (Phase 5+ territory)
- Have a perfect ecology score — Phase 2's E is admittedly thin

---

## If you get stuck

**Scoring runtime is still painful even after simplification**: Check that simplification actually applied. `SELECT ST_NPoints(geom) FROM candidates LIMIT 10;` should show low vertex counts. If high, simplification didn't run during ingest. Re-run with explicit `ST_SimplifyPreserveTopology` in the INSERT. If counts are low and runtime is still bad, profile with EXPLAIN ANALYZE on the scoring query to identify the bottleneck.

**FMZ 16 polygon download isn't on GeoHub**: The MNRF FMZ dataset is sometimes mirrored on data.ontario.ca. Or, last resort, derive the boundary from the regulations PDF — but this should not be necessary.

**Connectivity graph has way more edges than expected**: Tolerance might be too loose. Drop to 2m and rebuild. Conversely, if it has too few, raise to 10m. The right number is one that connects all segments of the same named river but doesn't connect adjacent unrelated ponds.

**ARA snap rate is very low (e.g., <20%)**: Check that ARA points are in the right CRS, and that your candidates table includes the polygons/reach_segments those points should snap to. Also: 50m might be too tight for the source data quality — try 100m and see if rates improve. If rates are still low at 100m, the survey program just doesn't cover most of FMZ 16, which is itself useful information.

**Most candidates are 'speculative' confidence**: Either ARA coverage is genuinely sparse (real signal — informs the value of doing more ground-truth trips), or the connectivity graph isn't bridging the network properly (artifact — fix the graph). Disambiguate by picking a few specific speculative candidates and checking whether they have *any* path through the graph to *any* ARA-anchored candidate.

**Species names don't match between ARA and species_values.csv**: Run the case-insensitive species inventory query from Part 6, then update your CSV to match exactly. Consider doing the species name normalization at query time (LOWER + TRIM) instead of at ingest, so future ARA updates don't break joins.

**Composite scoring seems to favor only one component regardless of weights**: Sub-scores aren't on the same 0-1 scale. Check distributions per component (`SELECT MIN, MAX, AVG, STDDEV per component`). If H ranges 0-0.95 but A only ranges 0-0.4, weight 0.25 doesn't equally weight them. Re-normalize per-component to use the full 0-1 range.

**You feel mid-phase scope creep tempting you**: Run `/scope-check`. The Phase 2 deliverable is at the top of this file. The "do not need to" list is at the bottom of the Done Criteria. Read both and re-narrow.

**You hit fatigue and integration is feeling unfixable**: This is what Part 0's mid-phase fatigue protocol is for. Stop, take a session off, run `/integration-check` next session, re-read Part 0.

---

## After Phase 2

Bring back to the next conversation:
- Your `phase_2_reflection.md` notes
- Screenshots of the working app at FMZ 16 scale, with weight sliders set to (a) equal, (b) F-only, (c) H-only — three different rankings
- Top 5 candidates under each weight scheme, with rough coordinates and confidence tiers
- Which Phase 0 manual gem candidates surfaced, and where they ranked
- Architectural decisions you're uncertain about
- Honest assessment: does the top-ranked composite candidate feel like a real spot you'd actually investigate? If yes — that's the green light for Phase 4 (ground-truth trip planning). If no — Phase 3 (routing) might need to come first to filter on practical accessibility.

Then we plan Phase 3: routing layer (trail Dijkstra + off-trail least-cost path on a cost surface from slope and landcover), or — if Phase 2's output already feels actionable — we plan Phase 4 (first ground-truth trip).
