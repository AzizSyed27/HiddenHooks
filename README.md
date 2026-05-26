# HiddenHooks

A geospatial tool for finding under-fished water bodies in Ontario. Pulls hydrology
data from the Ontario Hydro Network (OHN), road and trail network from OpenStreetMap,
fish survey data from the Ontario Aquatic Resource Areas (ARA) dataset, and ranks water
bodies and stream reaches by a multi-component score. Built as a personal project.

---
<img width="1919" height="954" alt="image" src="https://github.com/user-attachments/assets/ce267fda-692d-44f6-a559-2bcdb7349305" />

---

## Current phase: Phase 5 — Multi-agent reasoning layer (complete)
Coverage: **FMZ 16 and FMZ 17** (southern and central Ontario).

Four scoring components, each weighted independently per query:

| Signal | Label | Description |
|---|---|---|
| Hiddenness | H | Distance to nearest road — higher is more hidden |
| Accessibility | A | Proximity to trails and parking — lower distance = more accessible |
| Fish potential | F | ARA species survey match — strong / plausible / speculative confidence tiers |
| Ecology bonus | E | Habitat quality and connectivity through the reach network |

Weights are tunable from the panel. The composite score drives map color and per-FMZ rank.
A drive-time filter (Mapbox isochrone) limits candidates to within 20, 30, 45, or 60 minutes from a chosen location. Selecting a candidate shows drive time, distance, and route to nearest parking.

Phase 5 adds on-demand AI reasoning on top of the base scores. Two opt-in buttons — never auto-triggered:

- **Get AI take** — re-ranks the current candidate list using three parallel specialist agents (Weather, Timing/Pressure, Species) followed by peer review and a Coordinator synthesis. Replaces the candidate list with an AI-ordered view showing per-candidate reasoning, specialist agreement signal, and the weighting rationale.
- **Plan this trip** — runs the same three-round agent pipeline for a single selected candidate and produces a structured trip advisory: overall go/wait/skip call, best fishing window, active species, conditions summary, things to watch, and key risks.

---

## Tech stack

| Layer | Tools |
|---|---|
| Database | PostgreSQL 16 + PostGIS 3.4 (Docker) |
| Backend | Python 3.11, FastAPI, SQLAlchemy, GeoPandas, OSMnx, NetworkX |
| Frontend | Next.js 16, React 19, TypeScript |
| Map | Mapbox GL JS via react-map-gl, custom basemap style |
| UI | shadcn/ui, Tailwind CSS 4, Framer Motion, Lucide icons |
| Fonts | Poppins (UI chrome), Lora (candidate names) |
| AI layer | Anthropic API (Claude) — multi-agent orchestration, Phase 5 |
| Weather | Open-Meteo free API — forecast + ERA5 historical, no auth |

---

## Running locally

### Prerequisites

- Docker Desktop
- Python 3.11+ (conda environment: `hiddenhooks`)
- Node.js 20+
- A Mapbox account — access token and a custom style URL
- An Anthropic API key (Phase 5 agent endpoints)

Create `backend/.env` with:

```
MAPBOX_API_KEY=pk.your_token_here
ANTHROPIC_API_KEY=sk-ant-your_key_here
```

### 1. Start the database

```bash
cd docker
docker compose up -d
```

The PostGIS container starts on port 5432. On first run it applies the schema from
`docker/initdb/`. If the container already exists with data, the init scripts are skipped.

### 2. Set up the Python environment

```bash
conda activate hiddenhooks
```

### 3. Ingest data

OHN shapefiles are expected at:
- `phase-0-data/ohn/Ontario_Hydro_Network_(OHN)_-_Waterbody/`
- `phase-0-data/ohn/Ontario_Hydro_Network_(OHN)_-_Watercourse/`

ARA shapefile is expected at:
- `phase-0-data/ara/`

Download from [Ontario GeoHub](https://geohub.lio.gov.on.ca/) and place them there.

```bash
cd backend
python -m ingest.ohn_waterbody
python -m ingest.ohn_watercourse
python -m ingest.roads             # downloads OSM road network, caches to cache/
```

> **Known issue:** OHN ingest may leave literal `"NaN"` strings in the `name` column.
> After each waterbody or watercourse ingest, run:
> `UPDATE candidates SET name = NULL WHERE name = 'NaN';`

### 4. Run processing and scoring scripts

```bash
python -m scoring.dist_to_road              # ~8 min — populates h_score proxy
python -m processing.snap_ara_to_candidates
python -m processing.build_connectivity
python -m scoring.score_hiddenness
python -m scoring.score_accessibility
python -m scoring.score_fish_potential
python -m scoring.score_ecology
```

Each script is idempotent — safe to re-run.

### 5. Start the API

```bash
cd backend
python -m uvicorn api.main:app --port 8000 --reload
```

Endpoints:
- `GET /health` — liveness check
- `GET /regions` — list FMZ zones with candidate counts
- `GET /candidates` — scored GeoJSON with optional `fmz`, `w_h/w_a/w_f/w_e` weights,
  and `near_lat`/`near_lon`/`drive_time_min` drive-time filter
- `GET /candidates/{id}/drive-time?from_lat=X&from_lon=Y` — Mapbox-routed drive time,
  distance, and route geometry to nearest parking for a selected candidate
- `POST /agents/rerank` — 3-round multi-agent re-rank for a list of candidate IDs
- `POST /agents/trip-plan` — 3-round multi-agent trip advisory for a single candidate

### 6. Configure frontend environment

Create `frontend/.env.local`:

```
NEXT_PUBLIC_MAPBOX_TOKEN=pk.your_token_here
NEXT_PUBLIC_MAPBOX_STYLE=mapbox://styles/your_username/your_style_id
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 7. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## Project structure

```
docker/
  docker-compose.yml
  initdb/                    schema SQL applied on first container start

backend/
  config.py                  centralised paths + DATABASE_URL + API constants
  ingest/                    OHN waterbody, watercourse, OSM roads, ARA, regions
  processing/                snap_ara_to_candidates, build_connectivity, segment_reaches
  scoring/                   dist_to_road, hiddenness, accessibility,
                             fish_potential, ecology
  services/                  mapbox.py (isochrone + directions), weather.py (Open-Meteo),
                             conditions.py (datetime classifiers), topn.py (candidate
                             selection), orchestrator.py (3-round agent runner),
                             agents.py (specialist/coordinator calls),
                             anthropic_client.py (Claude SDK wrapper),
                             prompts/ (system prompt files per agent role)
  api/                       FastAPI app — /health, /regions, /candidates,
                             /drive-time, /agents/rerank, /agents/trip-plan

frontend/
  app/                       Next.js App Router pages
  components/
    map/                     MapView (react-map-gl layers, composite coloring)
    panel/                   CandidatePanel, CandidateDetail, LocationFilter,
                             AiRerankResult, TripPlanResult
  lib/                       shared types, utilities

phase-0-data/                raw data files — not committed
private/                     trip logs — not committed, gitignored
```

---

## Notes

- Trip data (actual GPS coordinates of validated spots) is never committed.
  Personal logs go in `private/` which is gitignored.
- The repo is private during development.
- OHN has a trails dataset that could replace the OSMnx data in a future iteration.
- ARA survey coverage varies significantly across FMZ 16 vs FMZ 17 — fish confidence
  tiers (strong / plausible / speculative) reflect this uncertainty explicitly.
