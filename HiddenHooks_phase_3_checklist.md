# HiddenHooks — Phase 3 Checklist

**Goal**: Replace the straight-line km radius filter with route-aware drive-time isochrones, build a trail-graph router on OSM data, and surface lazy-fetched walk-time on candidate selection. Total time (drive + walk) becomes the actionability primitive — the panel answers "is this candidate reachable today" alongside "is this candidate good."

**Deliverable**: A web page where the user picks a location and a drive-time preset (20 / 30 / 45 / 60 min); the panel shows ranked candidates within that drive-time isochrone. Click a candidate; the detail card lazily fetches walk-time from the parking-nearest-to-candidate to the candidate's trail-network entry, displayed as "Walk: 23 min via path" alongside the drive-time qualifier and existing four-component scores.

**Total time**: 3-4 weekends alongside other commitments. Smaller than Phase 2 in scope, but Mapbox integration and graph-building each have their own learning curve.

**Working partner**: Claude Code. The Phase 2 working pattern carries forward — Plan Mode for everything load-bearing, push back on bad ideas, integration smoke test as forcing function.

**Mindset**: Phase 3 is *routing*, not time estimation. Time falls out of routing because once the path is solved, "how long is the path" is trivial. The whole reason this phase is worth doing is "what trail should I take from parking to as-close-to-the-water-as-possible." The composite total time is a byproduct — useful, but not the design driver.

---

## Part 0 — Working with Claude Code on a routing-and-external-service phase (read first, do not skip)

Phase 1 was a single workstream. Phase 2 was five workstreams that had to integrate. Phase 3 is smaller — six workstreams — but introduces two failure modes Phase 2 didn't have: external service dependency (Mapbox) and in-memory routing state. Both reward discipline.

### Branch discipline

- [ ] Create a branch per workstream off `main`:
  - `phase-3/01-mapbox`
  - `phase-3/02-api-drive-time`
  - `phase-3/03-frontend-drive-time`
  - `phase-3/04-trail-graph`
  - `phase-3/05-walk-time-endpoint`
  - `phase-3/06-frontend-walk-time`
- [ ] Each branch merges back to `main` only after its own sanity check passes
- [ ] No four-week-old branches. Same Phase 2 rule: if a branch has been open more than a week, stop new work and integrate it
- [ ] Tag `phase-3-complete` only after the integration smoke test in Part 7 passes

### External service hygiene (new for this phase)

Phase 1 and 2 had no runtime dependencies outside the local stack. Phase 3 introduces Mapbox. Treat the API key as a secret, the API as fallible, and the failure mode as user-visible.

- [ ] `MAPBOX_API_KEY` lives in a `.env` file, loaded via `python-dotenv` (same pattern as `DATABASE_URL`)
- [ ] Verify `.env` is in `.gitignore` *before* the first commit that touches Mapbox code. Once a key is committed, even briefly, treat it as compromised and rotate.
- [ ] Missing key on app startup must fail fast with a clear error. The app must not start with `MAPBOX_API_KEY=None` and crash on first request.
- [ ] Mapbox failures (timeout, HTTP error, rate limit) return HTTP 503 from `/candidates` with a descriptive `detail` field. Do not crash, do not silently fall back, do not return 500.

### Lazy-fetch UX principle

Walk-time is computed per candidate via Dijkstra on the trail graph. Computing it for every candidate in the panel list is unworkable — 2000 Dijkstra runs per fetch is not a viable plan. The right pattern: walk-time is fetched only when the user opens a candidate's detail card. This means:

- The candidates list endpoint stays fast (no walk-time computation per row)
- The detail card has a brief loading state for walk-time
- "No trail route from parking" is a real terminal state to handle gracefully

Lock this design choice now. If you find yourself wanting to surface walk-time in the list, ask: do I want to compute Dijkstra 2000 times per panel update, or do I want a snappy panel?

### Pre-flight scoring-completeness check (lesson from Phase 2)

Before starting any new workstream that depends on candidate scoring, run:

```sql
SELECT COUNT(*) FROM candidates
WHERE is_active = TRUE
  AND (h_score IS NULL OR a_score IS NULL OR f_score IS NULL OR e_score IS NULL);
-- Expect: 0
```

