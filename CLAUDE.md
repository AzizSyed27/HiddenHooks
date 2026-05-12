# HiddenHooks

A geospatial tool for finding under-fished water bodies in Ontario.
Combines hydrology data, fish survey data, terrain, and accessibility
into a scored ranking. Personal/portfolio project.

## Tech stack
- Python 3.11 backend (FastAPI, GeoPandas, OSMnx 2.x, NetworkX, PostGIS via SQLAlchemy + psycopg2)
- PostgreSQL 16 + PostGIS 3.4 in Docker (port 5432); conda env: `hiddenhooks`
- Next.js 16 (App Router), React 19, TypeScript
- react-map-gl 8 — import from `react-map-gl/mapbox` (dual-export; bare `react-map-gl` doesn't work)
- Mapbox GL JS 3 for map rendering with a custom muted basemap style
- Tailwind CSS 4 + shadcn/ui — installed components: button, card, badge, sheet
- Framer Motion 12, Lucide React
- Fonts: Poppins (`--font-sans`, UI chrome) and Lora (`--font-serif`, candidate names)
- Anthropic API (Claude) for the multi-agent reasoning layer (later phases)

## Ports (local dev)
- PostgreSQL: 5432 (Docker)
- FastAPI: 8000 (`python -m uvicorn api.main:app --port 8000` from `backend/`)
- Next.js: 3000 (`npm run dev` from `frontend/`)

## Current phase: Phase 2 — in progress
Region: FMZ 16 and FMZ 17 (full Ontario management zones; replaces the Phase 1 test
region of ~20 km around Rouge National Urban Park, Scarborough, ON).
Four scoring components: H (hiddenness), A (accessibility), F (fish potential), E (ecology).
Composite and per-FMZ rank are computed at query time by the API.

## Key files

### Phase 1
| File | Purpose |
|---|---|
| `backend/config.py` | All paths, `DATABASE_URL`, `TEST_BBOX`, `ROADS_CACHE_PATH` |
| `backend/ingest/ohn_waterbody.py` | OHN waterbody → `candidates` (type: polygon) |
| `backend/ingest/ohn_watercourse.py` | OHN watercourse → `candidates` (type: reach_full) |
| `backend/ingest/roads.py` | OSM road network → `roads`; GraphML cache in `cache/` |
| `backend/scoring/dist_to_road.py` | PostGIS KNN UPDATE on `dist_to_road_meters` for all `is_active = TRUE` candidates |

### Phase 2 — added
| File | Purpose |
|---|---|
| `backend/scoring/snap_ara_to_candidates.py` | Snaps ARA survey points to nearest candidate geometry; populates join table |
| `backend/scoring/build_connectivity.py` | Builds NetworkX reach graph spanning both FMZs; writes `candidate_edges` |
| `backend/scoring/score_hiddenness.py` | Normalises `dist_to_road_meters` → `h_score` (0–1, higher = more hidden) |
| `backend/scoring/score_accessibility.py` | Trail + parking proximity → `a_score` |
| `backend/scoring/score_fish_potential.py` | ARA BFS propagation → `f_score`, `f_confidence`, `f_species` |
| `backend/scoring/score_ecology.py` | Habitat/connectivity bonus → `e_score` |
| `backend/api/main.py` | `GET /health`, `GET /regions`, `GET /candidates` (weights, fmz, radius filter) |
| `frontend/lib/types.ts` | Shared TS types including `Weights`, `NearLocation`, `RadiusKm` |
| `frontend/app/page.tsx` | Orchestrator: state (fmz, weights, nearLocation, radiusKm), all handlers |
| `frontend/components/map/MapView.tsx` | Map layers; composite drives color via interpolate expression |
| `frontend/components/panel/CandidatePanel.tsx` | Panel with region selector, weight sliders, LocationFilter, detail card, ranked list |
| `frontend/components/panel/CandidateDetail.tsx` | Score bars (H/A/F/E + composite), confidence badge, raw inputs |
| `frontend/components/panel/LocationFilter.tsx` | Three-state location filter: off / setter (geo+manual+Nominatim) / active |

## Established conventions and gotchas

### Database / ingest
- Geometry stored in EPSG:3161 (Ontario MNR Lambert, metric). Served to frontend as
  WGS84 via `ST_Transform(geom, 4326)` in the candidates SQL query.
- Candidates table uses `geometry(Geometry, 3161)` — generic type accepting both
  Polygon and LineString in one column.
- Ingest is UPSERT via partial unique indexes, NOT delete+insert. `parent_candidate_id`
  references `candidates.id` — DELETE+INSERT would either cascade-nuke Phase 2
  `reach_segment` rows or fail with FK violations.
- Three `candidate_type` values: `polygon` (lakes/ponds), `reach_full` (original
  watercourse features), `reach_segment` (segmented reaches from Phase 2). Parents
  (`reach_full`) that were segmented have `is_active = FALSE`; their segments are
  `is_active = TRUE`.
- **`is_active = TRUE` is the canonical "active candidates" filter** in all SQL — never
  filter on `candidate_type IN (...)`. This is what populates the map and drives scoring.

### Scoring architecture
- **Per-region normalization**: scores are normalised within each FMZ independently.
  `RANK() OVER (PARTITION BY fmz_zone ORDER BY composite DESC)` — rank 1 is the
  top composite within that FMZ, not globally. When radius filter is active,
  `fmz_total` reflects candidates within the radius, not the full FMZ count.
- **Cross-region graph**: `build_connectivity.py` builds a single NetworkX graph
  spanning both FMZ 16 and FMZ 17. Reach connectivity is not scoped per-region —
  a reach in FMZ 17 can be connected to one in FMZ 16 if the underlying watercourse
  crosses the boundary. BFS for fish potential propagation runs on this unified graph.
- **Isolated node crash (score_fish_potential.py)**: `G.add_edges_from()` only adds
  nodes that appear in at least one edge. ARA-anchored candidates with no rows in
  `candidate_edges` would crash on `G.neighbors()`. Fix: `G.add_nodes_from(ara_map.keys())`
  before BFS so every ARA anchor is present regardless of connectivity.
- `dist_to_road_meters` is populated by `scoring/dist_to_road.py`, not ingest. Runs
  on all `is_active = TRUE` candidates (~8 min for a full FMZ run on PostGIS KNN).

### API
- `GET /candidates` accepts weights `w_h`, `w_a`, `w_f`, `w_e` (floats, default 0.25
  each). Server normalises them to sum=1. Weight sum ≤ 0 returns 422.
- Composite is computed at query time via a CTE:
  `COALESCE(:w_h * h_score, 0) + COALESCE(:w_a * a_score, 0) + ...`
  COALESCE treats NULL component scores as 0 — safe when pipeline is partially run.
- `rank` is computed by `RANK() OVER (PARTITION BY fmz_zone ORDER BY composite DESC NULLS LAST)`.
  `fmz_total` is `COUNT(*) OVER (PARTITION BY fmz_zone)` — window functions fire before
  LIMIT so fmz_total is accurate regardless of the response limit.
- `total_count` on the FeatureCollection is the pre-LIMIT matching count (cross-joined
  from a `total AS (SELECT COUNT(*) FROM scored)` CTE).
- Radius filter: `near_lat`, `near_lon`, `radius_km` must all be provided together or
  not at all. Uses `ST_DWithin` with the stored EPSG:3161 geometry — no index needed
  beyond the existing GiST index.
- `normalizedRank` no longer exists — `composite` (0–1 float) is used directly for
  both map coloring and panel badge colors.
- SQL fragments `{fmz_filter}` and `{radius_filter}` are formatted in Python, not
  passed as nullable params, to avoid PostgreSQL null-in-parameterized-query ambiguity.

### Frontend
- `react-map-gl/mapbox` v8 event type is `MapMouseEvent` (from mapbox-gl), NOT
  `MapLayerMouseEvent`. The latter does not exist in this version.
- `SheetTitle` from shadcn wraps Radix `Dialog.Title` and requires being inside a
  `<Sheet>` (Dialog) context. Do not use it outside the Sheet wrapper — use a plain
  `<h2>` instead.
- The side panel is a `motion.div` (not a Sheet Dialog) to avoid modal behavior
  conflicting with Mapbox map interactions. `SheetHeader` (a plain div) is reused
  for consistent spacing.
- In React 19, `useRef<T>(null)` returns `RefObject<T | null>`. Prop types for refs
  should be `React.RefObject<T | null>`, not `React.RefObject<T>`.
- **Single `debounceRef`** is shared across `handleWeightsChange`, `handleLocationChange`,
  and `handleRadiusChange`. Whichever fires last wins — no concurrent fetches.
- `handleLocationChange` and `handleRadiusChange` do **not** call `fitBounds`.
  The existing `useEffect([candidates, mapReady])` fires after every fetch and zooms
  to the returned candidates' bounding box — the correct view. Adding a pre-fetch
  fitBounds would race with this.
- `handleFmzChange` calls `fitBounds` to the FMZ bbox only when no radius filter is
  active (`!nearLocation || !radiusKm`). If filter is active, candidates useEffect
  handles positioning.
- Weight slider `min` is `0.01` (not `0`) — prevents all-zero weight state that
  would send sum=0 to the API and return 422.
- `FMZ_BBOXES` in `page.tsx` are hardcoded for v1 — should eventually be derived
  from `GET /regions` once that endpoint exposes bboxes.
- Active radius pill click is a **no-op** — pills do not toggle off. "Clear filter"
  is the only deactivation path. This avoids the confusing state where location is
  set but radius is null (which sends no radius param despite the filter appearing active).
- `NearLocation.accuracy` (metres, browser geolocation only) is displayed as `±N km`
  in the panel. Highlighted orange if accuracy > 1000 m.

## Key design principles
- Decision support, not automation. Show all candidates, never hide.
- Confidence is a first-class output alongside score (Strong / Plausible / Speculative).
- Scoring is multi-component (Hiddenness, Accessibility, Fish potential,
  Ecology bonus); weights are tunable per query.
- Stream reaches are candidate units alongside lakes/ponds — a famous
  river can have a hidden 300m reach worth surfacing.
- The tool should look like something a serious angler would trust:
  cartographic, not corporate. Field-guide-meets-satellite-tool aesthetic.

## Working preferences
- Ask clarifying questions before implementing anything non-trivial.
- For architectural decisions, present 2-3 options with tradeoffs
  before recommending one.
- Use Plan Mode for anything beyond trivial code generation. Show me
  the plan before writing files.
- When I push back on a suggestion, engage with the pushback rather
  than immediately changing course. If you still think your original
  suggestion was right, defend it.
- I retain concepts better through interrogation than passive
  explanation, so explain reasoning even when I haven't asked.
- If you don't know something, say so. Don't invent API signatures
  or library behaviors.
- If something I'm asking for is a bad idea, push back before
  implementing it.
- Decisions about what feels like a good fishing spot, what species
  matter, or how the UI should feel are mine to make. Give me options,
  don't decide for me.

## Repo policy
- Repo is private during development.
- Future state: portfolio-visible with a "look but don't reuse" license.
- Trip data (actual GPS coordinates of validated spots) is never
  committed. Trip logs go in a gitignored `private/` folder.

## Known issues

**OHN NaN string normalization**: The `.where()` chain in `backend/ingest/ohn_waterbody.py`
and `backend/ingest/ohn_watercourse.py` is supposed to convert literal `"NaN"` strings in
the `name` column to NULL but doesn't take effect (root cause not yet diagnosed — the logic
looks correct on inspection). After every re-ingestion of waterbody or watercourse data,
manually run:
```sql
UPDATE candidates SET name = NULL WHERE name = 'NaN';
```
Verify with `SELECT COUNT(*) FROM candidates WHERE name = 'NaN';` returning 0 before
proceeding to downstream scoring or graph operations.

