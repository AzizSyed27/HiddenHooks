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