# HiddenHooks — Phase 1 Checklist (Revised)
 
**Goal**: Get a janky version of the full pipeline working end-to-end, on a tiny test region, with one trivial scoring feature. Prove the pipes work. Nothing more.
 
**Deliverable**: A web page that displays both waterbody polygons and watercourse linestrings within ~20km of your home, ranked by distance to nearest road, on a Mapbox map with a custom muted basemap. Click any feature, see its rank and metadata in a side panel.
 
**Total time**: 3-4 weekends alongside other commitments.
 
**Working partner**: Claude Code. Discipline matters more than speed.
 
**Mindset**: This isn't supposed to be useful. It's supposed to prove your stack works. Resist scope creep aggressively.
 
---
 
## Part 0 — Working with Claude Code (read first, do not skip)
 
The principles in this section matter more than any technical content below. Phase 1 is where you set the pattern for how you and Claude Code work together for the rest of the project.
 
### Set up your CLAUDE.md before writing any code
 
Create `CLAUDE.md` in the project root with this content as a starting point:
 
```markdown
# HiddenHooks
 
A geospatial tool for finding under-fished water bodies in Ontario.
Combines hydrology data, fish survey data, terrain, and accessibility
into a scored ranking. Personal/portfolio project.
 
## Tech stack
- Python 3.11+ backend (FastAPI, GeoPandas, PostGIS via SQLAlchemy)
- PostgreSQL 16 + PostGIS 3.4 in Docker
- Next.js 14+ with TypeScript and React
- Mapbox GL JS for map rendering with a custom muted basemap style
- shadcn/ui for component primitives
- Framer Motion for transitions
- Anthropic API (Claude) for the multi-agent reasoning layer (later phases)
 
## Current phase: Phase 1 — Vertical slice
Goal: prove end-to-end pipeline works on a tiny test region.
Test region: ~20km radius around Rouge National Urban Park (Scarborough, ON).
Single scoring feature: distance to nearest road.
 
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
```
 
- [x] Save the above to `CLAUDE.md` in your project root before any other work
- [x] Edit any sections that don't reflect your actual preferences
### Slash commands worth setting up
 
In `.claude/commands/`, create these as markdown files. They're saved prompts you can fire repeatedly:
 
- [x] `/sanity-check` — Connect to the database, report row counts, geometry validity, CRS for each layer, and any recent schema changes.
- [x] `/explain-query` — Given a SQL or PostGIS query, walk through it step by step explaining what each clause does and why.
- [x] `/scope-check` — Review what we're currently building against Phase 1's stated deliverable. Flag any scope creep.
- [x] `/why-this-choice` — Given a recent code or architectural decision, explain why it was chosen over the alternatives.
You won't use all of these constantly, but having them ready saves typing the same prompt repeatedly.
 
### Behavioral patterns to use throughout Phase 1
 
**Plan Mode for everything load-bearing.** Schema design, geospatial queries, API contracts. Read the plan, push back, then approve.
 
**The "you might be wrong" prompt.** When Claude Code generates a confident-looking solution, follow up with: "What's the case that this approach is wrong? What would change if data volume were 100x larger? What edge cases haven't you considered?"
 
**One conversation per phase, not per session.** Use `/compact` when context bloats. Restarting fresh each session means re-explaining your stack and losing architectural memory.
 
**Don't accept code without explanation for load-bearing logic.** Boilerplate is fine to skim. Schema, geospatial queries, and API contracts need you to be able to explain them line by line.
 
**No MCP servers in Phase 1.** You've hit token bloat from MCP overhead before. Add them later if needed; they're not needed now.
 
---
 
## Part 1 — Environment setup (1-2 hours)
 
You're staying on Windows native (your call, and reasonable). Use conda for the geospatial stack to avoid GDAL pain.
 
### Install Miniconda
 
- [x] Download Miniconda for Windows from https://docs.conda.io/projects/miniconda/
- [x] Install with default options
- [x] Open a fresh terminal (Windows Terminal recommended, not classic cmd)
- [x] Confirm: `conda --version` returns a version
### Install Node.js
 