## Phase 3 — walk-time deferred (concluded 2026-05-12)

Phase 3 ships Parts 1-3 (drive-time isochrone filter via Mapbox). Parts 4-6
(NetworkX trail graph, walk-time endpoint, walk-time UI) are deferred to Phase 6
pending better trail data. The investigation that drove the deferral:

**Approaches tried**:
1. NetworkX with spatial-hash snap on trail vertices; tolerance sweep 5/10/15/20 m.
2. pgRouting `pgr_nodeNetwork` + `pgr_createTopology` at 10 m tolerance
   (Option B from the investigation plan).

**Numbers (both approaches similar)**:

| Approach | Components | Largest component | Largest as % of total | Petticoat probe component |
|---|---|---|---|---|
| NetworkX, 5 m   | 26,705 | 9,219 nodes (every internal vertex) | ~1%  | 8-14 nodes / 120 m × 250 m |
| NetworkX, 20 m  | 24,831 | 6,377 nodes                          | ~1%  | similar                    |
| pgRouting, 10 m | 25,849 |   466 nodes (endpoints only)         | 0.36% | 6 nodes / 122 m × 261 m   |

The two graph representations aren't directly comparable on raw node counts
(NetworkX has every internal LineString vertex; pgRouting has endpoints only),
but they tell the same story in component count and Petticoat behavior.

