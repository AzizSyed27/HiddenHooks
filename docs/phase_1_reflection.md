# Phase 1 Reflection

Test region: ~20 km radius around Rouge National Urban Park, Scarborough, ON.
Scoring signal: distance to nearest road.
Date completed: 2026-05-03.

---

## What worked smoothly?

The PostGIS spatial pipeline was the strongest part of the phase. The KNN operator
(`<->`) on a GiST index, `ST_Distance` for exact measurement, and `ST_Transform` for
the WGS84 conversion to the frontend all composed cleanly without any correctness
issues. Writing raw SQL for the scoring and API queries (rather than fighting an ORM)
was the right call — the queries were readable and the intent was obvious.

The FastAPI + Pydantic API layer came together quickly. Defining the GeoJSON response
shape as Pydantic models caught the `area_m2` rename question early, before it became
a runtime mismatch.

The upsert pattern via partial unique indexes scaled to both ingest scripts without
modification and will carry cleanly into Phase 2. Once the FK-violation risk with
DELETE+INSERT was identified, the partial index solution was unambiguous and cost
nothing in complexity.

The Framer Motion panel and the Mapbox layer structure both worked on the first
attempt after the TypeScript errors were resolved. The four-layer setup
(poly-fill / poly-outline / reach-lines / highlight) is simple and complete.

---

## What took longer than expected, and why?

Scoring Performance: The `dist_to_road.py` script ran for 512 seconds on 2,888
candidates — roughly 8.5 minutes. The expectation going in was single-digit seconds.
The cause: `ST_Distance` between complex multi-vertex OHN geometries (some polygons
have hundreds of vertices) and OSM road linestrings is geometrically expensive, even
when the KNN index narrows the candidate roads to one. The index step is fast; the
exact-distance computation on complex shapes is not. This was left unresolved — a
known issue going into Phase 2.

I also had to revert the code to previous version becuase I missed the scroing step,
causing it to take the longest.

The OHN name field has rows where the value is the
string `"NaN"`, not a SQL NULL. Pandas reads these as float `nan` during GeoDataFrame
construction. The first normalization attempt used `str(v).strip() == ""` to catch
empty values, but `str(float('nan')) == "NaN"` — not an empty string — so the rows
slipped through. Required a second pass using `.where(gdf["name"].notna() & (gdf["name"].str.strip() != ""), other=None)`. One debugging round, but easy to miss.

Two errors only appeared at build time:
1. `MapLayerMouseEvent` does not exist in react-map-gl 8 — the correct type is
   `MapMouseEvent` re-exported from mapbox-gl.
2. React 19 changed `useRef<T>(null)` to return `RefObject<T | null>`, breaking prop
   types declared as `RefObject<T>`.

Neither was caught during authoring. Both are now documented in CLAUDE.md.

Everything else was pretty much a one shot with some plan editing.

---

## What surprised you about the data, the tooling, or the process?

The full Ontario Waterbody shapefile has ~1.4 million
features; Watercourse has ~2.7 million. The test bbox filtered that to ~2,888
candidates. The pyogrio bbox filter at the driver level was essential — loading even
a fraction of the province into memory first would have been a problem.

A significant number of waterbodies and reaches have `name =
"NaN"` (literal string) rather than a proper NULL. This appears to be an artifact of
whatever ETL process generated the shapefile — the source data had blank name fields
that got serialised as NaN floats somewhere. It means name filtering or display logic
has to be defensive about this string value, not just about SQL NULL.

The scoring script runtime at 512 seconds was genuinely surprising given that the
GiST index is present and the KNN operator is supposed to make nearest-neighbour
queries fast. The index does its job — it narrows the search space. The bottleneck is
the exact `ST_Distance` computation between complex polygons and linestrings, not the
index traversal. This distinction matters: optimising the index won't help; simplifying
the geometries before storage would.

---

## What architectural decisions are you uncertain about?

**Scoring performance strategy.** The current `dist_to_road.py` is correct but slow.
It takes 512 seconds to score which isn't great but I don't mind it.