- [x] Download Node LTS from https://nodejs.org/ (Windows installer)
- [x] Install with default options
- [x] Confirm: `node --version` and `npm --version` both return values
### Install Docker Desktop
 
- [x] Download Docker Desktop for Windows from https://www.docker.com/products/docker-desktop/
- [x] Install, then launch
- [x] Confirm: `docker --version` works in your terminal
- [ ] In Docker Desktop settings, ensure WSL2 backend is enabled (it's the default in current versions; this works fine even if you don't otherwise use WSL)
### Install VS Code (if not already)
 
- [x] You already use VS Code. Make sure these extensions are installed:
  - Python (Microsoft)
  - Pylance
  - PostgreSQL (Chris Kolkman or similar — for browsing the DB without leaving the editor)
  - ESLint
  - Tailwind CSS IntelliSense
  - Prettier
### Create the project structure
 
- [x] Pick a project location: `C:\Projects\hiddenhooks\` (or wherever fits your workflow)
- [x] Inside, create:
  ```
  hiddenhooks/
    backend/          # FastAPI + Python pipeline
    frontend/         # Next.js + React + TypeScript
    data/             # Local data files (gitignored)
    docker/           # Docker compose for Postgres
    docs/             # Design notes, phase reflections
    private/          # Trip logs, sensitive coords (gitignored)
    .gitignore
    README.md
    CLAUDE.md
  ```
- [x] Initialize git: `git init`
- [x] Add `.gitignore` excluding: `data/`, `private/`, `node_modules/`, `__pycache__/`, `.venv/`, `.conda/`, `.env`, `.env.local`, `*.pyc`, `.next/`
- [x] Optional but recommended: create a private GitHub repo and push, so you have backup
### Set up the conda environment
 
- [x] Open terminal in the project root
- [x] Run:
  ```
  conda create -n hiddenhooks python=3.11
  conda activate hiddenhooks
  conda install -c conda-forge geopandas shapely rasterio sqlalchemy psycopg2 fastapi uvicorn pydantic
  pip install osmnx anthropic python-dotenv
  ```
- [x] Confirm import works: `python -c "import geopandas; print(geopandas.__version__)"`
- [x] Save dependencies: `pip freeze > backend/requirements.txt` (note: conda envs aren't perfectly captured by pip freeze, but it's close enough for v1)
- [x] **If GDAL fails**: this is the moment WSL2 might be necessary. If conda's binaries don't work on your Windows install, switch to WSL2 (`wsl --install` in PowerShell as admin) and redo this step in Linux. Don't fight Windows GDAL for more than an hour.
### Initialize Claude Code in the project
 
- [x] Open the project in VS Code
- [x] Open Claude Code in the integrated terminal
- [x] First prompt: "Read CLAUDE.md and confirm you understand the project, current phase, and working preferences. Don't do anything else yet."
- [x] Verify the response reflects your preferences before proceeding
---
 
## Part 2 — Database setup (1-2 hours)
 
### Stand up Postgres + PostGIS
 
- [x] **Plan Mode prompt to Claude Code**: "Design a docker-compose.yml in `docker/` for local Postgres 16 + PostGIS 3.4 development. Persistent volume for data. Default credentials hiddenhooks/hiddenhooks/hiddenhooks. Exposed on port 5432. Show me the file and explain each section before writing it."
- [x] Read the plan, push back on anything that looks off, approve
- [x] Run `docker compose up -d` from the docker directory
- [x] Confirm container is running: `docker ps`
- [x] Connect with psql via Docker: `docker exec -it <container_id> psql -U hiddenhooks`
- [x] Inside psql: `CREATE EXTENSION IF NOT EXISTS postgis;` then `SELECT PostGIS_Version();` output: 3.4 USE_GEOS=1 USE_PROJ=1 USE_STATS=1
- [x] Exit psql with `\q`
### Design the v1 schema
 
This is load-bearing. Interrogate Claude Code's proposal carefully.
 
**Plan Mode prompt**: "Design a PostGIS schema for v1 of HiddenHooks. Each row is a candidate water feature. We have two source datasets: OHN Waterbody (polygons — lakes/ponds/wide rivers) and OHN Watercourse (linestrings — streams/creeks/narrow rivers). Both go into the same `candidates` table with a `candidate_type` discriminator. The candidate_type enum should support: `polygon` (waterbody), `reach_full` (entire watercourse linestring, what we'll have in Phase 1), and `reach_segment` (a segmented portion of a watercourse — Phase 2 territory but reserve the value now). Add a nullable `parent_candidate_id` column referencing back to candidates.id, so Phase 2 reach segments can link to the `reach_full` they were split from. Required columns: source OHN ID (preserve for re-joining to source), source dataset name (`waterbody` vs `watercourse`), candidate_type, parent_candidate_id (nullable), name (nullable), geometry with explicit SRID, surface area (nullable, for polygons), length (nullable, for linestrings), and a `dist_to_road_meters` column for our v1 feature. Include a spatial GIST index on geometry and a B-tree index on candidate_type. Use EPSG:3161 (Ontario MNR Lambert) for the geometry column. The geometry column should accept both POLYGON/MULTIPOLYGON and LINESTRING/MULTILINESTRING — use generic `geometry(Geometry, 3161)` rather than a specific subtype. Show me the SQL before generating files."
 
Verify in the proposed schema:
- [x] Geometry column has explicit SRID 3161 and accepts both polygons and linestrings
- [x] Spatial GIST index exists on the geometry column
- [x] `candidate_type` is an enum or check-constrained text with values `polygon`, `reach_full`, `reach_segment`
- [x] `parent_candidate_id` is nullable and self-references the table (foreign key to candidates.id)
- [x] `source_dataset` column exists and tracks `waterbody` vs `watercourse` provenance
- [x] OHN ID is preserved for traceability back to source data
- [x] Migrations live in `backend/db/migrations/` (or use a single SQL file for v1 — Alembic is overkill this early)
### Apply the schema
 
- [x] Save the schema to `backend/db/schema.sql`
- [x] Apply it via psql or a small Python script
- [x] Verify: list tables, check the spatial index exists (`\di` in psql), confirm column types
---
 
## Part 3 — Data ingestion (3-4 hours)
 
You have two OHN datasets to ingest: **Waterbody** (polygons — lakes, ponds, wide river sections) and **Watercourse** (linestrings — streams, creeks, narrow rivers). Both go into the same `candidates` table with different `candidate_type` values. Watercourse is essential — without it, the connectivity inference layer planned for Phase 2 has no stream network to traverse.
 
You'll write two near-identical ingestion scripts. The patterns are the same; the differences are which file is read and which `candidate_type`/`source_dataset` is written.
 
### Define the test bounding box
 
Pick a tight box for v1 — much smaller than your Phase 0 exploration area. Rouge Park area is ideal: enough water bodies to test, small enough to iterate fast.
 
- [x] Create `backend/config.py` with a `TEST_BBOX` constant covering Rouge National Urban Park (approx 43.78–43.85 N, -79.20 to -79.10 W — adjust to taste)
- [x] Comment why this bounding box was chosen
### Copy OHN data into the project
 
- [x] Copy your Phase 0 OHN Waterbody shapefiles to `data/ohn_waterbody/` in the project
- [x] Copy your OHN Watercourse shapefiles to `data/ohn_watercourse/`
- [x] Confirm all supporting files are present in each folder (`.shp`, `.shx`, `.dbf`, `.prj`)
### Write the Waterbody ingestion script
 
**Plan Mode prompt**: "Write a Python script `backend/ingest/ohn_waterbody.py` that reads the OHN Waterbody shapefile from `data/ohn_waterbody/`, filters to features intersecting our TEST_BBOX (defined in config.py), reprojects to EPSG:3161, and inserts them into the candidates table with `candidate_type='polygon'` and `source_dataset='waterbody'`. Compute and store surface area (in square meters) for each polygon; leave length null. Use GeoPandas for reading and reprojection, SQLAlchemy for inserts. Make it idempotent — running twice doesn't duplicate rows; use upsert on the OHN ID. Show me the plan before generating code."
 
Things to verify in the plan:
- [x] CRS handling explicit (detected from source `.prj`, not assumed)
- [x] Bounding box filter happens *before* reprojection (cheaper)
- [x] `candidate_type='polygon'` and `source_dataset='waterbody'` set correctly
- [x] Surface area computed in projected CRS (EPSG:3161) so units are meaningful
- [x] Idempotency strategy is real (upsert on OHN ID + source_dataset, since IDs may collide across datasets)
After implementation:
- [x] Run the script
- [x] `SELECT COUNT(*) FROM candidates WHERE source_dataset='waterbody';` — should match your expected polygon count
### Write the Watercourse ingestion script
 
**Plan Mode prompt**: "Write a Python script `backend/ingest/ohn_watercourse.py` that mirrors `ohn_waterbody.py` but reads the OHN Watercourse shapefile from `data/ohn_watercourse/`. Insert features with `candidate_type='reach_full'` and `source_dataset='watercourse'`. Compute and store length (in meters) for each linestring; leave area null. Same idempotency, same CRS handling, same bbox filter. Show me the plan before generating code, and call out anything that's different from the waterbody script beyond the file path and the type/length-vs-area fields."
 
Things to verify in the plan:
- [x] `candidate_type='reach_full'` and `source_dataset='watercourse'` set correctly
- [x] Length computed in projected CRS so units are meaningful
- [x] `parent_candidate_id` is null in Phase 1 (will be populated in Phase 2 when reaches are segmented)
- [x] Handles MultiLineString geometry properly (some watercourses may be split into multipart features)
After implementation:
- [x] Run the script
- [x] `SELECT candidate_type, COUNT(*) FROM candidates GROUP BY candidate_type;` — should now show both `polygon` and `reach_full` rows
- [x] Watercourse counts will likely outnumber waterbody counts substantially (streams are everywhere)
### Visual sanity check (do not skip)
 
- [ ] Open QGIS
- [ ] Layer → Add Layer → Add PostGIS Layers
- [ ] Connect to your local Postgres (host: `localhost`, port: 5432, db: hiddenhooks, user/pass: hiddenhooks)
- [ ] Add the candidates table as a layer (you may need two layers if QGIS struggles to render mixed geometry — filter one to polygons, one to linestrings)
- [ ] Verify polygons render in the right place at the right scale
- [ ] Verify watercourses **connect to** waterbodies at expected points — streams should flow into and out of lakes, not float in space disconnected
- [ ] If linestrings appear in the wrong location or polygons and lines don't align, fix CRS handling before proceeding
---
 
## Part 4 — Compute the one feature (1-2 hours)
 
For Phase 1, the only feature is `dist_to_road_meters`.
 
### Get road data
 
Use OSMnx — easier than dealing with Ontario Road Network for v1.
 
- [ ] **Plan Mode prompt**: "Write a script `backend/ingest/roads.py` that downloads the road network for our TEST_BBOX from OSM via OSMnx, projects it to EPSG:3161, and stores it in a `roads` table in Postgres. Cache the OSMnx download to a local file so we don't re-download on every run."
- [ ] Verify the plan handles caching properly
- [ ] Run it, sanity-check in QGIS as before
### Compute the feature
 
**Plan Mode prompt**: "Write `backend/scoring/dist_to_road.py` that computes the distance from each candidate to the nearest road, in meters, and updates the `dist_to_road_meters` column. Use PostGIS `ST_Distance` with the spatial index. The candidates table has both polygon and linestring geometries; the same query should handle both (`ST_Distance` is geometry-type-agnostic). For linestrings, distance is measured from the nearest point on the line, which is the correct semantic for a stream reach. Recommend the most efficient query approach. Show the SQL before writing."
 
Verify:
- [ ] Distances are in meters (requires projected CRS — they are, since we're in EPSG:3161)
- [ ] The "nearest" computation uses the spatial index efficiently (avoid full table scans)
- [ ] Updates happen in a single SQL statement, not row-by-row Python
- [ ] Both `polygon` and `reach_full` candidates get distances computed (no candidate_type filter)
After running:
- [ ] Spot-check 3-5 candidates of each type in QGIS — does each distance value match your eyeball estimate?
- [ ] `SELECT candidate_type, MIN(dist_to_road_meters), MAX(dist_to_road_meters), AVG(dist_to_road_meters), COUNT(*) FROM candidates GROUP BY candidate_type;` — sanity check distribution per type
---
 
## Part 5 — Backend API (2-3 hours)
 
### Build a minimal FastAPI service
 
**Plan Mode prompt**: "Create a FastAPI app in `backend/api/`. One endpoint: `GET /candidates` returns all candidates as a GeoJSON FeatureCollection, ranked by `dist_to_road_meters` descending (farther from roads = higher rank for v1's trivial scoring). Each feature includes: candidate ID, name, candidate_type, source_dataset, dist_to_road_meters, surface_area_m2 (nullable), length_m (nullable), rank (1-indexed). The FeatureCollection will contain mixed geometry types (Polygon/MultiPolygon for waterbodies, LineString/MultiLineString for watercourses) — this is valid GeoJSON and Mapbox handles it natively. Geometries returned in WGS84 (EPSG:4326) since Mapbox expects WGS84 even though storage is EPSG:3161. Use Pydantic models. Configure CORS for `http://localhost:3000`. Show me the endpoint signature and example response shape before generating."
 
