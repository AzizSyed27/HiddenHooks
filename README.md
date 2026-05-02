# HiddenHooks

A geospatial tool for finding under-fished water bodies in Ontario. Pulls hydrology
data from the Ontario Hydro Network, road network from OpenStreetMap, and ranks water
bodies and stream reaches by how hidden they are from roads. Built as a personal /
portfolio project.

---

## Current phase: Phase 1 — Vertical slice

End-to-end pipeline on a test region (~20 km radius around Rouge National Urban Park,
Scarborough, ON). Single scoring signal: distance to nearest road. The full map view
is working — candidates are ranked, colored by hiddenness, and clickable.

Planned signals for later phases: accessibility (drive time, trail proximity),
fish species potential, and ecology bonuses. Scoring weights will be tunable per
query.

---

## Tech stack

| Layer | Tools |
|---|---|
| Database | PostgreSQL 16 + PostGIS 3.4 (Docker) |
| Backend | Python 3.11, FastAPI, SQLAlchemy, GeoPandas, OSMnx |
| Frontend | Next.js 16, React 19, TypeScript |
| Map | Mapbox GL JS via react-map-gl, custom basemap style |
| UI | shadcn/ui, Tailwind CSS 4, Framer Motion, Lucide icons |
| Fonts | Poppins (UI chrome), Lora (candidate names) |
| AI layer | Anthropic API — planned for later phases |

---

## Running locally

### Prerequisites

- Docker Desktop
- Python 3.11+ (conda environment recommended)
- Node.js 20+
- A Mapbox account — access token and a custom style URL

### 1. Start the database

```bash
cd docker
docker compose up -d
```

The PostGIS container starts on port 5432. On first run it applies the schema from
`docker/initdb/`. If the container already exists with data, the init scripts are
skipped.

### 2. Set up the Python environment

```bash
conda activate hiddenhooks   # or: pip install -r backend/requirements.txt
```

### 3. Ingest data

OHN shapefiles are expected at:
- `phase-0-data/ohn/Ontario_Hydro_Network_(OHN)_-_Waterbody/`
- `phase-0-data/ohn/Ontario_Hydro_Network_(OHN)_-_Watercourse/`

Download from [Ontario GeoHub](https://geohub.lio.gov.on.ca/) and place them there.

```bash
cd backend
python -m ingest.ohn_waterbody
python -m ingest.ohn_watercourse
python -m ingest.roads          # downloads OSM road network, caches to cache/
python -m scoring.dist_to_road  # ~8 min on first run
```

Each script is idempotent — safe to re-run.

### 4. Start the API

```bash
cd backend
python -m uvicorn api.main:app --port 8000 --reload
```

Verify: `curl http://localhost:8000/candidates | python -m json.tool | head -20`

### 5. Configure frontend environment

Create `frontend/.env.local`:

```
NEXT_PUBLIC_MAPBOX_TOKEN=pk.your_token_here
NEXT_PUBLIC_MAPBOX_STYLE=mapbox://styles/your_username/your_style_id
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 6. Start the frontend

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
  initdb/               schema SQL applied on first container start

backend/
  config.py             centralised paths + DATABASE_URL
  ingest/               OHN waterbody, watercourse, OSM roads
  scoring/              dist_to_road (Phase 1)
  api/                  FastAPI app — GET /candidates

frontend/
  app/                  Next.js App Router pages
  components/
    map/                MapView (react-map-gl layers)
    panel/              CandidatePanel (side panel + detail card)
  lib/                  shared types, utilities

phase-0-data/           raw data files — not committed
private/                trip logs — not committed, gitignored
```

---

## Notes

- Trip data (actual GPS coordinates of validated spots) is never committed.
  Personal logs go in `private/` which is gitignored.
- The repo is private during development.
