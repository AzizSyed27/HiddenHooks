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
- Anthropic API (Claude) for the multi-agent reasoning layer (Phase 5 — in progress)
- Open-Meteo free weather API — forecast + ERA5 historical, no auth required

## Ports (local dev)
- PostgreSQL: 5432 (Docker)
- FastAPI: 8000 (`python -m uvicorn api.main:app --port 8000` from `backend/`)
- Next.js: 3000 (`npm run dev` from `frontend/`)

## Current phase: Phase 5 — multi-agent reasoning layer (in progress)
Region: FMZ 16 and FMZ 17 (full Ontario management zones; replaces the Phase 1 test
region of ~20 km around Rouge National Urban Park, Scarborough, ON).
Four scoring components: H (hiddenness), A (accessibility), F (fish potential), E (ecology).
Composite and per-FMZ rank are computed at query time by the API.
Phase 3 added Mapbox drive-time isochrone filter and per-candidate drive routing.
Phase 5 adds a multi-agent reasoning layer (Weather, Timing/Pressure, Species specialists
+ Coordinator) on top of Phase 2 scoring. Two new endpoints: `POST /agents/rerank` and
`POST /agents/trip-plan`. On-demand only, opt-in via UI buttons. Agents never fire
automatically on panel refresh.

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
| `backend/processing/snap_ara_to_candidates.py` | Snaps ARA survey points to nearest candidate geometry; populates join table |
| `backend/processing/build_connectivity.py` | Builds NetworkX reach graph spanning both FMZs; writes `candidate_edges` |
| `backend/scoring/score_hiddenness.py` | Normalises `dist_to_road_meters` → `h_score` (0–1, higher = more hidden) |
| `backend/scoring/score_accessibility.py` | Trail + parking proximity → `a_score` |
| `backend/scoring/score_fish_potential.py` | ARA BFS propagation → `f_score`, `f_confidence`, `f_species` |
| `backend/scoring/score_ecology.py` | Habitat/connectivity bonus → `e_score` |
| `backend/api/main.py` | `GET /health`, `GET /regions`, `GET /candidates` (weights, fmz, radius filter) |
| `frontend/lib/types.ts` | Shared TS types including `Weights`, `NearLocation`, `DriveTimeMin`, `DriveTimeData` |
| `frontend/app/page.tsx` | Orchestrator: state (fmz, weights, nearLocation, driveTimeMin), all handlers |
| `frontend/components/map/MapView.tsx` | Map layers; composite drives color via interpolate expression |
| `frontend/components/panel/CandidatePanel.tsx` | Panel with region selector, weight sliders, LocationFilter, detail card, ranked list |
| `frontend/components/panel/CandidateDetail.tsx` | Score bars (H/A/F/E + composite), confidence badge, raw inputs |
| `frontend/components/panel/LocationFilter.tsx` | Three-state location filter: off / setter (geo+manual+Nominatim) / active |

### Phase 3 — added
| File | Purpose |
|---|---|
| `backend/services/mapbox.py` | `get_drive_isochrone` (filter polygon) + `get_drive_directions` (route to parking); `MapboxAPIError`, `MapboxTimeoutError` |
| `backend/api/main.py` | Added `GET /candidates/{id}/drive-time?from_lat&from_lon`; `CandidateFeatureCollection` gains `isochrone_polygon` |

### Phase 5 — added
| File | Purpose |
|---|---|
| `backend/services/weather.py` | `get_weather_context(lat, lon)` — Open-Meteo forecast + ERA5 historical; `WeatherAPIError`, `WeatherTimeoutError`; dual in-memory cache (1h forecast TTL, 24h historical TTL) |
| `backend/services/conditions.py` | `get_day_category`, `get_season`, `get_time_of_day`, `get_all_conditions` — pure stdlib datetime classifiers; naive datetimes treated as Toronto local |

**Phase 5 Part 2 deviation**: time-of-day boundaries deviate from the checklist by design — fishing-context boundaries aligned with Ontario seasonal light, not office hours (dawn 05:00, morning 07:00, midday 12:00, evening 16:00, dusk 18:00, night 21:00).

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
- Drive-time filter: `near_lat`, `near_lon`, `drive_time_min` must all be provided together
  or not at all. Filter is a Mapbox isochrone polygon; candidates are filtered by
  `ST_Within(geom, ST_Transform(isochrone, 3161))`. Replaced the Phase 2 `radius_km` /
  `ST_DWithin` approach in Phase 3.
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
  and `handleDriveTimeChange`. Whichever fires last wins — no concurrent fetches.