Verify in the plan:
- [ ] Response is valid GeoJSON FeatureCollection (not custom format)
- [ ] Mixed geometry types in one FeatureCollection are explicitly handled
- [ ] Reprojection to EPSG:4326 happens at query time via `ST_Transform`
- [ ] CORS configured correctly for local dev
- [ ] Pydantic models validate the response shape, including nullable area/length fields
### Run and test
 
- [ ] `cd backend && uvicorn api.main:app --reload --port 8000`
- [ ] Open `http://localhost:8000/candidates` in browser — should see JSON response
- [ ] Validate the GeoJSON: paste into [geojson.io](http://geojson.io) — should render on a map there
- [ ] Open `http://localhost:8000/docs` for the auto-generated Swagger UI
---
 
## Part 6 — Frontend (4-6 hours)
 
This is the visually-important part. You said you want it polished and easy to use, so we're going to do this carefully even though Phase 1's content is minimal.
 
### Initialize Next.js with TypeScript
 
- [ ] In `frontend/`: `npx create-next-app@latest . --typescript --tailwind --app --eslint`
- [ ] Choose default options for the rest
- [ ] Confirm it runs: `npm run dev`, open `http://localhost:3000`
### Set up shadcn/ui
 
- [ ] Run `npx shadcn-ui@latest init` (or whatever the current command is — check shadcn's docs)
- [ ] Choose "Default" style, "Slate" or "Stone" base color (warmer than Slate, fits the cartographic aesthetic)
- [ ] Install initial components you'll need: `npx shadcn-ui@latest add button card sheet badge`
### Set up Mapbox
 
- [ ] Sign up at mapbox.com (free tier is plenty for personal use)
- [ ] Get your public access token from Account → Tokens
- [ ] Save in `frontend/.env.local`: `NEXT_PUBLIC_MAPBOX_TOKEN=pk.your_token_here`
- [ ] Add `.env.local` to `.gitignore` (should already be there from Next.js defaults)
- [ ] Install: `npm install mapbox-gl react-map-gl`
### Create a custom basemap style (this is what makes it feel cartographic)
 
- [ ] Open Mapbox Studio (studio.mapbox.com)
- [ ] Create a new style starting from "Outdoors" template
- [ ] Customize the palette to muted earth tones:
  - Land: warm beige (#e8dfd0 ish)
  - Water: muted blue (#a8c4d4 ish)
  - Forest: muted green (#aabc9a ish)
  - Roads: subtle gray, lower contrast than default
  - Labels: serif font if available, smaller than default
- [ ] Reference: National Geographic's online maps aesthetic
- [ ] Publish the style
- [ ] Copy the style URL (looks like `mapbox://styles/yourname/styleid`)
- [ ] Save in `.env.local`: `NEXT_PUBLIC_MAPBOX_STYLE=mapbox://styles/yourname/styleid`
This basemap step is what separates a generic Mapbox app from something that feels like HiddenHooks. Don't skip it.
 
### Add Framer Motion and Lucide
 
- [ ] `npm install framer-motion lucide-react`
### Set up typography
 
- [ ] In `frontend/app/layout.tsx`, configure two fonts via `next/font/google`:
  - **Inter** for UI chrome
  - **Source Serif 4** (or Lora) for body content in candidate cards/details
- [ ] Set up Tailwind theme to expose them as `font-sans` and `font-serif`
### Build the map page
 
**Plan Mode prompt**: "Create a Next.js page in `frontend/app/page.tsx` for the HiddenHooks map view. Layout: full-screen Mapbox map (using react-map-gl with the custom basemap from NEXT_PUBLIC_MAPBOX_STYLE), centered on Rouge Park. A collapsible left side panel (320px wide) using shadcn Sheet component, showing the ranked candidate list. On mount, fetch /candidates from `http://localhost:8000`. The FeatureCollection has mixed geometry — render in two layers: polygons as filled shapes with semi-transparent fill, linestrings (watercourses) as 2-3px wide lines. Both layers use the same rank-based color scale (high-rank = brighter/more saturated, low-rank = muted). Click a polygon, line, OR list item, the side panel highlights that candidate and shows: name (or 'Unnamed [type]' — distinguish 'Unnamed pond' from 'Unnamed stream reach' based on candidate_type), rank, distance to road, area or length depending on type, and a small breakdown card. Use Framer Motion for the side panel slide-in. Lucide icons for the chevron and any toggles. Show me the component structure and proposed file layout before generating."
 
Verify in the plan:
- [ ] Components are split sensibly (Map, CandidateList, CandidateCard, etc.) — not one giant page file
- [ ] Mapbox uses two separate layer definitions: one for polygons (fill type), one for linestrings (line type)
- [ ] Both layers share the same data source (the FeatureCollection) but filter by `$type` to render appropriately
- [ ] State management is local React state (no need for global state in Phase 1)
- [ ] Loading/error states are handled
- [ ] Polygon and line styling is computed from rank, not hardcoded
- [ ] Click handlers don't fight Mapbox's native pan/zoom
- [ ] List item rendering distinguishes pond vs stream reach in the displayed name and metadata
After implementation, polish pass:
- [ ] List items use the serif font for the candidate name (subtle but matters)
- [ ] Spacing is generous, not cramped — let the design breathe
- [ ] The selected candidate's polygon should visually pop (thicker stroke, slight glow)
- [ ] Side panel collapse animation feels smooth, not jerky
- [ ] If something feels off aesthetically, fix it now — bad UX patterns calcify
---
 
## Part 7 — End-to-end smoke test (30 min)
 
The moment of truth.
 
- [ ] Stop everything. Restart Docker, restart backend (uvicorn), restart frontend (npm run dev). Fresh slate.
- [ ] Load `http://localhost:3000`
- [ ] Map loads with custom basemap (not default Mapbox blue/gray)
- [ ] Both polygon candidates (filled shapes) and watercourse candidates (lines) appear, color-coded by rank
- [ ] Side panel shows ranked list mixing both types
- [ ] Click a polygon — both shape and list highlight; card shows area
- [ ] Click a watercourse line — both line and list highlight; card shows length
- [ ] Walk through the data path mentally: this feature came from a shapefile → ingestion script → Postgres → FastAPI query → JSON response → React state → Mapbox layer. You should be able to explain each hop.
- [ ] Pick the top-ranked candidate. Does its location make sense — is it actually in a remote part of Rouge Park, far from roads?
- [ ] Pick a bottom-ranked candidate. Is it next to a road as expected?
- [ ] Verify watercourses connect waterbodies visually — streams flow into and out of polygons, not floating disconnected
If both top and bottom rankings make geographic sense across both feature types, **Phase 1 is functionally complete.**
 
---
 
## Part 8 — Reflection and commit (30-45 min)
 
This is the part most people skip, and it's the part that compounds across phases.
 
### Document
 
- [ ] Update `README.md` with: project description, how to run locally (Docker → backend → frontend, in that order), tech stack, current phase
- [ ] Update `CLAUDE.md` with anything that changed about the architecture during Phase 1
- [ ] Create `docs/phase_1_reflection.md` with these prompts:
  - What worked smoothly?
  - What took longer than expected, and why?
  - What surprised you about the data, the tooling, or the process?
  - What architectural decisions are you uncertain about?
  - Looking at the top-ranked candidates: do they look like real candidates worth investigating, or does the trivial scoring miss the point?
  - What did you learn about Claude Code's working pattern on this project?
  - What's one thing you'd do differently if starting Phase 1 over?
### Commit
 
- [ ] `git add -A && git commit -m "Phase 1: vertical slice complete"`
- [ ] Push to your private GitHub repo if you set one up
- [ ] Tag the commit: `git tag phase-1-complete && git push --tags`
The tag matters — it gives you a "known good" point to roll back to if Phase 2 goes sideways.
 
---
 
## Done criteria
 
You're done with Phase 1 when:
- [ ] A live page shows ranked candidates in the test region — both waterbody polygons and watercourse linestrings
- [ ] Custom muted basemap is rendering, not default Mapbox
- [ ] Click-to-select works for polygons, lines, and list items
- [ ] You can explain every layer of the stack out loud
- [ ] The repo is committed, tagged, and documented
You do **not** need to:
- Have multiple scoring features (Phase 2 territory)
- Handle the full FMZ 16 region (Phase 2 territory)
- Look pretty enough for the portfolio (Phase 6 polish)
- Build the multi-agent layer (Phase 5 territory)
- Implement the four-component scoring formula (Phase 2 territory)
- Build a candidate detail view (Phase 2-3 territory)
- Segment watercourses into reaches (Phase 2 territory — `reach_full` rows are good enough for v1)
- Build the connectivity graph (Phase 2 territory — Watercourse data just needs to *exist* in the DB for now)
---
 
## If you get stuck
 
**GDAL fails to install on Windows native**: Try the conda installation again with `conda install -c conda-forge gdal` explicitly first, then geopandas. If still failing after an hour, switch to WSL2 — `wsl --install` in PowerShell as admin, redo Part 1's environment setup inside Ubuntu.
 
**Postgres container won't start**: Check `docker logs <container>` for errors. Most common: port 5432 is already in use by an existing Postgres install. Either stop the other one or change Docker Compose to use port 5433.
 
**Polygons render in the Atlantic Ocean**: CRS handling is wrong. Most likely you're storing in EPSG:3161 but serving without reprojecting to EPSG:4326. Add `ST_Transform(geom, 4326)` to your API query.
 
**Mapbox shows default style instead of yours**: Token issue or style URL issue. Verify `NEXT_PUBLIC_MAPBOX_TOKEN` and `NEXT_PUBLIC_MAPBOX_STYLE` are set in `.env.local` and that the style is published (not just saved as a draft) in Mapbox Studio.
 
**OSMnx hangs or errors**: It hits Overpass API which is rate-limited. Cache aggressively. If still bad, download an OSM PBF extract for southern Ontario from Geofabrik and read locally instead.
 
**Claude Code generates code that doesn't quite work**: Paste the error back, ask for both the fix and an explanation of why it broke. Don't accept fixes without explanations on load-bearing logic.
 
**You feel mid-phase scope creep tempting you**: Run `/scope-check`. If you've drifted, narrow back to the deliverable. Phase 2 will be there next month.
 
**Aesthetics feel off and you can't tell why**: Spend 30 minutes browsing CalTopo, onX Hunt, and National Geographic's web maps. Identify what specifically you like. Then look at your UI and find one thing to bring closer to that reference.
 
---
 
## After Phase 1
 
Bring back to the next conversation:
- Your `phase_1_reflection.md` notes
- A screenshot of the working app showing both polygons and lines
- Top 5 ranked candidates with rough coordinates (so we can compare against your Phase 0 calibration set when we have one) — note whether they're polygons or watercourses
- Any architectural decisions you're uncertain about
- Whether the trivial scoring (just distance to road) produces *any* candidates that look interesting, or if the rankings feel arbitrary
- Specifically for watercourses: do `reach_full` rankings feel meaningful, or does ranking whole streams feel too coarse? (This informs the segmentation strategy for Phase 2.)
Then we plan Phase 2: real ingestion of all FMZ 16 data, the four-component scoring formula, **stream reach segmentation** (splitting `reach_full` watercourses into smaller `reach_segment` candidates), the connectivity graph for fish inference, and the species-value table.