**Generic geometry column.** `geometry(Geometry, 3161)` accepts any geometry type.
The flexibility was the right call for Phase 1, but it means a future bug could write
a Point geometry into the candidates table with no DB-level rejection. Adding a
`CHECK (ST_GeometryType(geom) IN ('ST_Polygon', 'ST_MultiPolygon', 'ST_LineString',
'ST_MultiLineString'))` constraint would close that gap.

**All candidates in one API response.** 2,888 features is fine. The full Ontario
dataset is in the millions. But at the same time we don't plan on doing all of
Ontario.

---

## Looking at top-ranked candidates: do they look real?

The top-ranked candidate had `dist_to_road_meters = 8,743 m` — nearly 9 km from the
nearest road. In the Rouge Park / Scarborough test region, that distance places a
feature deep in the Greenbelt or in rural agricultural land east of the park boundary.
This cadidate is literally in the ocean, so it's not a plausible spot.

Some honest assessment:

Features far from roads are genuinely harder
to reach and less likely to be fished frequently. The scoring isn't wrong.

Remoteness from roads
is not the same as remoteness from people. A feature 8 km from a road but adjacent to
a popular trail network, or on private farmland with no legal access, would score at
the top but be useless. The scoring also says nothing about whether the water holds
fish worth catching — a remote roadside ditch scores the same as a remote glacial lake
if both are equidistant from roads.

Rouge River tributaries running
through Scarborough neighbourhoods score near the bottom because they're within metres
of roads. Some of those reaches might be genuinely overlooked — urban water bodies
that most anglers dismiss — which is exactly the kind of thing this tool should
surface. The current signal ranks them last.

Several candidates touch or cross roads
in the urban part of the test region. That's correct behaviour for Scarborough.

The Phase 1 map is a proof of concept, not a fishing recommendation. The scoring will
only become meaningful once accessibility (trail proximity, land ownership), water
quality, and species data are incorporated.

---

## What did you learn about Claude Code's working pattern on this project?

The iterative plan-refine-approve cycle prevented
several mistakes from reaching code: the DELETE+INSERT FK violation was caught in
planning, the highlight filter expression was verified before writing, and the five
gaps you flagged in the map view plan (mapRef ownership, fitBounds on non-points,
loading states, memoization, filter syntax) would all have been wrong or missing in a
first draft. The overhead is real — more turns, more back-and-forth — but the
resulting code had fewer debugging rounds. I also conferred to claude.ai chats to look
at plans from Claude Code and catch any holes or contraints, creating close to flawless
plans.

Both frontend type errors
(MapMouseEvent rename, RefObject type change) only surfaced at `next build`. Authoring
the components feels complete before that step; it isn't. Running a build after every
component should be a default, not an afterthought.

This session ran long enough to require compaction. The quality of the continuation
depended entirely on what had been documented — in CLAUDE.md, in code comments, in
commit messages. Undocumented decisions become invisible across sessions.

**The "show SQL / show plan before writing" preference paid off most on the scoring
query.** The scoring SQL was reviewed and approved before the script was written. When
the 512-second runtime appeared, we had a shared understanding of what the query was
doing and why it was slow — no confusion about intent. On the frontend, the "show
component structure first" request caught the mapRef and fitBounds design gaps before
any code existed.



---

## What's one thing you'd do differently starting Phase 1 over?

I would appraoch the whole project with more peace of mind. Also I think I would have added
more features other then distance from road becuase it would'nt be too hard and we would 
get cadidates right away.

What Claude Code says:

Add a geometry simplification step during ingest.

Before inserting OHN geometries into the candidates table, run
`ST_SimplifyPreserveTopology(geom, 1.0)` — a 1-metre tolerance in EPSG:3161 removes
sub-metre vertex noise from the OHN data without meaningfully changing polygon or
linestring shapes. The result would be geometries that are visually identical on any
map but have a fraction of the vertex count. The scoring script that took 512 seconds
would likely run in under 30.

This change is cheap at ingest time (milliseconds per feature) and saves time on every
subsequent spatial operation — not just scoring, but any future intersection or
proximity query. The only cost is that the stored geometry is approximate, not exact.
For a scoring tool operating at the scale of fishing spots, 1-metre approximation is
well within acceptable error.

Everything else — the schema, the upsert pattern, the API design, the frontend
architecture — held up well enough that Phase 2 can build on it without restructuring.