**Diagnosis**: Gap distribution between unrelated OSM trail features in this
region is concentrated at 10-30 m, not the 0-2 m intersection cluster a
well-noded dataset would show. `pgr_nodeNetwork` did detect mid-segment
crossings — it split 25,187 of 80,772 edges (31%) — but that fixed a different
problem than the dominant one. The OSM data is missing structural connectivity,
not just snap tolerance. Increasing tolerance further would either help
marginally or start falsely merging parallel-but-separate trails.

**What data would change the decision**:
- Re-ingestion of OSM via OSMnx with preserved OSM node IDs (would replace
  the spatial-hash dedup with real topological connectivity).
- OTN (Ontario Trail Network) layered in alongside OSM — flagged as a candidate
  in Phase 0; OTN preserves trail topology more reliably.
- Manual gap-bridging in fishing areas (small-scale, high-ROI: bridge a few
  hundred known-bad gaps near Phase 4 candidate spots).
- pgRouting 4.x `pgr_extractVertices` (the successor to the removed
  `pgr_createTopology`) — if pgRouting 4.x's analyze tooling improves
  meaningfully, re-test then.

**pgRouting deprecation note (Phase 6 carry-forward)**: the investigation used
`pgr_createTopology`, which was deprecated in pgRouting 3.8 and removed in 4.0.
If Phase 6 revives walk-time on pgRouting, the production code must use
`pgr_extractVertices`. The Docker image `pgrouting/pgrouting:16-3.4-3.6.1` is
kept on master so the extension is available without a rebuild; the extension
itself is enabled in the running DB and is harmless when unused.

**Preserved branches** (do not delete):
- `phase-3/04-trail-graph` — NetworkX spatial-hash implementation (`backend/services/trail_graph.py` + lifespan integration)
- `phase-3/04b-pgrouting-investigation` — pgRouting topology build state + diagnostic SQL