If it returns nonzero, the scoring pipeline state has drifted (most likely from a prior re-run that didn't complete). Fix it before building Phase 3 features on top.

### Pipeline ordering reminders (lesson from Phase 2)

Phase 2 caught a chronology bug where `dist_to_road.py` had a hardcoded `candidate_type IN ('polygon', 'reach_full')` filter that excluded reach_segments. The right pattern across the codebase is `WHERE is_active = TRUE`. Reinforce this for Phase 3:

- [x] Any new query in Phase 3 that filters candidates uses `is_active = TRUE`, not a hardcoded type list
- [x] If you find a stale type filter while working in Phase 3, fix it (don't just patch around it)
- [x] Document new pipeline dependencies in CLAUDE.md as you discover them

### The "you might be wrong" prompt

In Phase 2 you used "what's the case this approach is wrong, what would change at 100x scale, what edge cases haven't you considered" against simplification and connectivity. Apply it in Phase 3 to:

- The Mapbox 60-min cap (does the 4-preset set adequately cover your trip planning, or does the 60-min cap matter more in practice than expected?)
- The walk speed model (path = 4 km/h, track = 5 km/h — what would change at very different terrain types?)
- The trail graph node identity (5m snap tolerance — does that under- or over-connect at hiking-trail scale?)
- The "nearest parking" assumption (the parking already in `a_dist_to_parking_m` is the parking *nearest the candidate* — is that always the right parking, or could one slightly farther but reachable from a different road system be better?)

### Slash commands worth setting up

In addition to Phase 1's and Phase 2's slash commands, add to `.claude/commands/`:

- [x] `/route-explain` — Given a candidate ID and the current location filter, walk through the routing decisions: which parking, which trail node, what edges, what walk time, what failure mode if any.
- [x] `/mapbox-debug` — Given an isochrone request that returned an unexpected polygon, inspect the request URL, the response shape, and any rate-limit or quota signals.

### Mid-phase fatigue protocol (carries forward from Phase 2)

Same protocol, same symptoms. Phase 3 is shorter, but Mapbox debugging and graph correctness are both topics that can swallow a weekend. If you're skipping verification or writing without Plan Mode:

- [x] Don't push through. Pause for a session.
- [x] Re-read this Part 0 and the Phase 3 deliverable description.
- [x] Run the scoring-completeness query and the integration smoke test list to ground yourself in what's actually broken vs what *feels* broken.

### Schema and data hygiene reminders from Phase 2

- [x] Active candidates filter: `WHERE is_active = TRUE` everywhere
- [x] Frontend: `npm run build` after every TypeScript file change — dev mode hides type errors that production build catches
- [x] Restart uvicorn manually after API code changes if behavior doesn't match the file. The Phase 2 lesson about `--reload` being unreliable still applies.

---

## Part 1 — Mapbox Isochrones integration (1-2 hours)

This is the foundation for Part 2. Pure plumbing — bring Mapbox into the codebase as a thin client. No DB changes; no UI changes.

### Set up the API key

- [x] Sign in to your Mapbox account (you have one from Phase 1 for the basemap)
- [x] Account → Tokens → create a new token scoped only to the Isochrones API endpoint (don't reuse the public token from Phase 1)
- [x] Save in `backend/.env`: `MAPBOX_API_KEY=sk.your_token_here`
- [x] Verify `.env` is in `.gitignore` (it should be from Phase 1, but check)
- [x] If the file isn't there, create it. Restart your editor so VS Code's git integration sees the rule.

### Verify the Mapbox 60-min limit before locking presets

The Mapbox Isochrones API has historically capped `contours_minutes` at 60. This affects which presets the panel can offer. Before starting Part 1 implementation:

- [x] Read the current Mapbox Isochrones API reference at https://docs.mapbox.com/api/navigation/isochrone/
- [x] Confirm the `contours_minutes` maximum value as of today
- [x] If still 60: presets are 20 / 30 / 45 / 60 (locked decision below)
- [x] If higher (e.g., 90 or 120): re-evaluate whether to expand presets, and update Part 3 accordingly

### Locked design decisions

- Routing service: **Mapbox Isochrones API** (driving profile, typical traffic)
- Drive-time presets: **20 / 30 / 45 / 60 min** (Mapbox cap; revisit in Phase 6 if 60-min cap turns out to limit real trip planning)
- HTTP client: `requests` library (sync, simple)
- Polygon precision: 32 (Mapbox default; balances accuracy vs response size)
- Timeout: 5 seconds. Personal-use traffic; longer means Mapbox is degraded.
- Single-contour requests only. Even though Mapbox supports up to 4 contours per request, request once per minute value. Simpler logic.
- No request caching in v1. Each isochrone request hits Mapbox. If dev iteration becomes painful, add an in-memory cache later.

### Build the Mapbox client

**Plan Mode prompt**: "Create `backend/services/mapbox.py`. One function: `get_drive_isochrone(lat: float, lon: float, minutes: int) -> shapely.Polygon | shapely.MultiPolygon`. Calls the Mapbox Isochrones API at `https://api.mapbox.com/isochrone/v1/mapbox/driving/{lon},{lat}` with `contours_minutes={minutes}`, `polygons=true`, `access_token={MAPBOX_API_KEY}`. Returns the parsed geometry as a Shapely shape (in EPSG:4326). Defines two custom exceptions: `MapboxAPIError` (HTTP errors, missing/invalid response shape) and `MapboxTimeoutError(MapboxAPIError)` (timeout specifically). Caller catches and decides how to surface. Do not log the API key. Show the file before generating."

Verify in the plan:
- [x] API key read from env via `os.environ` (with a startup-time validation that it exists)
- [x] Request timeout configured (5s)
- [x] Response validation: features array exists, has at least one feature, geometry is non-empty
- [x] Returns `shape(features[0]['geometry'])` — Shapely handles both Polygon and MultiPolygon
- [x] Exception messages are informative but never include the API key
- [x] Module-level config (URL, timeout) is in `config.py`, not hardcoded in the service

### Verify the client manually

In a Python REPL with the project's environment activated:

```bash
cd backend
python -c "
import sys; sys.path.insert(0, '.')
from services.mapbox import get_drive_isochrone
poly = get_drive_isochrone(43.77, -79.26, 30)
print(f'Type: {poly.geom_type}, Bounds: {poly.bounds}, Area: {poly.area:.4f}')
"
```

- [x] Output shows Polygon or MultiPolygon
- [x] Bounds span roughly +/- 0.4 degrees from input
- [x] Area is non-zero
- [x] Test with bad API key (e.g., temporarily edit `.env` to a wrong value): expect MapboxAPIError, not a silent failure
- [x] Test with `minutes=99` (above cap): expect MapboxAPIError with descriptive message

### Merge to main

- [x] Branch sanity check: `services/mapbox.py` exists, manual REPL test passes, `.env` is gitignored
- [x] Merge `phase-3/01-mapbox` to `main`

---

## Part 2 — API: drive-time replaces radius filter (2-3 hours)

This is the user-facing contract change. The `radius_km` query param goes away; `drive_time_min` takes its place. The handler now makes an outbound Mapbox request before the database query, transforming the returned polygon to EPSG:3161 and using it as a `ST_Within` filter.

No DB schema changes.

### Plan the changes to `/candidates`

**Plan Mode prompt**: "Update `backend/api/main.py`'s `GET /candidates` endpoint:

1. Remove the `radius_km` query parameter entirely. No backward compat. Phase 3 frontend updates to match in Part 3.
2. Add `drive_time_min: int | None = Query(default=None, ge=1, le=60)`. Validation 1-60 reflects Mapbox's per-contour cap.
3. Cross-param rule: if `near_lat` or `near_lon` is provided, both must be (existing). `drive_time_min` is required when `near_*` is set; raises 422 if missing. `drive_time_min` without `near_*` raises 422.
4. When `near_*` and `drive_time_min` are all set: call `get_drive_isochrone(near_lat, near_lon, drive_time_min)`. Catch `MapboxTimeoutError` and `MapboxAPIError`, raise HTTPException(503, ...) with descriptive detail.
5. Pass the polygon's WKT into the SQL via a new `:isochrone_wkt` parameter. The scored CTE's existing `{radius_filter}` placeholder is replaced with `{isochrone_filter}`, which is either `''` or `'AND ST_Within(geom, ST_Transform(ST_GeomFromText(:isochrone_wkt, 4326), 3161))'`.
6. The existing `total_count`, `fmz_total`, ranking, weight, and limit logic all stay. The radius_filter → isochrone_filter swap is the only SQL change.
7. The `total_count` semantic stays correct: it's COUNT(*) FROM scored, which now reflects the isochrone-filtered set.

Show me the updated handler signature, the cross-param validation block, and the SQL template diff before generating."

Verify in the plan:
- [x] No `radius_km` references remain anywhere in the file
- [x] Cross-param validation order: weights, then near_lat/near_lon both-or-neither, then drive_time_min required when near_*, then drive_time_min requires near_*
- [x] Mapbox call happens *after* parameter validation (don't waste an API call on a request that's about to 422)
- [x] Isochrone polygon is constructed once per request, transformed once via `ST_Transform`, used in the GIST-indexed `ST_Within`
- [x] 503 includes a descriptive `detail` ("Drive-time service timeout" or "Drive-time service unavailable: ..."), never exposes the API key

### Verification

```bash
# Restart uvicorn first (the Phase 2 reload-gotcha applies here too)
cd backend && uvicorn api.main:app --reload --port 8000
```

In another terminal or browser:

- [x] **Baseline (no filter)**: `GET /candidates?fmz=FMZ16` — `total_count` matches pre-Phase-3 baseline. Existing functionality unchanged.
- [ ] **20-min filter**: `GET /candidates?near_lat=43.77&near_lon=-79.26&drive_time_min=20` — `total_count` is small (local-only). Eyeball the geometry coordinates: should all be within ~15-20km of Scarborough.
- [x] **30-min filter**: same as above with `drive_time_min=30`. Strictly more candidates than 20-min.
- [x] **45-min filter**: more again.
- [x] **60-min filter**: most. Coverage should reach Pickering, Whitby, into the Oak Ridges Moraine.
- [x] **Drive-time + FMZ filter**: `GET /candidates?fmz=FMZ16&near_lat=43.77&near_lon=-79.26&drive_time_min=45` — strict subset of `?drive_time_min=45` alone. All features have `fmz_zone='FMZ16'`.
- [x] **422 cases** — each must return 422 with a descriptive error:
  - `?near_lat=43.77` (missing near_lon)
  - `?near_lat=43.77&near_lon=-79.26` (missing drive_time_min)
  - `?drive_time_min=30` (no location)
  - `?near_lat=43.77&near_lon=-79.26&drive_time_min=99` (over Mapbox cap)
  - `?near_lat=51.0&near_lon=-79.26&drive_time_min=30` (lat out of Ontario range)
  - `?near_lat=43.77&near_lon=-70.0&drive_time_min=30` (lon out of Ontario range)
- [x] **503 case**: temporarily set `MAPBOX_API_KEY` to an invalid value, restart uvicorn, hit `?near_lat=43.77&near_lon=-79.26&drive_time_min=30`. Expect 503 with descriptive error. Restore the real key after.
- [x] **Empty result** (small radius in empty area): `?near_lat=42.0&near_lon=-83.0&drive_time_min=20` — returns `{"type":"FeatureCollection","features":[],"total_count":0}` cleanly.

### Merge to main

- [x] Branch sanity check: all verification cases pass; no `radius_km` references in code or comments
- [x] Merge `phase-3/02-api-drive-time` to `main`

---

## Part 3 — Frontend: drive-time UI (2-3 hours)

Replace the radius preset pills with drive-time pills. Same UX shape — user picks a location (geolocation, manual, or Nominatim), picks a preset, panel filters. State variable name and preset values change.

### Plan the type and state changes

**Plan Mode prompt**: "Update the frontend to replace the radius filter with a drive-time filter:

1. In `frontend/lib/types.ts`: rename `RadiusKm` to `DriveTimeMin`, with values `20 | 30 | 45 | 60`.
2. In `frontend/app/page.tsx`: rename `radiusKm` state to `driveTimeMin`, update `fetchCandidates` to send `drive_time_min` instead of `radius_km` in the URL, update all handler dependencies.
3. In `frontend/components/panel/CandidatePanel.tsx`: rename props (`radiusKm` → `driveTimeMin`, `onRadiusChange` → `onDriveTimeChange`, `onRadiusClear` → `onClear`).
4. In `frontend/components/panel/LocationFilter.tsx`: change pill values to 20/30/45/60, displayed labels to '20 min'/'30 min'/'45 min'/'60 min'. Four pills instead of three — they fit in a row but the spacing tightens slightly.
5. In `frontend/components/panel/CandidateDetail.tsx`: change rank line qualifier from 'within {n} km' to 'within {n} min'.

All other UI behavior unchanged: location picker (geolocation, manual, Nominatim), 'Clear filter' button, three display states (off / setter / active), no-op on active pill click, accuracy display when geolocation is used.

Show me the diff per file before generating."

Verify in the plan:
- [x] No `radius_km` or `RadiusKm` references remaining anywhere
- [x] Four-pill row fits in the existing panel width (360px from Phase 2)
- [x] Debounce ref is still shared across weights, location, and drive-time changes (Phase 2's "latest user action wins" pattern)
- [x] Rank line text update propagates to all places it renders

### Verification

- [x] `npm run build` passes — no TypeScript errors
- [x] Cold load: panel shows "Filter by distance from location" button (unchanged behavior)
- [x] Open setter, use geolocation: shows lat/lon + accuracy (if available) + 4 drive-time pills
- [x] Click "20 min": pill highlights, fetch fires, URL has `drive_time_min=20`. Returned candidates visibly closer to home than 30/45/60 sets.
- [x] Click "30 min": refetches, URL has `drive_time_min=30`. Strict superset of 20-min.
- [x] Click "60 min": refetches, URL has `drive_time_min=60`. Superset.
- [x] Click "60 min" again (active pill): no-op, no fetch fires, pill stays selected.
- [x] Click "Clear filter": both location and drive-time clear, map zooms back to FMZ/COMBINED bbox, fetch unfiltered.
- [x] Detail card on a filtered candidate: rank line reads "Rank #N of M in FMZ X within 30 min".
- [x] Network tab: no remaining requests with `radius_km` in URL.
- [x] Rapid weight slider + drive-time pill change: only one fetch fires (shared debounceRef, latest wins).
- [x] FMZ change while drive-time filter is active: refetches with both filters; map stays at the candidates-bbox view (existing useEffect handles map positioning).

### Merge to main

- [x] Branch sanity check: all verification cases pass, build is clean
- [x] Merge `phase-3/03-frontend-drive-time` to `main`

**Run the integration smoke test from Part 7 at this point**, before starting trail-graph work. Drive-time replaces radius cleanly; the trail graph and walk-time work is structurally separate. A midpoint smoke test confirms the API contract change is solid before layering more on top.

---

## Part 4 — Trail graph build (3-4 hours)

Build a routing graph from the existing OSM `trails` table, filtered to hiking-relevant classes. The graph lives in process memory, built once at API startup, used by Part 5's walk-time endpoint.

This is structurally similar to Phase 2's `build_connectivity.py` for water topology — but for trails, and in memory rather than materialized in the DB.

### Pre-Phase-3 trail data evaluation (carried forward from design discussion)

A manual comparison between OSM and OTN (Ontario Trail Network) data was run during Phase 3 design across 10 candidates ranked 1-700 within 30 km of home. Datasets were nearly identical with only minor branching differences in either direction — neither strictly dominant. **Decision locked: OSM-only for Phase 3**, with re-evaluation in Phase 6 if Phase 4 trips reveal routing failures attributable to missing trail data, or if Phase 6 expansion targets FMZs with poorer OSM coverage.

### Locked design decisions

- **No new DB tables.** Graph lives in process memory. Rebuilt on each app restart.
- **Trail filter**: `highway IN ('path', 'track')` only. Exclude `footway` and `cycleway` from the routing graph. The trails table contains ~580k footways out of ~681k total — sidewalks dominate. Sidewalks are accessibility signal (Phase 2 A-scoring) but not where you walk to fish.
- **Graph library**: NetworkX undirected graph. Same as Phase 2 connectivity.
- **Node identity**: trail LineString endpoints. Two trails sharing an endpoint within 5m (same `SNAP_TOLERANCE_M` as Phase 2 connectivity) are the same node.
- **Edge identity**: one edge per trail segment between nodes. Length is geometric length in meters. Trail class preserved on the edge.
- **Build at app startup**, not first request. Predictable startup cost; first user request is fast.
- **A-scoring formula UNCHANGED.** The accessibility score still uses `min(trail_dist, parking_dist) / 2000` from Phase 2 — no re-weighting for trail class, no formula change. Locked previous to Phase 3, revisit in Phase 6.

### Build the trail graph service

**Plan Mode prompt**: "Create `backend/services/trail_graph.py`. Module-level state: `_graph: nx.Graph | None`. Functions:

1. `build_trail_graph(engine) -> None`: queries trails table filtered to `highway IN ('path', 'track')`, builds NetworkX undirected graph in memory. Stores reference at module level. Algorithm:
   - For each trail LineString, walk its vertices in order
   - For each vertex, find or create a node ID. Use a spatial-hash on the (x, y) coordinate at 5m precision so vertices within 5m of each other become the same node.
   - Connect successive vertices in the same LineString with an edge. Edge attributes: `length` (geometric distance in meters between the two vertices), `class` (the highway value: 'path' or 'track').
   - Multiple LineStrings sharing a vertex (within 5m) end up sharing a node — this is what makes the graph connected.

2. `get_trail_graph() -> nx.Graph`: returns the built graph. Raises RuntimeError if not yet built.

3. `find_nearest_trail_node(point_3161: Point) -> int | None`: given a Point in EPSG:3161, returns the node ID of the nearest graph node, or None if no node within a sane distance (e.g., 5km).

In `backend/api/main.py`, register `build_trail_graph(engine)` as a FastAPI lifespan startup event so the graph is ready before the first request.

Diagnostic prints during build:

```
Building trail graph...
  trails table:                    {n:,} rows
  filtered (path + track):         {n:,} rows
  building graph...                ({s:.0f}s)
  nodes:                           {n:,}
  edges:                           {m:,}
  components:                      {c:,}
  largest component:               {n:,} nodes / {m:,} edges
  isolated nodes:                  {n:,}
```

Memory cost expectation: ~80k edges, NetworkX overhead in the 150-300MB range. Acceptable for the personal-use process. Document in the docstring.

Show me the build algorithm and the spatial-hash approach before generating."

Verify in the plan:
- [x] Trail filter is exactly `highway IN ('path', 'track')`
- [x] Spatial-hash node deduplication is explicit (not naive O(n²) deduplication)
- [x] Edge weight is the geometric `ST_Length` of the segment, not Euclidean
- [x] Lifespan startup registration in `main.py` is correct (FastAPI 0.93+ lifespan handler pattern)
- [x] `find_nearest_trail_node` uses NetworkX spatial query patterns, not a brute scan

### Verify the graph build

After implementation, restart uvicorn and watch the startup logs:

- [x] Startup completes in under 60s
- [x] Memory usage of the uvicorn process stays under 600MB total (check Task Manager / `top`)
- [x] Connected components count is reported. Many small components (>1000) means trail data is fragmented. A few large ones (10-100) means good connectivity.
- [x] Largest component contains a meaningful fraction (>50%) of all nodes — otherwise the graph is too disconnected to route on
- [x] Isolated nodes count is small (<5%)

Spot check via Python REPL:

```bash
cd backend && python -c "
import sys; sys.path.insert(0, '.')
from sqlalchemy import create_engine
from config import DATABASE_URL
from services.trail_graph import build_trail_graph, get_trail_graph
import networkx as nx

engine = create_engine(DATABASE_URL)
build_trail_graph(engine)
G = get_trail_graph()
print(f'Nodes: {G.number_of_nodes():,}, Edges: {G.number_of_edges():,}')
print(f'Components: {nx.number_connected_components(G):,}')
print(f'Largest: {len(max(nx.connected_components(G), key=len)):,}')
"
```

- [x] Pick a known trail (e.g., a specific trail near Petticoat Creek you've walked) and confirm both endpoints are in the same component via `nx.has_path(G, node_a, node_b)` after looking up node IDs

### Merge to main

- [x] Branch sanity check: graph builds in <60s, memory acceptable, components look sane, spot-check passes
- [x] Merge `phase-3/04-trail-graph` to `main`

---

## Part 5 — Walk-time routing endpoint (2-3 hours)

New endpoint that computes walk-time from the parking nearest to a candidate to the candidate itself, via Dijkstra on the trail graph from Part 4. Called by the frontend lazily when the user opens a candidate's detail card.

### Endpoint design

- **Endpoint shape**: `GET /candidates/{candidate_id}/walk-time`
- **No user-location parameter**. Walk-time is independent of where the user lives — it's parking-to-candidate, the same regardless of which direction the user drove from. Reusing the existing `a_dist_to_parking_m` from Phase 2 means we already know which parking is closest.
- **Walk speeds (initial values, calibrate in Phase 6 with trip data):**
  - `path` = 4 km/h = 66.7 m/min
  - `track` = 5 km/h = 83.3 m/min
- **Failure modes** (each returns walk_time_min=null with a descriptive `error` field; not 5xx):
  - Candidate doesn't exist → 404
  - No parking polygon within reasonable distance (>10 km) → "no parking within reasonable distance"
  - Parking found but no path on graph → "no trail route from parking to candidate"

### Build the endpoint

**Plan Mode prompt**: "Add `GET /candidates/{candidate_id}/walk-time` to `backend/api/main.py`. Algorithm:

1. Query the candidate by ID. If not found, raise 404.
2. Query the candidate's nearest parking polygon using existing `a_dist_to_parking_m` to identify the parking record. Get parking geometry centroid (Point in EPSG:3161).
3. If parking distance > 10000m, return walk_time_min=null with error 'No parking within reasonable distance'.
4. Find the nearest trail node to the parking centroid via `find_nearest_trail_node` from `services.trail_graph`. If no node within 5km, return walk_time_min=null with error 'No trail near parking'.
5. Find the nearest trail node to the candidate centroid (use ST_Centroid for polygons; the linestring midpoint for reach_segments). Same nearest-node pattern.
6. Run `nx.shortest_path_length(G, source, target, weight=lambda u,v,d: d['length'] / SPEEDS[d['class']])`. The weight function ensures Dijkstra minimizes time, not distance. SPEEDS is a constant `{'path': 66.7, 'track': 83.3}` (m/min).
7. If no path exists, return walk_time_min=null with error 'No trail route from parking to candidate'.
8. Otherwise, also compute total walk distance and the dominant trail class along the path (for display: 'path', 'track', or 'mixed' if both).
9. Return:

```python
class WalkTimeResponse(BaseModel):
    walk_time_min: float | None
    walk_distance_m: float | None
    primary_trail_class: str | None
    parking_lat: float
    parking_lon: float
    error: str | None
```

`parking_lat` and `parking_lon` are the parking centroid in EPSG:4326 (transformed from 3161). Useful for the frontend's 'Get directions' button if you implement it.

Show me the algorithm and the SQL queries before generating."

Verify in the plan:
- [ ] Dijkstra weight function divides length by class speed (not just `length`)
- [ ] No-path case is handled via try/except on `nx.NetworkXNoPath` or via `nx.has_path` check first
- [ ] Failure modes return 200 with `walk_time_min=null` and descriptive `error` (not 5xx)
- [ ] 404 only for missing candidate, not for missing path

### Verification

```bash
# Pick a candidate ID from the panel that you know has accessible parking
GET /candidates/{id}/walk-time
# Expect: walk_time_min in 5-30 min, distance reasonable, primary_trail_class set
```

- [ ] Pick 5 candidates from the panel that should have accessible parking — walk-time loads, values are sensible
- [ ] Pick 2 candidates in remote areas — at least one should return walk_time_min=null with descriptive error
- [ ] Invalid candidate ID returns 404
- [ ] Median response time under 200ms (Dijkstra on a graph this size is fast)
- [ ] No memory leaks: hit the endpoint 50+ times in succession, watch the uvicorn process memory — should stay flat (graph is reused, not rebuilt per request)

### Merge to main

- [ ] Branch sanity check: endpoint works for the test cases, response time is acceptable, no memory growth
- [ ] Merge `phase-3/05-walk-time-endpoint` to `main`

---

## Part 6 — Frontend: walk-time and total-time display (2-3 hours)

When the user clicks a candidate's detail card, fetch and display walk-time. Add total-time framing (drive + walk) to the panel.

### Plan the detail card update

**Plan Mode prompt**: "Update `frontend/components/panel/CandidateDetail.tsx`:

1. Add a `useEffect` triggered by `selectedFeature.properties.id` that fetches `/candidates/{id}/walk-time` and stores the response in local component state.
2. Three terminal states for walk-time display:
   - Loading: 'Computing walk time...' (small italic text)
   - Success: 'Walk: 23 min via path' (or 'via track', 'via mixed trails')
   - Failure: graceful display of the error field (e.g., 'No trail route from parking')
3. When the parent's `driveTimeMin` is non-null, also display the drive context: 'Drive: up to {driveTimeMin} min from your location' below the walk-time line.
4. The total-time framing is implicit — user reads 'Drive: up to 30 min, Walk: 23 min' and combines mentally. Don't auto-compute a 'Total' field — the drive value is an upper bound (the isochrone cap), not a per-candidate exact value.

In `frontend/lib/types.ts`, add:

```ts
export interface WalkTimeData {
  walk_time_min: number | null
  walk_distance_m: number | null
  primary_trail_class: string | null
  parking_lat: number
  parking_lon: number
  error: string | null
}
```

Optional, only if quick: a 'Get directions to parking' link that opens an external map app with the parking lat/lon as destination. Format: `https://www.google.com/maps/dir/?api=1&destination={parking_lat},{parking_lon}` (cross-platform; works on iOS, Android, desktop browsers). Skip if it adds significant complexity.

Show me the component diff and the new state shape before generating."

Verify in the plan:
- [ ] The fetch is triggered only on selection change, not on every render
- [ ] Cancellation: if the user clicks a different candidate while a previous fetch is still in flight, the previous fetch's response is ignored (use a `current` ref or AbortController)
- [ ] Loading state has reserved space — no layout shift when walk-time loads in
- [ ] Walk-time display includes the trail class qualifier ('via path', 'via track', 'via mixed trails') — sets honest expectations about the kind of walk
- [ ] Drive-time line only appears when `driveTimeMin` is non-null

### Verification

- [ ] `npm run build` passes
- [ ] Click an accessible candidate (one with reasonable parking nearby): walk-time loads within 1-2 seconds, displays in detail card
- [ ] Click a remote candidate: 'No trail route from parking' (or similar error) displays gracefully — no broken layout, no error toast
- [ ] Trail class qualifier appears: 'via path', 'via track', or 'via mixed trails'
- [ ] When drive-time filter is active: 'Drive: up to 30 min from your location' appears alongside the walk-time
- [ ] When drive-time filter is not active: drive line is hidden
- [ ] Click candidate A, then quickly click candidate B before A's walk-time finishes: B's walk-time displays (not A's response misattributed to B)
- [ ] Network tab: walk-time fetch only fires on candidate click, never on list render or on weight slider changes

### Merge to main

- [ ] Branch sanity check: all verification cases pass, build is clean, no console errors
- [ ] Merge `phase-3/06-frontend-walk-time` to `main`

---

## Part 7 — Integration smoke test (45-60 min)

Same shape as Phase 2's Part 9. Walk every UI path with intent before tagging Phase 3 complete. This is the forcing function that catches cross-layer bugs.

### Setup

- [ ] Stop everything (Docker stays up; restart uvicorn and `npm run dev`)
- [ ] Cold-load `http://localhost:3000`
- [ ] Watch backend logs for the trail graph build line — should complete in under 60s

### Manual smoke test

Walk through every checkbox. Don't rush — bugs you skip here cost more later.

- [ ] App loads, panel shows ranked candidates, both regions, no filter
- [ ] Console clean, no errors in browser or server
- [ ] FMZ 16 only: pill works, candidates filter, fmz_total updates correctly
- [ ] FMZ 17 only: same
- [ ] All weight sliders at 0.01 (minimum from Phase 2): composite roughly uniform, ranks shuffle
- [ ] All weight sliders at default 0.25: rankings match prior baseline
- [ ] Heavy w_h: top candidates are most-hidden across the dataset
- [ ] Heavy w_f: top candidates have `f_confidence='strong'`
- [ ] Location filter — 'Use my current location': geolocation works, lat/lon shows with accuracy tag
- [ ] Drive-time 20 min: candidates within 20-min driving polygon (small set)
- [ ] Drive-time 30 min: superset of 20 min
- [ ] Drive-time 45 min: superset of 30 min
- [ ] Drive-time 60 min: superset of 45 min
- [ ] Active-pill click is no-op (e.g., click '30 min' twice — no fetch fires the second time)
- [ ] Drive-time + FMZ: additive, both filters apply, `total_count` reflects both
- [ ] Manual location entry: type lat/lon, click Set, valid range → State 3
- [ ] Manual location entry: out-of-range values → inline validation error
- [ ] Nominatim address search: type 'Scarborough, ON' → returns ~43.77, -79.26 → State 3
- [ ] Nominatim no-results case: type 'gibberish that nominatim wont find' → 'No results found' error
- [ ] Geolocation denied (use browser dev tools to deny): error displays, manual entry still available
- [ ] Click candidate in panel: detail card opens with full scores
- [ ] Walk-time fetches and displays within 1-2 seconds
- [ ] Walk-time matches a candidate you have intuition about (pick a known spot)
- [ ] Walk-time 'no route' case displays gracefully (pick a remote candidate)
- [ ] Trail class qualifier in walk-time line ('via path', 'via track', or 'via mixed trails')
- [ ] When drive-time filter active: 'Drive: up to N min from your location' shown
- [ ] Detail card rank line: 'Rank #N of M in FMZ X within Y min' (drive-time-aware text)
- [ ] Click 'Clear filter': map zooms back to FMZ/COMBINED, candidates refresh
- [ ] FMZ change while drive-time filter active: refetches with both filters, no crash

### Performance smoke

- [ ] Cold-start API in under 60s (graph build dominates)
- [ ] `/candidates` response in under 2s for filtered queries
- [ ] `/candidates/{id}/walk-time` response in under 500ms
- [ ] Frontend feels responsive; no UI freezes during weight slider drag or drive-time pill clicks
- [ ] After 30 minutes of use, uvicorn process memory hasn't grown (graph stays in memory but doesn't leak)

### Failure-mode smoke

- [ ] Set `MAPBOX_API_KEY` to invalid temporarily, restart uvicorn:
  - `/candidates?near_lat=43.77&near_lon=-79.26&drive_time_min=30` returns 503 with descriptive error
  - Frontend handles 503 gracefully (error banner, last result preserved or cleared depending on existing pattern)
  - Restore key and verify recovery
- [ ] Stop the trail graph service somehow (e.g., temporarily break the lifespan import): `/candidates/{id}/walk-time` returns 5xx with descriptive error. Restore.

### Definition of done

- Every checkbox passes
- Any 'almost' or 'weird' finding gets a CLAUDE.md note (known issue) before tagging the phase complete
- If something fails: fix it on a new branch off main, re-run the smoke test, then proceed

---

## Part 8 — Reflection and commit (45-60 min)

Same prompts as Phase 2, plus Phase-3-specific ones.

### Document

- [ ] Update `README.md` with the current state — drive-time filter, walk-time on selection, OSM-only trail data
- [ ] Update `CLAUDE.md` with anything that changed about the architecture (especially: external service dependency, in-memory trail graph at startup, OSM-only trail decision and rationale)
- [ ] Create `docs/phase_3_reflection.md` answering:
  - What worked smoothly?
  - What took longer than expected, and why?
  - **Did the Mapbox 60-min cap matter in practice? Did you find yourself wishing for 90 or 120 min?**
  - **Was the trail graph build cost acceptable? Did the in-memory rebuild on each restart cause friction?**
  - **Did the walk-time numbers feel right? Where did they feel off, and is the issue speed model, terrain, or graph topology?**
  - **How did the OSM-only trail decision land? Any candidates where you wished for OTN coverage?**
  - **Was lazy walk-time fetch (on selection, not in the list) the right call, or did you wish you saw walk-times in the list?**
  - **What did Phase 4 trip data (if you've done a trip by reflection time) reveal about scoring vs reality?**
  - **What would Phase 6 calibration need from walk-time data — a per-class speed table tuned to actual trip pace, or something more detailed?**
  - What architectural decisions are you uncertain about?
  - What did you learn about Claude Code's working pattern on a phase with external dependencies?
  - What's one thing you'd do differently starting Phase 3 over?

### Commit and tag

- [ ] `git add -A && git commit -m "Phase 3: routing layer with drive-time and walk-time"`
- [ ] Push to GitHub
- [ ] Tag: `git tag phase-3-complete && git push --tags`

---

## Done criteria

You're done with Phase 3 when:
- [ ] App loads, drive-time filter works for all 4 presets (20/30/45/60 min)
- [ ] Drive-time filter replaces the old radius filter cleanly — no `radius_km` references in code, UI, or URL
- [ ] Walk-time fetch on candidate selection works for accessible candidates and degrades gracefully for remote ones
- [ ] Trail class qualifier shows in walk-time display ('via path', 'via track', 'via mixed trails')
- [ ] When drive-time filter is active, the panel shows both drive context and walk time
- [ ] Mapbox failures return 503 with descriptive errors; frontend handles them gracefully
- [ ] Trail graph builds at startup in under 60s, memory stays under 600MB
- [ ] All workstream branches are merged to main
- [ ] Integration smoke test passes
- [ ] Repo is committed, tagged, documented

You do **not** need to:
- Have walking-time accuracy beyond `length / class_speed` (no elevation, no season, no off-trail bushwhack — Phase 6 territory after trip calibration)
- Have real-time traffic in drive-time (Mapbox typical-traffic is fine)
- Have multi-stop trip planning ("hit three spots in one drive" — out of scope)
- Have visualized isochrone polygon or routes on the map (nice-to-have, optional)
- Have per-candidate exact drive time (only the filter polygon; click 'Get directions' opens external Maps if implemented)
- Have walk-speed calibration data ingestion (collected during Phase 4, applied Phase 6)
- Have a Mapbox response cache (skip in v1; add if dev iteration is slow)
- Have changed the A-scoring formula (locked: stays as `min(trail, parking)` linear decay, revisit Phase 6)
- Have switched to OTN trails or combined OSM+OTN (locked: OSM-only, revisit Phase 6)

---

## If you get stuck

**Mapbox returns empty isochrone for valid coordinates**: Verify the lat/lon order in `ST_MakePoint(lon, lat)` — Mapbox's URL format is `{lon},{lat}` which is the *opposite* of how PostGIS reads coordinates in WKT. If the polygon is in the wrong place (off Africa, in Lake Ontario), it's a coordinate-order bug. Check both the Mapbox call and the SQL.

**Mapbox rate-limits during dev iteration**: 300 req/min is generous but achievable if you're hammering the panel. Add an in-memory cache keyed on `(round(lat, 4), round(lon, 4), drive_time_min)` — same isochrone for the same approximate location reuses the response. ~11m precision, fine since geolocation accuracy is much coarser.

**Trail graph build takes >2 minutes**: Check that the trail filter actually applied. `SELECT COUNT(*) FROM trails WHERE highway IN ('path', 'track');` should be ~80k. If it's higher, the WHERE clause is wrong. If the count is right and build is still slow, profile the spatial-hash deduplication step — the naive O(n²) approach explodes at this scale.

**Trail graph has too many components (>5000)**: Snap tolerance is too tight. Bump to 7m or 10m and rebuild. Conversely, if the graph is overly connected (paths that shouldn't share endpoints get fused), drop to 3m. The right number connects all segments of the same official trail but doesn't connect adjacent unrelated paths.

**Walk-time always returns 'no trail route from parking'**: Either parking-to-trail-node lookup is broken (check `find_nearest_trail_node` for the parking centroid in QGIS — does it pick a sensible node?), or the candidate-to-trail-node lookup is broken, or the graph is disconnected between them. Use `nx.has_path(G, parking_node, candidate_node)` to verify reachability before debugging Dijkstra.

**Walk-time values feel way off (too fast or too slow)**: Speeds are starting guesses (path=4 km/h, track=5 km/h). Calibrate after a real trip — note your pace on the trail, compare to the prediction, adjust SPEEDS in `services.trail_graph`. Phase 4 trip data feeds Phase 6 calibration; this is expected.

**`drive_time_min=99` returns 422 instead of 503**: That's correct — FastAPI's `Query(le=60)` validates before the handler runs, so it's a 422 (validation error), not 503 (service error). The 503 is only for Mapbox-side failures within the valid input range.

**Frontend build fails after the rename**: TypeScript catches stale `RadiusKm` references in places you forgot. `grep -r "RadiusKm\|radius_km\|radiusKm" frontend/` to find them, fix them all in one pass.

**Mapbox API key is in a committed file**: Treat it as compromised. Mapbox dashboard → rotate the key. Update `.env`. Verify the new `.env` is gitignored. The old key in git history is still present, but rotated keys make it harmless.

**You feel mid-phase scope creep tempting you (e.g., 'while we're here, let's add walk-time to the list')**: Run `/scope-check`. Phase 3's deliverable is at the top of this file. The 'do not need to' list is in the Done Criteria. Read both, re-narrow.

**Integration tests pass but walk-time feels wrong on actual candidates you know**: That's not a Phase 3 bug, that's the speed model needing calibration. Capture the discrepancy in Phase 4 trip notes — note prediction, note actual, note trail class. Phase 6 uses this to retune speeds.

---

## After Phase 3

Bring back to the next conversation:
- Your `phase_3_reflection.md` notes
- Screenshots of the working app: drive-time filter at each preset, candidate detail with walk-time displayed, candidate detail with 'no trail route' graceful failure
- Top 5 candidates within 30 min and 60 min of home with their walk-times — note which ones surprised you (positively or negatively)
- Any candidates where the walk-time felt wildly off compared to your sense of the location
- Architectural decisions you're uncertain about
- Whether the drive-time + walk-time framing is enough for trip planning, or whether something else is missing (off-trail bushwhack distance, elevation gain, anything else)

Then we plan Phase 4: the first ground-truth trip, with predictions captured before the trip and outcomes captured after. Phase 4 is the first time the tool's output meets reality, and the trip data is the input to Phase 5 (multi-agent reasoning) and Phase 6 (weight calibration).
