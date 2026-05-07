# HiddenHooks — Phase 2 Checklist (revised: FMZ 16 + FMZ 17)

**Goal**: Move from "the pipes work" to "the pipes carry meaningful signal." Re-ingest at the scale of two FMZs (16 and 17) with geometry simplification and proper filtering, segment watercourses into 200m reaches, build a connectivity graph that spans both regions, ingest ARA survey data, and compute a four-component score (Hiddenness, Accessibility, Fish potential, Ecology) with per-region semantics where appropriate. Surface sub-scores, FMZ identity, and confidence tiers in the UI so the user can see *why* something ranks where it does.

**Deliverable**: A web page that displays scored candidates across FMZ 16 and FMZ 17, filterable by FMZ, with sub-score breakdowns, three-tier confidence labels (Strong / Plausible / Speculative), and the ability to adjust component weights. The top-ranked candidates *within each region* should look like real candidates worth investigating, not artifacts.

**Total time**: 5-7 weekends alongside other commitments. Roughly 1 extra weekend over the FMZ-16-only scope, mostly in ingestion and sanity-checking. Pace yourself.

**Working partner**: Claude Code. Discipline matters more than speed, and matters even more here than in Phase 1.

**Mindset**: Phase 1 produced a vertical slice that wasn't supposed to be useful. Phase 2's output should start to *feel* useful — not perfect, but at least defensible. If a top-ranked candidate is in Lake Ontario, you have a bug, not a "future feature will fix it." If FMZ 17's rankings look great and FMZ 16's look thin, that's a real signal about ARA coverage — don't paper over it.

---

## Part 0 — Working with Claude Code on a multi-workstream, multi-region phase (read first, do not skip)

Phase 1 was one workstream done five different ways. Phase 2 is five workstreams that have to fit together — and now operate cleanly across two regions. The failure mode is shipping all five components and finding out at the end that they don't integrate, or that they integrate for one region but silently break for the other. This part is how you avoid that.

### Branch discipline

- [x] Create a branch per workstream off `main`:
  - `phase-2/01-fmz-regions` (note: plural)
  - `phase-2/02-reingest`
  - `phase-2/03-segmentation`
  - `phase-2/04-connectivity`
  - `phase-2/05-species-table`
  - `phase-2/06-ara-ingest`
  - `phase-2/07-scoring`
  - `phase-2/08-api-frontend`
- [x] Each branch merges back to `main` only after its own sanity check passes (described in each Part below)
- [x] No four-week-old branches. If a branch has been open more than a week, stop new work and integrate it.
- [x] Tag `phase-2-complete` only after the integration smoke test in Part 9 passes for **both regions**

The point isn't ceremony. It's that small focused merges are easy to debug; one giant Phase-2 megamerge is not.

### Default to per-region semantics

A new principle for this phase: when a design decision touches "across all candidates," ask whether it should actually be "across all candidates in the same FMZ." Most percentile-style normalizations, ranks, and "compared to peers" computations should be per-region. Only absolute-scale things (species weights, distance thresholds in meters, area thresholds in m²) should be global. When in doubt, per-region — it's the more honest default for a tool that compares fishing spots, because "hidden" and "accessible" are inherently relative concepts.

This becomes load-bearing in Part 7. Lock it in your head now.

### Integration smoke test as forcing function

Part 9 is an end-to-end smoke test that exercises every workstream **across both regions**. It is not optional. Do not skip it. Do not run it for the first time after declaring Phase 2 done. Run it after Workstream 7 (scoring) merges, before the API/frontend updates, as a midpoint check. Run it again at the end.

### The "you might be wrong" prompt

In Phase 1 you used the "what's the case this approach is wrong, what would change at 100x scale, what edge cases haven't you considered" prompt. In Phase 2 you're literally going to ~70x scale (FMZ 16 + FMZ 17 vs Rouge bbox). Use the prompt more aggressively. Specifically apply it to:

