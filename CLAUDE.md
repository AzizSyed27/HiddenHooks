# HiddenHooks

A geospatial tool for finding under-fished water bodies in Ontario.
Combines hydrology data, fish survey data, terrain, and accessibility
into a scored ranking. Personal/portfolio project.

## Tech stack
- Python 3.11 backend (FastAPI, GeoPandas, OSMnx 2.x, PostGIS via SQLAlchemy + psycopg2)
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

## Current phase: Phase 1 — complete
Test region: ~20 km radius around Rouge National Urban Park (Scarborough, ON).
Scoring signal: distance to nearest road (`dist_to_road_meters`).
Pipeline runs end-to-end: ingest → score → API → map view.

## Key files built in Phase 1
| File | Purpose |
|---|---|
| `backend/config.py` | All paths, `DATABASE_URL`, `TEST_BBOX`, `ROADS_CACHE_PATH` |
| `backend/ingest/ohn_waterbody.py` | OHN waterbody → `candidates` (type: polygon) |
| `backend/ingest/ohn_watercourse.py` | OHN watercourse → `candidates` (type: reach_full) |
| `backend/ingest/roads.py` | OSM road network → `roads`; GraphML cache in `cache/` |
| `backend/scoring/dist_to_road.py` | PostGIS KNN UPDATE on `dist_to_road_meters` |
| `backend/api/main.py` | `GET /candidates` → GeoJSON FeatureCollection |
| `frontend/lib/types.ts` | Shared TS types: `CandidateProperties`, `CandidateFeature`, `CandidateCollection` |
| `frontend/app/page.tsx` | Map view orchestrator: state, fetch, `mapRef`, `handleSelect`, overlays |
| `frontend/components/map/MapView.tsx` | react-map-gl map + 4 layers (poly-fill, poly-outline, reach-lines, highlight) |
| `frontend/components/panel/CandidatePanel.tsx` | Framer Motion slide panel, ranked list, detail card |

## Established conventions and gotchas

**Database / ingest**
- Geometry stored in EPSG:3161 (Ontario MNR Lambert, metric). Served to frontend as
  WGS84 via `ST_Transform(geom, 4326)` in the candidates SQL query.
- Candidates table uses `geometry(Geometry, 3161)` — generic type accepting both
  Polygon and LineString in one column.
- Ingest is UPSERT via partial unique indexes, NOT delete+insert. `parent_candidate_id`
  references `candidates.id` — DELETE+INSERT would either cascade-nuke Phase 2
  `reach_segment` rows or fail with FK violations.
- `candidates.dist_to_road_meters` is populated by the scoring script, not ingest.
  The scoring script takes ~8 min on the test region (PostGIS KNN on 2,888 candidates).

**API**
- `GET /candidates` returns all features; `rank` is a 1-indexed integer (1 = farthest
  from road = most hidden). `normalizedRank` is NOT in the API response — it is
  computed client-side in `page.tsx` after fetch.

**Frontend**
- `react-map-gl/mapbox` v8 event type is `MapMouseEvent` (from mapbox-gl), NOT
  `MapLayerMouseEvent`. The latter does not exist in this version.
- `SheetTitle` from shadcn wraps Radix `Dialog.Title` and requires being inside a
  `<Sheet>` (Dialog) context. Do not use it outside the Sheet wrapper — use a plain
  `<h2>` with `className="font-heading font-medium text-foreground"` instead.
- The side panel is a `motion.div` (not a Sheet Dialog) to avoid modal behavior
  conflicting with Mapbox map interactions. `SheetHeader` (a plain div) is reused
  for consistent spacing.
- In React 19, `useRef<T>(null)` returns `RefObject<T | null>`. Prop types for refs
  should be `React.RefObject<T | null>`, not `React.RefObject<T>`.

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
- If you notice scope creep beyond Phase 1's deliverable, flag it.
- Decisions about what feels like a good fishing spot, what species
  matter, or how the UI should feel are mine to make. Give me options,
  don't decide for me.

## Repo policy
- Repo is private during development.
- Future state: portfolio-visible with a "look but don't reuse" license.
- Trip data (actual GPS coordinates of validated spots) is never
  committed. Trip logs go in a gitignored `private/` folder.