- `handleLocationChange` and `handleRadiusChange` do **not** call `fitBounds`.
  The existing `useEffect([candidates, mapReady])` fires after every fetch and zooms
  to the returned candidates' bounding box — the correct view. Adding a pre-fetch
  fitBounds would race with this.
- `handleFmzChange` calls `fitBounds` to the FMZ bbox only when no drive-time filter is
  active (`!nearLocation || !driveTimeMin`). If filter is active, candidates useEffect
  handles positioning.
- Weight slider `min` is `0.01` (not `0`) — prevents all-zero weight state that
  would send sum=0 to the API and return 422.
- `FMZ_BBOXES` in `page.tsx` are hardcoded for v1 — should eventually be derived
  from `GET /regions` once that endpoint exposes bboxes.
- Active drive-time pill click is a **no-op** — pills do not toggle off. "Clear filter"
  is the only deactivation path. This avoids the confusing state where location is
  set but drive_time_min is null (which sends no filter param despite the filter appearing active).
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

## Phase 5 v1 limitations

- **Rerank result resets on any filter change**: `rerankResult` clears whenever `fetchCandidates`
  is called (weight/FMZ/location change). A 30-60s expensive ranking is lost on the next filter
  interaction. Smarter v2 behavior: filter the AI-ranked list to the current visible candidates
  rather than resetting. Deferred: full reset is simpler and safe; re-running is explicit.

- **"Plan this trip" button hidden once result shows**: Re-firing requires "← Back to scores"
  then clicking again. Deferred: "Re-plan" link is a Phase 5 UI iteration.

- **`top_n_mode` not exposed in UI**: Defaults to `composite`. Revisit if `f_score` mode
  proves useful for heavy fish-potential use cases.

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

## Phase 3 — drive-routing (added 2026-05-12)

Replacement scope for the deferred walk-time work. Sibling note to
"Phase 3 — walk-time deferred" — these are distinct features. Drive-routing
fills the actionability gap walk-time was meant to fill (moving the detail
card from "within 30 min" — the isochrone cap — to "Drive: 23 min (18.3 km)"
with the actual route visible on the map). Lands on branch
`phase-3/04c-drive-routing` as seven pieces.

**What it adds**:
- `backend/services/mapbox.py`: `get_drive_directions(start_lat, start_lon, end_lat, end_lon)` — Mapbox Directions API client. Same exception classes (`MapboxAPIError`, `MapboxTimeoutError`), same token hygiene as `get_drive_isochrone` (token in `params=`, never URL; no `str(exc)`; 200-char response snippet limit).
- `backend/api/main.py`: `GET /candidates/{candidate_id}/drive-time?from_lat=X&from_lon=Y` — returns drive_time_min, drive_distance_km, route_geometry, parking_lat, parking_lon, error. Single LATERAL JOIN combines existence check and nearest-parking lookup; 0 rows → 404, 1 row with `parking_id IS NULL` → graceful "No parking found" 200, 1 row with values → Mapbox call.
- `backend/api/main.py`: `CandidateFeatureCollection` gains optional `isochrone_polygon` field — already-computed isochrone serialized as GeoJSON Polygon/MultiPolygon in EPSG:4326. No extra Mapbox call.
- `frontend/lib/types.ts`: `DriveTimeData` interface mirroring the backend response; `isochrone_polygon` slot on `CandidateCollection`.
- `frontend/app/page.tsx`: drive-time fetch effect on `[selectedId, nearLocation, driveTimeMin]`. AbortController guards every then/catch/finally with `signal.aborted` checks so the response that paints is always the response for the currently-selected candidate.
- `frontend/components/panel/CandidateDetail.tsx`: drive-time text line under the rank line ("Drive: X min (Y km) from your location" / "Computing drive time..." / error text). "Get directions to parking" anchor at the bottom of the card (universal Google Maps URL, opens in new tab).
- `frontend/components/map/MapView.tsx`: route line as a blue `#2563eb` 3.5px layer above the candidate fills (NOT in `interactiveLayerIds`). Isochrone polygon as a translucent slate fill (15%) + slate-600 outline (50%), both via `beforeId="poly-fill"` so they stack below candidates.

**Lazy-fetch + abort-on-change**: drive-time is per-candidate-selection. A list-render fetch would blow the Mapbox 100k/month free tier; selection-only keeps the call count proportional to user attention. `driveTimeAbortRef` is a `useRef<AbortController>` separate from the existing `debounceRef` (debounce is for input changes, abort is for stale-response prevention).

**Failure path is unified**: a fetch failure leaves `driveTimeData.route_geometry === null` and `driveTimeData.parking_lat === null`. The map's conditional render therefore draws no route, and the directions button does not render. Map state and detail card state stay in sync without separate cleanup logic.