- The simplification tolerance (1m might be wrong at FMZ-pair scale)
- The segmentation algorithm on edge-case geometries (very short reaches, MultiLineString)
- The connectivity graph tolerance (5m might over- or under-connect)
- The ARA snap tolerance (50m might miss real associations or create wrong ones)
- The per-region normalization choice (is anything you're treating as global actually region-relative?)

### Slash commands worth setting up

In addition to Phase 1's slash commands, add these to `.claude/commands/`:

- [x] `/integration-check` — Walk through the data path from raw shapefile to scored API response. For each layer, state row counts and a smoke check, **broken out per FMZ**. Flag any obvious gaps.
- [x] `/workstream-status` — Given the current branch, list what's done, what's verified, what's left, and what merges are blocking.
- [x] `/score-explain` — Given a candidate ID, explain its scores component-by-component with raw inputs, including which FMZ it belongs to and which percentile of that region.

### Mid-phase fatigue protocol

Phase 2 will hit a wall around weekend 4-5. Symptoms: workstream merges feel harder than they should, you're tempted to skip sanity checks, you start writing code without Plan Mode. When this happens:

- [x] Don't push through. Pause for a session.
- [x] Run `/integration-check` and re-read this Part 0
- [x] Look at the Phase 2 deliverable description at the top of this file. Are you still building toward it, or have you drifted?
- [ ] If the next workstream feels like it's getting too big, split it. The work is bounded by the deliverable, not by how much you can stomach in one weekend.

### Schema and data hygiene reminders from Phase 1

- [x] OHN's `name` and `FISH_SPECIES_SUMMARY` fields can contain literal `"NaN"` strings, not just SQL NULL. Filter both in ingestion.
- [x] Build the frontend regularly with `npm run build` — TypeScript build errors don't surface during dev mode.
- [x] Roads must use a buffered combined bbox (FMZ 16 ∪ FMZ 17 + 5km buffer) so candidates near *either* FMZ boundary aren't artificially "far from any road."

---

## Part 1 — FMZ region polygons + land mask (2-3 hours)

This is the foundation for every filter in Phase 2. Do it first; everything else depends on it. Compared to a single-region setup, this is barely any more work — you ingest two polygons instead of one.

### Download FMZ 16 and FMZ 17 boundaries

- [x] Find the Ontario Fisheries Management Zone polygon dataset on https://geohub.lio.gov.on.ca/ (search "Fisheries Management Zone")
- [x] Download the FMZ shapefile, filtered to FMZ 16 and FMZ 17 (or download all FMZs and filter in QGIS — your call)
- [x] Save to `data/fmz/`
- [x] Open both polygons in QGIS together, confirm they share a boundary along roughly the Toronto/Pickering line, and confirm together they cover everything from Lake Ontario north through the Kawarthas and Lake Simcoe area

### Download or derive a land mask

You need a polygon representing "land in Ontario" so you can filter out candidates whose geometry sits in Lake Ontario, Georgian Bay, etc. Two options:

- **Option A**: Download a Great Lakes polygon dataset, treat the inverse as land. Cleanest semantically.
- **Option B**: Use the Ontario boundary polygon and assume anything inside it is "in Ontario," then check candidate geometries against `ST_Intersects(land_mask, candidate)` requiring at least *some* of the candidate to be on land.

Recommendation: **Option B** is simpler and good enough. Download the Ontario provincial boundary from GeoHub, save to `data/ontario_boundary/`.

### Create the regions table

**Plan Mode prompt**: "Create a `regions` table in the candidates database. Columns: id, name (text, e.g., 'FMZ 16', 'FMZ 17', 'Ontario Land'), region_type (text, 'fmz' or 'land_mask'), geom (geometry(MultiPolygon, 3161)). Spatial GIST index on geom. Also write an ingestion script `backend/ingest/regions.py` that reads the FMZ 16 polygon, FMZ 17 polygon, and the Ontario land mask polygon, reprojects each to EPSG:3161, and inserts them. Idempotent on (name, region_type). Show me the SQL and Python plan before generating."

Verify in the plan:
- [x] Geometry column is `MultiPolygon` (FMZ boundaries are often multipart)
- [x] CRS is explicit and matches the rest of the project (3161)
- [x] Spatial index exists
- [x] Idempotency uses upsert on (name, region_type), not delete-and-reinsert
- [x] All three regions get loaded in one script run

After implementation:
- [x] Run the script
- [x] `SELECT name, region_type, ST_Area(geom)/1e6 AS area_km2 FROM regions ORDER BY area_km2 DESC;` — sanity check the areas. FMZ 17 should be larger than FMZ 16 by area (more rural land). Both should be in the thousands of km².
- [x] Visual check in QGIS: load the regions table, confirm both FMZs and the land mask render where expected, and that FMZ 16 and FMZ 17 share a clean boundary

### Define working bboxes

For driver-level filtering during shapefile reads, you need bounding boxes:

- [x] In `backend/config.py`, define:
  - `FMZ16_BBOX` = envelope of the FMZ 16 polygon, in EPSG:4326
  - `FMZ17_BBOX` = envelope of the FMZ 17 polygon, in EPSG:4326
  - `COMBINED_BBOX` = union envelope of both, in EPSG:4326
  - `ROADS_BBOX` = COMBINED_BBOX expanded by 5km (fixes Phase 1's edge effect across either FMZ boundary)
- [x] Keep `TEST_BBOX` available as a fallback for fast iteration during scoring development — running the full scoring pipeline against both FMZs will not be quick

### Merge to main

- [x] Branch sanity check: regions table populated with three polygons, FMZ 16 and FMZ 17 are visibly adjacent, areas are in the right ballpark
- [x] Merge `phase-2/01-fmz-regions` to `main`

---

## Part 2 — Re-ingestion with simplification, land mask, FMZ-zone tagging (5-7 hours)

This is the biggest single workstream. You're rewriting the Phase 1 ingest scripts to:
1. Apply geometry simplification to fix the 512s scoring problem
2. Filter to candidates whose centroid is in **either** FMZ 16 or FMZ 17, and tag the candidate with which one
3. Filter out candidates whose geometry doesn't intersect the land mask
4. Use the buffered combined roads bbox

The schema gets a small change: add an `fmz_zone TEXT NOT NULL` column. You're going from ~2,888 candidates to a much larger number — likely 80,000-200,000 across both regions — so the scoring pipeline needs to handle that volume. Simplification is what makes it tractable.

### Schema migration: add fmz_zone

**Plan Mode prompt**: "Add a `fmz_zone TEXT NOT NULL` column to the candidates table, with `CHECK (fmz_zone IN ('FMZ16', 'FMZ17'))`. Create a B-tree index on fmz_zone (we'll filter and group-by often). Show the migration before generating, and call out: since the table currently has Phase 1 data with no fmz_zone, the cleanest path is `TRUNCATE candidates RESTART IDENTITY CASCADE` and then re-ingest from scratch under Part 2 — no need to retrofit existing rows."

Verify in the plan:
- [x] CHECK constraint locks down the allowed values
- [x] Index exists for fast region filtering
- [x] Phase 1 data is dropped, not retrofitted (cleaner)

### Decide whether to drop and re-ingest, or to migrate

- [x] Recommendation: drop and re-ingest. The Phase 1 candidates table covers a tiny bbox; trying to add to it leaves stale rows. `TRUNCATE candidates RESTART IDENTITY CASCADE;` and re-run.
- [x] If you've manually annotated anything in Phase 1, export it first. (You probably haven't.)

### Update the waterbody ingestion script

**Plan Mode prompt**: "Update `backend/ingest/ohn_waterbody.py` to:
1. Read OHN Waterbody at the COMBINED_BBOX driver-level filter (still use pyogrio bbox).
2. Load both FMZ 16 and FMZ 17 polygons from the regions table at script start.
3. After loading and reprojecting to EPSG:3161, filter to features whose centroid is inside *either* FMZ 16 *or* FMZ 17. Tag each surviving feature with `fmz_zone='FMZ16'` or `'FMZ17'` based on which polygon contained the centroid.
4. After the FMZ filter, drop features whose geometry does not intersect the land mask polygon.
5. Apply `ST_SimplifyPreserveTopology(geom, 1.0)` before insert. Tolerance is 1m in EPSG:3161 — visually identical, much fewer vertices.
6. Normalize literal 'NaN' strings to NULL on text fields (specifically `name`).
7. Same idempotency, same area computation, same source_dataset='waterbody', candidate_type='polygon'.

Edge case: a centroid can only be in one FMZ at a time (they don't overlap), but a polygon's *geometry* might extend across the FMZ boundary. Keep the original geometry — don't clip — and tag by centroid. This is centroid-containment semantics.

Show me the updated script structure before generating."

Verify in the plan:
- [x] Both FMZ polygons are loaded once, not per-feature
- [x] Centroid containment is computed in EPSG:3161 (after reprojection), not in source CRS
- [x] Land mask intersection check uses the spatial index
- [x] `ST_SimplifyPreserveTopology` is applied via PostGIS in the INSERT, not Python (faster, idempotent across runs)
- [x] `"NaN"` string normalization is applied to all text fields
- [x] FMZ tagging uses ST_Contains or ST_Within with the spatial index, not a brute scan

After implementation:
- [x] Run the script. Note the elapsed time.
- [x] `SELECT fmz_zone, COUNT(*) FROM candidates WHERE source_dataset='waterbody' GROUP BY fmz_zone;` — both should be populated. FMZ 17 likely has more polygon candidates (more lakes in the Kawarthas).
- [x] QGIS sanity check: load the polygons, color by `fmz_zone`, confirm they cover both FMZ land areas with no Lake Ontario candidates and a clean visible boundary along the FMZ 16/17 line

### Update the watercourse ingestion script

**Plan Mode prompt**: Mirror the waterbody changes for `backend/ingest/ohn_watercourse.py`. Same dual-FMZ centroid filter, same land mask intersection, same simplification, same fmz_zone tagging. `candidate_type='reach_full'` and `source_dataset='watercourse'` unchanged. Show me the diff from the waterbody script — call out anything that's different beyond file paths and type/length-vs-area.

Verify in the plan:
- [x] MultiLineString handling is preserved (do NOT explode to LineStrings here — segmentation in Part 3 will handle that)
- [x] Length is computed in EPSG:3161 after simplification
- [x] Centroid containment for linestrings: PostGIS `ST_Centroid` works for linestrings; the centroid of a long winding stream might be in surprising places, but it's still a defensible filter
- [x] A reach_full whose centroid is in FMZ 17 but extends into FMZ 16 (e.g., parts of the Trent system) gets tagged FMZ17, full geometry preserved. This is the same semantics as waterbody.

After implementation:
- [x] Run the script. Note the elapsed time.
- [x] `SELECT fmz_zone, candidate_type, COUNT(*) FROM candidates GROUP BY fmz_zone, candidate_type ORDER BY fmz_zone, candidate_type;` — every cell should be populated, watercourses substantially exceed waterbodies in both regions
- [x] QGIS sanity check: watercourses connect to waterbodies, no orphan offshore lines, FMZ tagging visible by color

### Re-run the roads ingestion with the buffered combined bbox

- [x] Update `backend/ingest/roads.py` to use `ROADS_BBOX` (COMBINED_BBOX + 5km buffer)
- [x] Drop and re-ingest the roads table
- [x] Verify count is meaningfully higher than Phase 1's 47,601 (probably 5-10x given the area increase)

### Re-run the dist_to_road scoring with simplified geometry

This is the moment of truth for the simplification decision.

- [x] Run `backend/scoring/dist_to_road.py` against the new candidates table
- [x] **Note the elapsed time.** Phase 1 was 512s for 2,888 candidates. With simplification + larger candidate set + buffered roads, the per-candidate cost should drop sharply. If total runtime exceeds an hour for the full two-region set, the simplification didn't take effect or there's a different bottleneck — debug before moving on.
- [x] Spot check 5 candidates of each type, in each FMZ, in QGIS — do distance values still match eyeball estimates?

### Merge to main

- [x] Branch sanity check: counts make sense per-region, no Lake Ontario candidates, scoring runtime is reasonable
- [x] Merge `phase-2/02-reingest` to `main`

---

## Part 3 — Reach segmentation (3-4 hours)

Take each `reach_full` row, walk its geometry, and emit `reach_segment` children at 200m intervals. The schema already supports this (`parent_candidate_id`, `candidate_type='reach_segment'`). Children inherit their parent's `fmz_zone`.

### Add the segmentation config parameter

- [x] In `backend/config.py`, add `SEGMENT_LENGTH_M = 200` with a comment explaining this is tunable
- [x] Anywhere you reference segment length downstream, import from config — no magic numbers

### Write the segmentation script

**Plan Mode prompt**: "Write `backend/processing/segment_reaches.py` that reads each `reach_full` candidate from the database, splits its geometry at SEGMENT_LENGTH_M intervals using PostGIS `ST_LineSubstring` (or via Shapely's `substring` in Python), and inserts the resulting LineString segments as new candidates with `candidate_type='reach_segment'`, `parent_candidate_id` pointing to the original `reach_full`, `name` inherited from the parent, `fmz_zone` inherited from the parent, length computed for each segment, area NULL.

Handle MultiLineString parents by exploding to LineStrings first, then segmenting each part. The last segment of each LineString may be shorter than SEGMENT_LENGTH_M — keep it (don't merge with previous).

Idempotency: deleting all existing reach_segments before re-segmenting is fine here because they have no FKs pointing in yet (the connectivity graph in Part 4 will reference them). Implement as: DELETE FROM candidates WHERE parent_candidate_id IS NOT NULL; then re-run.

Show me the algorithm and SQL plan before generating, especially the MultiLineString handling and the boundary cases (segments shorter than SEGMENT_LENGTH_M, very short reach_full inputs)."

Verify in the plan:
- [x] MultiLineString handling is explicit (explode to LineStrings, segment each, parent_id same for all)
- [x] Last-segment-shorter-than-200m case is handled (kept, not dropped or merged)
- [x] reach_full with length < SEGMENT_LENGTH_M is handled (becomes a single reach_segment, or stays as reach_full only — pick one and document)
- [x] Name inheritance: child segments get parent's name (so "Willowgrove Creek" segments are still labeled "Willowgrove Creek" in the panel)
- [x] **fmz_zone inheritance** from parent — call this out explicitly in the INSERT
- [x] OHN ID inheritance: store parent's OHN ID on segments too, for traceability

### Decide what reach_full rows do after segmentation

When a `reach_full` is segmented, do you keep it in the candidates table, or remove it from queries?

- Recommendation: **keep the `reach_full` row** (it's the parent record, has the OHN ID, useful for "the parent of this segment"), but **filter it out of API queries** when it has reach_segment children. The query is `WHERE NOT (candidate_type = 'reach_full' AND id IN (SELECT DISTINCT parent_candidate_id FROM candidates WHERE parent_candidate_id IS NOT NULL))` — or store an `is_active` boolean on candidates and update it during segmentation.
- [ ] Pick one approach. Document it. Apply it to the API query in Part 8.

## How active candidates are tracked after segmentation

- Decision: add an `is_active BOOLEAN NOT NULL DEFAULT TRUE` column to candidates. The segmentation script flips parents to FALSE after inserting their children, in the same transaction. All downstream queries filter with WHERE is_active = TRUE.
- Why this approach over the inline-subquery alternative: the boolean is shorter to remember in every query, indexes naturally, and generalizes if future phases add other reasons a candidate might be inactive (private land, regulatory exclusion, etc.). The drift risk is bounded because only one script (segment_reaches.py) writes to the column, and it does so atomically with segment inserts.

- [x] Add migration 007_add_is_active.sql (or next available number): ALTER TABLE candidates ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE; plus an index on is_active for the common filter.
- [x] Apply the migration manually (same pattern as other Phase 2 migrations).
- [x] Update segment_reaches.py to flip parents off in the same transaction as the segment INSERT.
- [x] Document the rule in CLAUDE.md: "Active candidates are filtered with WHERE is_active = TRUE. The flag is maintained exclusively by segment_reaches.py. Don't write queries that ignore it; don't write code that toggles it from elsewhere."

### Sanity checks

After running the script:
- [x] `SELECT fmz_zone, candidate_type, COUNT(*) FROM candidates GROUP BY fmz_zone, candidate_type;` — should now show reach_segment as a large number in each region, reach_full unchanged
- [x] `SELECT parent_candidate_id, SUM(length_m) AS total_segment_length, p.length_m AS parent_length, p.fmz_zone FROM candidates c JOIN candidates p ON c.parent_candidate_id = p.id WHERE c.candidate_type='reach_segment' GROUP BY parent_candidate_id, p.length_m, p.fmz_zone LIMIT 10;` — for each parent, the sum of segment lengths should be ≈ parent length (within rounding)
- [x] Pick one named river you know in **each** FMZ (e.g., Willowgrove Creek for FMZ 16, something in the Trent system for FMZ 17) and confirm each has been split into the expected number of segments
- [x] QGIS visual: load reach_segments only, confirm they look like a continuous river rendered in alternating colors (color by `id % 2`)

### Merge to main

- [x] Merge `phase-2/03-segmentation` to `main`

---

## Part 4 — Connectivity graph, spanning both regions (3-5 hours)

The graph is what lets fish observations at one ARA point inform candidates that have no ARA point of their own. It's the highest-leverage piece of Phase 2.

**Important design choice**: edges are allowed to span the FMZ boundary. Fish do not respect regulatory zones. A walleye observed in the Trent system in FMZ 17 should be able to inform an inferred candidate further down the same connected water in FMZ 16, if the geometry actually connects. The graph is a hydrology graph, not a regulatory one.

### Schema

**Plan Mode prompt**: "Add a `candidate_edges` table for the connectivity graph. Columns: from_candidate_id (FK to candidates), to_candidate_id (FK to candidates), edge_type (text: 'touches' or 'snapped'), distance_m (FLOAT, the gap that was bridged for snapped edges, 0 for touches). Primary key (from_candidate_id, to_candidate_id). Index on each FK column for fast graph traversal. Edges are stored undirected, but I'll insert each pair only once with from < to to avoid double-counting — do this via CHECK constraint or convention. Edges deliberately span the FMZ boundary; do not add an FMZ filter to edge construction. Show me the SQL before generating."

Verify in the plan:
- [x] Foreign keys with ON DELETE CASCADE so dropping candidates cleans up edges
- [x] Indexes on both FK columns (graph traversal queries on either direction)
- [x] Convention or constraint for undirected representation (from_id < to_id)
- [x] **No FMZ filter** in the edge build query — confirmed explicit

### Build the graph

**Plan Mode prompt**: "Write `backend/processing/build_connectivity.py` that populates the candidate_edges table. Algorithm:

1. For each candidate (polygon or reach_segment, regardless of fmz_zone), find all *other* candidates within 5m using `ST_DWithin`. This is the snap tolerance — handles minor topology gaps in OHN data where a stream and a pond should connect but don't quite touch in the source geometry.
2. For each found pair, insert one edge (from_id, to_id) with from_id < to_id, edge_type='snapped' if distance > 0 else 'touches', distance_m as the actual gap.
3. Skip self-edges and duplicate edges.
4. Skip reach_full rows that have segmented children (use the same active-candidate filter from Part 3).
5. Do NOT create polygon-to-polygon edges unless they actually touch — two ponds 4m apart probably aren't connected. Restrict polygon-to-polygon edges to edge_type='touches' only.

Use ST_DWithin with the spatial index, not nested loops. Estimate the runtime — this is a self-join with a spatial predicate over ~100k+ candidates. Show me the SQL plan and a runtime estimate before generating."

Verify in the plan:
- [ ] Self-edges and duplicates are excluded
- [ ] Polygon-polygon edges are restricted appropriately
- [ ] reach_full rows that have been segmented are excluded
- [ ] The `c1.id < c2.id` ordering enforces undirected uniqueness
- [ ] Spatial index is used (EXPLAIN should show Index Scan, not Seq Scan)

### Sanity checks

- [x] `SELECT COUNT(*) FROM candidate_edges;` — should be much larger than candidate count
- [x] `SELECT edge_type, COUNT(*) FROM candidate_edges GROUP BY edge_type;` — both types should appear
- [x] **Cross-region edges**: `SELECT COUNT(*) FROM candidate_edges e JOIN candidates c1 ON e.from_candidate_id=c1.id JOIN candidates c2 ON e.to_candidate_id=c2.id WHERE c1.fmz_zone != c2.fmz_zone;` — there should be *some* of these (where the FMZ boundary cuts across a connected water network), but not many. If there are zero, your graph isn't bridging the boundary at all and the fish-inference benefit of doing both regions together is wasted. If there are tens of thousands, the FMZ polygons are probably wonky and over-bordering rivers.
- [x] Pick a named river in each region and verify its segments are connected end-to-end
- [x] Pick a small isolated pond and verify it has zero or few edges (correct: it shouldn't connect to anything)
- [x] **Connected components check**: write a one-off SQL or Python script (using networkx) that loads the edge list and computes connected components. The largest few components should cover most of the water network. Many small components = something's wrong.

### Merge to main

- [x] Merge `phase-2/04-connectivity` to `main`

---

## Part 5 — Species-value table (1-2 hours)

This is the values document that encodes "the aim are the bigger fish." It's a CSV you author, then ingest. **Global, not per-region** — a walleye is a walleye whether it's in FMZ 16 or FMZ 17.

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
- [ ] FMZ 17 will likely surface walleye/muskie populations that FMZ 16 doesn't have. Make sure those species are in your CSV with thoughtful weights — they're going to drive a lot of FMZ 17's F-scoring.

### Schema and ingestion

**Plan Mode prompt**: "Create a `species_values` table: species_name TEXT PRIMARY KEY, weight FLOAT NOT NULL, notes TEXT. Write `backend/ingest/species_values.py` to read the CSV and upsert into the table. Idempotent on species_name. Show me the SQL and Python before generating."

After implementation:
- [x] Run the script
- [x] `SELECT COUNT(*) FROM species_values;` — matches your CSV row count
- [x] `SELECT * FROM species_values ORDER BY weight DESC LIMIT 10;` — top of list should be the species you actually want to catch

### Merge to main

- [x] Merge `phase-2/05-species-table` to `main`

---

## Part 6 — ARA ingestion + snap to candidates (3-4 hours)

ARA points are the empirical anchor for F-scoring. You ingest the survey points across both FMZs, then snap each one to its nearest candidate within 50m. **ARA coverage in FMZ 17 will likely be substantially better than FMZ 16** — that asymmetry is real and informative.

### Schema

**Plan Mode prompt**: "Create an `ara_points` table: ara_id TEXT PRIMARY KEY (the OHN/ARA source ID), geom geometry(Point, 3161) NOT NULL, survey_date DATE, fish_species_summary TEXT, fmz_zone TEXT NOT NULL CHECK (fmz_zone IN ('FMZ16', 'FMZ17')), snapped_candidate_id INTEGER REFERENCES candidates(id), snap_distance_m FLOAT. Spatial GIST index on geom, B-tree index on snapped_candidate_id (for fast 'find ARA points for this candidate' queries during F-scoring), B-tree index on fmz_zone. Show me the SQL before generating."

### Ingest ARA points

**Plan Mode prompt**: "Write `backend/ingest/ara_points.py` that:
1. Reads the ARA Survey Point shapefile from `data/ara/Aquatic_Resource_Area_Survey_Point`.
2. Filters to points whose geometry is inside FMZ 16 *or* FMZ 17. Tag each surviving point with the appropriate fmz_zone.
3. Reprojects to EPSG:3161.
4. Captures FISH_SPECIES_SUMMARY (handle 'NaN' string normalization) and survey date.
5. Inserts into ara_points table (snapped_candidate_id and snap_distance_m left NULL for now — separate snap step).

Same patterns as the OHN ingestion: GeoPandas, pyogrio bbox at driver level using COMBINED_BBOX, idempotent upsert on ara_id."

Verify in the plan:
- [x] FMZ filter handles both regions, tags appropriately
- [x] Survey date column name in the source — confirm before assuming
- [x] FISH_SPECIES_SUMMARY normalization handles 'NaN' string

After running:
- [x] `SELECT fmz_zone, COUNT(*) FROM ara_points GROUP BY fmz_zone;` — both populated. Note the asymmetry; this is your ARA spatial coverage signal.
- [x] `SELECT fmz_zone, COUNT(*) FILTER (WHERE fish_species_summary IS NOT NULL) AS populated, COUNT(*) AS total FROM ara_points GROUP BY fmz_zone;` — what fraction is populated in each region? If FMZ 17 has higher coverage, that's expected.
- [x] `SELECT fish_species_summary FROM ara_points WHERE fish_species_summary IS NOT NULL LIMIT 20;` — eyeball the format. Comma-separated, no spaces after commas? Are there species names with commas in them?
- [x] `SELECT DISTINCT TRIM(unnest(string_to_array(fish_species_summary, ','))) AS species FROM ara_points WHERE fish_species_summary IS NOT NULL ORDER BY species;` — get the full species list across both regions. Compare to your species_values.csv. Anything missing? Anything with weird capitalization or whitespace? Update the CSV if needed.

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

Note: I'm intentionally NOT requiring a.fmz_zone = c.fmz_zone for the snap. An ARA point on a river right at the FMZ boundary should snap to the nearest segment regardless of which side of the line it falls on. The FMZ assignment for the candidate already reflects centroid containment.

Some ARA points will not snap (no candidate within 50m). Leave them NULL — log the count after running, broken out by fmz_zone."

Verify in the plan:
- [x] KNN operator is used for efficiency (not nested loops)
- [x] Polygon and reach_segment are eligible targets, reach_full is not
- [x] No FMZ-equality constraint on snap (intentional)
- [x] Snap tolerance is the 50m we agreed on, exposed as a config parameter

### Sanity checks

- [x] `SELECT fmz_zone, COUNT(*) FILTER (WHERE snapped_candidate_id IS NOT NULL) AS snapped, COUNT(*) AS total FROM ara_points GROUP BY fmz_zone;` — fraction snapped per region tells you ARA spatial coverage
- [x] `SELECT fmz_zone, AVG(snap_distance_m), MAX(snap_distance_m) FROM ara_points WHERE snapped_candidate_id IS NOT NULL GROUP BY fmz_zone;` — most snaps should be very small
- [x] **Cross-FMZ snaps**: `SELECT COUNT(*) FROM ara_points a JOIN candidates c ON a.snapped_candidate_id = c.id WHERE a.fmz_zone != c.fmz_zone;` — should be small but non-zero (boundary effects)
- [x] QGIS visual: load ara_points, color by `snap_distance_m`. Most should be near-zero.
- [x] Pick 3 ARA points from each region, look up their snapped candidates in QGIS, confirm spatial association is correct

### Merge to main

- [x] Merge `phase-2/06-ara-ingest` to `main`

---

## Part 7 — Four-component scoring with per-region semantics (5-7 hours)

This is where it all comes together — and where the per-region principle from Part 0 becomes load-bearing.

### Normalization design — read carefully

Each of the four components has a different appropriate scale:

- **H (Hiddenness)**: percentile rank of `dist_to_road_meters` **within the same FMZ**. A 5km-from-road candidate is exceptional in dense FMZ 16 but unremarkable in rural FMZ 17. Per-region percentile is the only honest answer.
- **A (Accessibility)**: linear decay of distance to nearest trail/parking, formula `1 - clip(min_dist / 2000, 0, 1)`. This is on an absolute scale — 500m from a trail is 500m regardless of region — so it's **global**.
- **F (Fish potential)**: weighted sum of species values (from a global table) × graph-distance discount. Fully **global** — a walleye lake is a walleye lake regardless of zone.
- **E (Ecology)**: % forested-or-wetland in 100m buffer. Already 0-1, on an absolute scale, **global**.

The **composite** score is computed at API time as `w_h*h_score + w_a*a_score + w_f*f_score + w_e*e_score`. Because H is per-region normalized and A/F/E are global, the composite is implicitly comparable within a region but only loosely comparable across. **Rank is computed per-region** so users see "rank 1 of 8,000 in FMZ 16" or "rank 1 of 12,000 in FMZ 17." This matches how a fisher actually plans — you pick a region, then pick a spot within it.

If at any point you find yourself wanting to normalize H globally, ask: would a 5km-from-road candidate in dense FMZ 16 actually be the same kind of "hidden" as a 5km-from-road candidate in the Kawarthas? It wouldn't. Per-region.

### Schema additions

**Plan Mode prompt**: "Add scoring columns to the candidates table:
- h_score FLOAT (per-region normalized 0-1, hiddenness)
- a_score FLOAT (global 0-1, accessibility)
- a_dist_to_trail_m FLOAT (raw input)
- a_dist_to_parking_m FLOAT (raw input)
- f_score FLOAT (global 0-1, fish potential)
- f_confidence TEXT CHECK (f_confidence IN ('strong', 'plausible', 'speculative', NULL))
- f_species TEXT (comma-separated for display)
- f_inferred_from_ara_id TEXT (which ARA point provided the inference, NULL for speculative)
- f_graph_distance INT (hops in connectivity graph from nearest ARA-anchored candidate, NULL if direct or speculative)
- e_score FLOAT (global 0-1, ecology bonus)

Most are nullable — they get populated by the scoring scripts. Show me the migration before generating."

### H — Hiddenness score (per-region)

**Plan Mode prompt**: "Write `backend/scoring/score_hiddenness.py`. Hiddenness is a function of:
1. dist_to_road_meters (already populated)
2. name is NULL or 'NaN' (small additive boost — unnamed water bodies are less likely to be in guidebooks)

Normalization: **percentile-rank dist_to_road_meters within fmz_zone**. Use a window function partitioned by fmz_zone:

UPDATE candidates SET h_score = sub.h FROM (
  SELECT id,
    PERCENT_RANK() OVER (PARTITION BY fmz_zone ORDER BY dist_to_road_meters) AS h
  FROM candidates
  WHERE [active candidate filter]
) sub WHERE candidates.id = sub.id;

Then add 0.1 to h_score for unnamed candidates, clip to 1.0. Show SQL before generating."

Verify:
- [x] Window function PARTITIONS BY fmz_zone — confirmed in the SQL
- [x] Active-candidate filter is applied
- [x] After running, `SELECT fmz_zone, MIN(h_score), AVG(h_score), MAX(h_score) FROM candidates GROUP BY fmz_zone;` — both regions should range 0 to ~1.0 with average near 0.5 (it's a percentile rank)

### A — Accessibility score (global)

**Plan Mode prompt**: "Accessibility means 'easy for an angler to physically get to.' Two raw inputs:
1. Distance to nearest trail (OSM ways with highway IN ('path', 'footway', 'cycleway', 'track'))
2. Distance to nearest parking (OSM nodes/ways with amenity='parking')

Write `backend/ingest/trails_and_parking.py` to ingest these from OSM (OSMnx or Overpass) into trails and parking tables, using ROADS_BBOX. Then write `backend/scoring/score_accessibility.py` that:
- Updates a_dist_to_trail_m and a_dist_to_parking_m via spatial nearest-neighbor query (same KNN pattern as roads)
- Computes a_score = 1 - clip(min(dist_to_trail, dist_to_parking) / 2000, 0, 1)
  - At 0m from trail or parking: a_score = 1.0
  - At ≥2000m: a_score = 0.0
  - Linear in between
- This is global — same formula in both FMZs.
- 2000m threshold is in config.py as ACCESSIBILITY_DECAY_M

Show plan before generating, especially the OSM ingestion approach (cache, idempotent, etc.)."

Verify:
- [x] OSM ingestion follows the same caching pattern as Phase 1's roads.py and uses ROADS_BBOX
- [x] Threshold is configurable, not magic
- [x] Edge case: candidates with no trail OR parking within any reasonable distance get a_score = 0 (not NULL)

### E — Ecology bonus (global)

**Plan Mode prompt**: "Write `backend/ingest/landcover.py` to ingest SOLRIS landcover for the COMBINED_BBOX, then `backend/scoring/score_ecology.py` that computes ecology score per candidate:
- Buffer each candidate by 100m
- Compute % of buffer area that is 'forested' or 'wetland' landcover (SOLRIS class codes — verify the codes during ingestion)
- e_score = forested_or_wetland_pct (already 0-1, global)

Buffer + intersection on hundreds of thousands of candidates × landcover polygons is expensive. Plan should propose: rasterize landcover to a single raster, then use raster summary statistics per candidate buffer. Or, if vector-only is preferred for simplicity, restrict to candidates above a certain size.

Make a recommendation and show the plan."

Verify:
- [x] SOLRIS class codes are explicitly identified (don't assume)
- [x] Performance approach is justified — at this scale, raster-based is probably necessary
- [x] Default for skipped candidates is documented (don't leave NULL — set a sensible default like 0.3)

### F — Fish potential (global, leverages the cross-region graph)

This is the most complex of the four. It depends on ARA snaps + connectivity graph + species values. **Critical**: the graph traversal can cross FMZ boundaries, so an FMZ 16 candidate connected to an FMZ 17 ARA point gets that point's species via inference. This is the whole reason we built the cross-region graph.

**Plan Mode prompt**: "Write `backend/scoring/score_fish_potential.py`. Algorithm:

For each active candidate:
1. **Strong tier**: If the candidate has any ARA point snapped to it (via ara_points.snapped_candidate_id), parse its fish_species_summary, look up each species in species_values, sum the weights. Take the union across multiple ARA points if more than one is snapped (every species ever observed counts; track the most recent survey_date in metadata). Normalize the raw sum: divide by some 'max plausible' value (sum of weights of top 5 species in your CSV) and clip to 1.0. f_confidence = 'strong'. f_inferred_from_ara_id = the ARA ID with the most recent survey.

2. **Plausible tier**: If no ARA snapped directly, BFS the connectivity graph from this candidate (the graph spans FMZ 16 and FMZ 17 — do not filter by fmz_zone), find the nearest ARA-anchored candidate, take its species list with a discount factor of 0.7^graph_distance (so 1 hop = 0.7x, 2 hops = 0.49x, etc.). f_confidence = 'plausible'. Cap graph_distance at 5 hops; beyond that, fall through to speculative.

3. **Speculative tier**: No graph path to any ARA-anchored candidate within 5 hops. f_score = candidate_type prior:
   - polygon (lake/pond): 0.3
   - reach_segment (stream): 0.2
   f_confidence = 'speculative'. f_species = NULL. f_inferred_from_ara_id = NULL.

Implementation: graph traversal in Python (networkx loaded from candidate_edges, all rows, not filtered by region) is simpler than recursive CTEs in SQL for this. Show the algorithm + the data loading approach before generating."

Verify:
- [x] Graph traversal does not filter by fmz_zone (cross-region inference works)
- [x] Graph distance is computed correctly (BFS, not weighted)
- [x] Discount factor 0.7^d is configurable (F_GRAPH_DISCOUNT in config)
- [x] Species name matching is case-insensitive and trimmed
- [x] Species not in species_values table get weight 0 (not NULL)
- [x] Performance: pre-load species_values into a dict, pre-load ARA snaps into a dict keyed by candidate_id

### Sanity checks across all four components

- [x] `SELECT fmz_zone, candidate_type, AVG(h_score), AVG(a_score), AVG(f_score), AVG(e_score) FROM candidates GROUP BY fmz_zone, candidate_type;` — averages should be in the 0.2-0.6 range, not all 0 or all 1. H average should be ~0.5 in both regions (it's a percentile). The other three may differ between regions, which is informative.
- [x] `SELECT fmz_zone, f_confidence, COUNT(*) FROM candidates GROUP BY fmz_zone, f_confidence ORDER BY fmz_zone, f_confidence;` — distribution per region. Expect FMZ 17 to have a higher fraction of 'strong' and 'plausible'; FMZ 16 to have more 'speculative'. If they're identical, something's wrong with how the graph is propagating.
- [x] **Cross-region inference check**: pick a candidate in FMZ 16 with f_confidence='plausible' and look up `f_inferred_from_ara_id`. Find that ARA point. Is it in FMZ 17? If yes, the cross-region inference is working as designed. Find a few of these — they're the strongest evidence that "doing both regions together" was the right call.
- [x] Pick the highest h_score candidate in each FMZ separately. Look at each in QGIS. Do they make sense within their respective regions?
- [x] Pick a candidate with strong f_confidence and look at f_species. Do the species match the species_values weights?

### Merge to main

- [x] Branch sanity check: all four scores populated in both regions, no NULL contamination, distributions look right
- [x] Merge `phase-2/07-scoring` to `main`
- [x] **Run the integration smoke test from Part 9 NOW as a midpoint check, before frontend work starts**

---

## Part 8 — API + frontend updates (5-7 hours)

Surface sub-scores, FMZ identity, confidence tiers, and weight controls in the UI. The frontend gets a region filter so users can focus on one zone or see both.

### Update the API

**Plan Mode prompt**: "Update `backend/api/main.py`:

1. GET /candidates accepts query parameters:
   - w_h, w_a, w_f, w_e (each float, default 0.25). Validate they sum to ~1.0 (within 0.01 tolerance) or normalize.
   - fmz (optional string, 'FMZ16' or 'FMZ17' or omitted for both)
2. Composite score computed at query time: composite = w_h*h_score + w_a*a_score + w_f*f_score + w_e*e_score
3. **Rank is computed per-FMZ** using a window function: `RANK() OVER (PARTITION BY fmz_zone ORDER BY composite DESC NULLS LAST)`. Users see 'rank 1 of 8,123 in FMZ 16' style displays.
4. If fmz query param is set, filter to that region. If not, return both with their per-region ranks.
5. Order results by composite DESC across the full result set (ties broken by id).
6. Response properties expand to include: fmz_zone, h_score, a_score, f_score, e_score, f_confidence, f_species, a_dist_to_trail_m, a_dist_to_parking_m, dist_to_road_meters, composite, rank (per-region).
7. Filter out reach_full rows that have segmented children using WHERE is_active = TRUE (per Part 3's decision). This is the active-candidate filter; every scoring query and every API query uses it.
8. Add GET /health endpoint (simple, returns {status: ok}).
9. Add GET /regions endpoint that returns the list of available FMZs with candidate counts (for the frontend region selector).

Update the Pydantic models accordingly. Show the diff before generating."

Verify:
- [ ] Weight validation is forgiving (normalize rather than 400-error on small float drift)
- [ ] Active-candidates filter is applied
- [ ] Rank window function partitions by fmz_zone
- [ ] f_species is passed through as text (frontend will format)
- [ ] Response payload size — at two-FMZ scale this might be 100k+ features and 100MB+. Default behavior should probably be to require an fmz parameter, OR cap responses at top N by composite. Plan should flag this and propose a strategy.

### Update the frontend panel

**Plan Mode prompt**: "Update CandidatePanel and CandidateDetail in `frontend/components/panel/`:

1. Add a region selector at the top of the panel: radio buttons or pill toggle for 'FMZ 16', 'FMZ 17', 'Both'. Default to 'Both'. Selection changes the `fmz` query param on the next /candidates fetch.

2. Each candidate's list item shows a small FMZ badge ('16' or '17') alongside the rank badge. Subtle but visible.

3. Detail card: show four horizontal score bars (H, A, F, E) with the composite at top. Bars colored by score. Below the bars, show raw inputs and the FMZ ('FMZ 16' or 'FMZ 17') prominently. Rank now shows as 'Rank #N of M in FMZ 17' to make per-region semantics explicit.

4. Confidence tier displayed as a colored badge next to the candidate name: green for strong, amber for plausible, gray for speculative.

5. List items: keep the rank badge, add the small FMZ badge, add a tiny confidence indicator.

6. Weight controls: four sliders at the top of the panel (H, A, F, E), each 0-1, defaulting to 0.25. On change, re-fetch /candidates with the new weights (debounced 300ms). Show the current numeric values next to each slider.

7. Layout: panel is now denser; consider expanding the default width from 320 to 360px.

Show the component diffs before generating, especially: (a) where region selector state lives (page.tsx or panel?), (b) whether the map view also re-filters when region changes, (c) slider state management."

Verify:
- [ ] Slider re-fetch is debounced (300ms is reasonable)
- [ ] Loading state during re-fetch is visible (subtle spinner or fade), not jarring
- [ ] Region selector triggers both panel update AND map source data update
- [ ] Color-coding for confidence is accessible (don't rely on color alone — also use letter or icon)
- [ ] **Run `npm run build` after every component change.** TypeScript build errors don't surface in dev mode (Phase 1 lesson).

### Map updates

- [ ] Color expression on map layers should now use the composite score, not normalizedRank. Expose composite as a feature property.
- [ ] On weight change OR region change, the map source data updates → layer recolors automatically (Mapbox handles this if `data` prop reference changes — make sure the parent uses `useMemo` correctly)
- [ ] Map should `fitBounds` to the selected region when the user changes selection (FMZ 16 only → zoom to FMZ 16 envelope; both → zoom to combined envelope). Use the regions endpoint or hardcode the envelopes for v1.
- [ ] Optional: tint reach_segments slightly differently from polygons so the panel and map agree on type at a glance

### Merge to main

- [ ] Branch sanity check: app loads with both regions, region selector works, weights work, scores display, map zooms correctly per region selection
- [ ] Merge `phase-2/08-api-frontend` to `main`

---

## Part 9 — End-to-end integration smoke test, both regions (1-2 hours)

This is not a polish step. It's a verification step that everything still works together across both regions. **Run it at the midpoint (after Part 7) and again at the end (before tagging).**

- [ ] Stop everything. Restart Docker, restart backend, restart frontend.
- [ ] Open `http://localhost:3000`.
- [ ] Map loads with custom basemap, scoped to combined FMZ 16 + FMZ 17 region.
- [ ] No candidates in Lake Ontario, Lake Simcoe shoreline anomalies absent. (If any, Part 1 land mask broke. Stop and fix.)
- [ ] Both polygons and reach_segments visible on map across both regions.
- [ ] Side panel shows ranked list. Region selector defaults to 'Both' or to one — check both modes.
- [ ] Switch region selector to 'FMZ 16' only — map zooms, list filters, ranks show 'in FMZ 16.' Top 5 candidates change.
- [ ] Switch to 'FMZ 17' — same behavior, different candidates, ranks show 'in FMZ 17.'
- [ ] Click a top candidate in each region. Detail card opens. All four sub-scores display, FMZ shows correctly, raw inputs display, f_species shows actual species names from your CSV.
- [ ] Confidence badge displays correctly. Strong/Plausible/Speculative distribution should look notably different between regions — FMZ 17 with more 'strong' due to better ARA coverage.
- [ ] Adjust weight sliders. Top candidates change as expected within each region. (Set w_f=1.0; the top candidates should be ARA-anchored ones with the most valuable species.)
- [ ] **Cross-region inference verification**: with region='Both' and w_f=1.0, find a candidate in FMZ 16 ranked highly with `f_confidence='plausible'` and `f_inferred_from_ara_id` pointing to an ARA point in FMZ 17. This is the "cross-region graph paid off" check. If you can't find one, the graph isn't bridging the boundary correctly.
- [ ] Pick one of your Phase 0 manual gem candidates (Scarborough/Rouge area, FMZ 16) and one of your real Pickering/Ajax fishing spots (FMZ 17). Search for each in the panel. Where do they rank within their respective regions? Does the rank match your intuition?
- [ ] Walk through the full data path one more time, out loud or in writing: shapefile → ingestion (with FMZ tagging) → simplification → land mask → segmentation (FMZ inherited) → cross-region connectivity graph → ARA snap → species lookup → four-component scoring (H per-region, others global) → API (per-region rank) → frontend → pixel. You should be able to explain every hop without hesitating, including which steps are per-region and which are global.
- [ ] If anything fails: do not declare Phase 2 done. Open a fix branch off main, fix, re-run smoke test.

---

## Part 10 — Reflection and commit (45-60 min)

Same prompts as Phase 1, plus Phase-2-specific ones, plus dual-region prompts.

### Document

- [ ] Update `README.md` with current state (note both FMZs are covered)
- [ ] Update `CLAUDE.md` with anything that changed about the architecture (especially: per-region normalization principle, cross-region graph)
- [ ] Create `docs/phase_2_reflection.md` answering:
  - What worked smoothly?
  - What took longer than expected, and why?
  - What surprised you about the data, the tooling, or the process?
  - What architectural decisions are you uncertain about?
  - **Looking at top-ranked candidates within FMZ 16: do they look defensible? How about in FMZ 17?**
  - **How different are the two regions in terms of confidence distribution? Did F-scoring degrade gracefully on the data-sparse side?**
  - **Did adding FMZ 17 in Phase 2 (rather than waiting) feel worth it? Specifically: did cross-region graph inference help any FMZ 16 candidates? How many?**
  - **Which of the four components is doing the most work in the rankings? Which feels weakest?**
  - **Was per-region H normalization the right call, or did it make scores feel weird?**
  - **Is the species_values weighting producing the rankings you wanted, or do you need to revisit the weights?**
  - What did you learn about Claude Code's working pattern on a multi-workstream, multi-region phase?
  - What's one thing you'd do differently starting Phase 2 over?

### Commit and tag

- [ ] `git add -A && git commit -m "Phase 2: four-component scoring across FMZ 16 + FMZ 17"`
- [ ] Push to GitHub
- [ ] Tag: `git tag phase-2-complete && git push --tags`

---

## Done criteria

You're done with Phase 2 when:
- [ ] App loads, with both FMZ 16 and FMZ 17 covered, including 200m reach segments in each
- [ ] All four sub-scores populated for active candidates in both regions
- [ ] Confidence tier (Strong/Plausible/Speculative) is visible per candidate
- [ ] FMZ identity is visible per candidate, and a region filter works
- [ ] Per-region ranks are displayed correctly
- [ ] Weight sliders work and re-rank within each region
- [ ] Top-ranked candidates within each region look defensible — none in Lake Ontario, none obviously absurd
- [ ] At least one demonstrable cross-region inference exists (FMZ 16 candidate inferred from FMZ 17 ARA via graph)
- [ ] You can explain every component's computation out loud, including which parts are per-region and which are global
- [ ] All workstream branches are merged to main
- [ ] Integration smoke test passes for both regions
- [ ] Repo is committed, tagged, documented

You do **not** need to:
- Have a routing layer (Phase 3 territory)
- Have done the first ground-truth trip (Phase 4 territory)
- Have a multi-agent layer (Phase 5 territory)
- Have weight calibration from trip outcomes (Phase 6 territory)
- Have FMZ 18 / further expansion (out of scope)
- Have Information Value scoring (Phase 6 territory)
- Have private-land filtering, regulation overlays, or stocking integration (Phase 5+ territory)
- Have a perfect ecology score — Phase 2's E is admittedly thin

---

## If you get stuck

**Scoring runtime is still painful even after simplification**: Check that simplification actually applied. `SELECT ST_NPoints(geom) FROM candidates LIMIT 10;` should show low vertex counts. If high, simplification didn't run during ingest. Re-run with explicit `ST_SimplifyPreserveTopology` in the INSERT. If counts are low and runtime is still bad, profile with EXPLAIN ANALYZE on the scoring query to identify the bottleneck.

**One FMZ has 10x the candidates of the other and skews everything**: Check `SELECT fmz_zone, COUNT(*) FROM candidates GROUP BY fmz_zone;`. If the ratio is wildly off from QGIS visual expectation, the centroid-containment filter is wrong somewhere. Most common cause: CRS mismatch between FMZ polygons and candidate centroids during the contains check.

**FMZ polygon download isn't on GeoHub**: The MNRF FMZ dataset is sometimes mirrored on data.ontario.ca. Or, last resort, derive the boundary from the regulations PDF — but this should not be necessary.

**Connectivity graph has way more edges than expected**: Tolerance might be too loose. Drop to 2m and rebuild. Conversely, if it has too few, raise to 10m. The right number is one that connects all segments of the same named river but doesn't connect adjacent unrelated ponds.

**Zero cross-region edges in the connectivity graph**: This means either (a) FMZ 16 and FMZ 17 don't actually share connected water (unlikely — Trent system, Oak Ridges Moraine creeks), or (b) the FMZ polygons have a buffer/gap at the boundary causing centroid-containment to miss boundary candidates entirely. Check by visualizing candidates near the FMZ 16/17 line in QGIS.

**ARA snap rate is very low (<20%) in one or both regions**: Check that ARA points are in the right CRS. 50m might be too tight — try 100m. If rates are still low at 100m, the survey program just doesn't cover that region well, which is itself useful information.

**Most FMZ 16 candidates are 'speculative' and most FMZ 17 are 'strong'**: This is probably correct and informative — it reflects the real-world ARA coverage asymmetry. Don't try to hide it. If it bothers you, it tells you where Phase 4 ground-truth trips have the most leverage (FMZ 16, where the system is least anchored).

**Species names don't match between ARA and species_values.csv**: Run the case-insensitive species inventory query from Part 6, then update your CSV. Consider doing the species name normalization at query time (LOWER + TRIM) instead of at ingest, so future ARA updates don't break joins.

**Composite scoring seems to favor only one component regardless of weights**: Sub-scores aren't on the same 0-1 scale. Check distributions per component per region. If H ranges 0-1 (good — it's a percentile) but A only ranges 0-0.4 (a lot of candidates are far from trails), weight 0.25 doesn't equally weight them. This is honest, not broken — but the user should see it. Document.

**You feel mid-phase scope creep tempting you**: Run `/scope-check`. The Phase 2 deliverable is at the top of this file. The "do not need to" list is at the bottom of the Done Criteria. Read both and re-narrow.

**You hit fatigue and integration is feeling unfixable**: This is what Part 0's mid-phase fatigue protocol is for. Stop, take a session off, run `/integration-check` next session, re-read Part 0.

---

## After Phase 2

Bring back to the next conversation:
- Your `phase_2_reflection.md` notes
- Screenshots of the working app: (a) FMZ 16 only, (b) FMZ 17 only, (c) both regions, with weight sliders set differently in each. Six screenshots minimum.
- Top 5 candidates in each FMZ under equal weights and under F-only weights — four lists, with rough coordinates and confidence tiers
- Which Phase 0 manual gem candidates surfaced (FMZ 16), and where they ranked
- Your Pickering/Ajax actual fishing spots (FMZ 17), and where they ranked
- Architectural decisions you're uncertain about
- Honest assessment: do the top-ranked composite candidates in each region feel like real spots you'd actually investigate? Yes for one region but not the other? — Phase 3 (routing) might need to come before Phase 4 ground-truth, or might not.

Then we plan Phase 3: routing layer (trail Dijkstra + off-trail least-cost path on a cost surface from slope and landcover), or — if Phase 2's output already feels actionable — we plan Phase 4 (first ground-truth trip).