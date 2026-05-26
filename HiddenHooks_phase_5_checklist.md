# HiddenHooks — Phase 5 Checklist

**Goal**: Add a multi-agent reasoning layer on top of Phase 2's static scoring. Three specialist agents (Weather, Timing/Pressure, Species) reason independently about top-N candidates, perform peer critique and revision, and a Coordinator synthesizes a final ranking (re-rank mode) or trip plan (trip-plan mode). On-demand only, opt-in via UI buttons. Cost-bounded by a hard top-N cap regardless of database size.

**Deliverable**: Two new endpoints — `POST /agents/rerank` and `POST /agents/trip-plan` — driven by two new UI surfaces ("Get AI take" button in the panel header for re-rank, "Plan this trip" button in each detail card for trip-plan). Re-rank reorders the visible top-N with a one-line "why" per candidate. Trip-plan produces a structured-fields deep dive (best window, expected species behavior, conditions to watch, key risks) for a single locked candidate. Both run a 3-round multi-agent pattern: parallel specialist analysis → parallel peer critique and revision → coordinator synthesis.

**Total time**: 6-8 weekends alongside other commitments. Larger than Phase 3 in scope, smaller than Phase 2. The complexity is in the orchestration, prompts, and frontend state management — not the data layer.

**Working partner**: Claude Code. The Phase 2/3 working pattern carries forward — Plan Mode for everything load-bearing, push back on bad ideas, integration smoke test as forcing function.

**Mindset**: Phase 5 is a synthesis layer, not a forecaster. The agents don't predict fish behavior — they reason about how known scoring signals interact with current conditions and explain the call. If you find yourself writing a prompt that asks Claude to "predict whether you'll catch fish," stop. The job is to synthesize known information into actionable insight, not to forecast the future. The user makes the catch/no-catch call themselves; the agents just present the relevant considerations clearly.

---

## Part 0 — Working principles, scope, design decisions (read first, do not skip)

### Phase 5 mission

Phase 2 produces scored candidates that are good "in general." Phase 5 produces analysis that is good "right now." The synthesis layer takes Phase 2's H/A/F/E candidates plus current-conditions context (weather, season, day-of-week, time-of-day) and answers two questions:

1. **Re-rank:** of the candidates I'm currently looking at, which one is the best call given the conditions tomorrow?
2. **Trip-plan:** for this specific candidate I'm locking in, what should I know going in?

Phase 5 doesn't replace the existing scoring or ranking. It's a layer *on top* that's opt-in via explicit user action.

### Scope locked

- **Multi-agent architecture (light pattern with peer review):**
  - 3 specialist agents: Weather, Timing/Pressure, Species
  - 1 coordinator agent
  - 3 rounds: parallel independent analysis → parallel peer critique and revision → coordinator synthesis
- **External data sources:**
  - Weather via Open-Meteo (forecast + 7-day history, free, no auth)
  - Day-of-week and season computed at request time (no ingestion needed)
- **Two endpoints:**
  - `POST /agents/rerank` — operates on top-N visible candidates
  - `POST /agents/trip-plan` — operates on single locked candidate
- **Top-N cap:** Default 30. User-configurable via toggle but hard-capped at 50. Regardless of database size, the agents NEVER see more than the cap.
- **Top-N selection modes:**
  - Top-N of current panel view (default; respects user's filters and weights)
  - Top-N by F-score (alternative; catches high-fish-potential regardless of composite)
- **On-demand only:** Agents fire exclusively on explicit button click. No auto-fire on panel refresh.
- **Stateless:** No memory across sessions. No learning loop. Trip outcomes don't feed back into the system in Phase 5 (Phase 6 territory).
- **Light multi-agent:** No tool use, no autonomous agent loops, no recursion. All inter-agent communication routes through the coordinator's orchestration.
- **Critique-then-revise pattern for peer review:** Each specialist explicitly critiques peer outputs before revising its own position. Output structure includes `critique_of_peers`, `my_revised_position`, `what_changed_from_round_1`.
- **Prompt storage:** Separate `backend/prompts/` directory, one `.md` file per agent. Loaded at module import. Git-tracked.
- **API key:** `ANTHROPIC_API_KEY` in `backend/.env`, same gitignore discipline as `MAPBOX_API_KEY`.

### Out of scope / explicit non-goals

- Autonomous agents (agents calling tools, fetching their own data, planning their own actions)
- Multi-turn debate (more than one peer-review round)
- Direct agent-to-agent communication (everything routes through coordinator)
- Persistent memory (no embeddings, no past-session recall)
- Tactical fishing advice (don't tell user what bait to use; they know better)
- Fish-catching forecasting (agents synthesize, they don't predict catch rates)
- Auto-fire on panel updates (cost discipline)
- Replacing or modifying Phase 2 scoring (Phase 5 is additive only)
- Real-time water sensor integration (Phase 7+)
- Moon phase / solunar tables (signal value unclear; skip until trip data justifies)
- Agent learning from trip outcomes (Phase 6 calibration territory)
- Specialized agents beyond the three (no barometric pressure agent, water temp agent, etc. — Phase 7+ if trip data shows they matter)

### Locked design decisions for cost

- Top-N hard-capped at 50, default 30
- Re-rank: ~$0.57 per call at top-30 (3 specialists × 2 rounds + 1 coordinator)
- Trip-plan: ~$0.08 per call (single candidate, same 3-round pattern)
- Realistic monthly cost: $15-40 at typical personal-use frequency
- Cost monitoring: log token usage per call in development; review weekly during Phase 5 build

### Working principles (inherit from Phase 2 and 3)

- Branch per workstream: `phase-5/01-weather-ingestion`, `phase-5/02-conditions-utils`, etc.
- Plan Mode for any non-trivial change
- Push back on bad ideas, especially scope creep
- Document decisions in CLAUDE.md as they're locked
- Run `npm run build` after every frontend file change
- Restart uvicorn manually if API behavior doesn't match the code on disk
- Integration smoke test at midpoint as forcing function
- Don't merge until each workstream's verification passes
- "Shipping is a feature" — don't gold-plate v1

### Phase 5 fragilities to document up-front

- **External service dependencies (two now):** Open-Meteo for weather, Anthropic API for agent calls. Either can fail. Frontend handles agent failures gracefully with an error banner; existing Phase 2/3 functionality remains usable without the agent layer.
- **Prompt quality is load-bearing.** Bad prompts produce bad reasoning. Plan for an iteration weekend after the initial agent build to tune prompts based on real candidate data.
- **Cost can spike if usage patterns change.** Worst-case is enthusiastic user clicking "Get AI take" repeatedly. Add basic rate-limiting in the orchestrator (no more than one in-flight agent call per user, debounce 5s between requests).
- **JSON parsing of agent outputs.** Claude can occasionally produce malformed JSON despite structured output instructions. Wrap parsing in defensive try/except; if parse fails, retry once with explicit "respond with valid JSON only" reminder; if second attempt fails, return graceful error.
- **Open-Meteo coverage and accuracy.** Free tier is great for personal use but rate-limited at ~10k requests/day. Caching weather by (location, date) is cheap and obvious; do it.

### Decision points to revisit in Phase 6

- Whether peer-review round adds value vs single-round multi-agent (empirical, measure by reviewing trip outcomes vs predictions)
- Whether 3 specialist axes are the right axes (trip data might suggest barometric pressure, water temp, etc.)
- Whether trip outcomes should feed back into prompts as few-shot examples
- Whether per-candidate specialist scores should be displayed alongside Phase 2 sub-scores in the detail card

---

## Part 1 — Weather ingestion via Open-Meteo (3-4 hours)

### Context

Open-Meteo is a free weather API requiring no authentication. Returns forecast (up to 16 days) and historical data (back several years) in JSON. Coverage is global. Rate-limited but extremely generous for personal use.

This part builds a thin client that fetches weather for a given location and time window. Caching is essential — agent calls will repeatedly request weather for the same locations (your fishing area).

### Files to create

- `backend/services/weather.py` — Open-Meteo client + caching
- `backend/config.py` — add Open-Meteo config constants

### Decisions to lock

- HTTP client: `requests` library (sync, simple, same as Mapbox client)
- Timeout: 5 seconds
- Cache strategy: in-memory dict keyed on `(round(lat, 2), round(lon, 2), date)` — ~1km precision, granular enough to vary by candidate, coarse enough for aggressive cache hits
- Cache TTL: 1 hour for forecast data (forecasts update; refresh hourly), 24 hours for historical data (won't change)
- API endpoint: `https://api.open-meteo.com/v1/forecast` for current/forecast, `https://archive-api.open-meteo.com/v1/archive` for historical
- Returned data shape: a structured dict with current conditions, 24h forecast, and 7-day historical summary

### Open-Meteo parameters to request

For forecast:
- `latitude`, `longitude` — location
- `current` — current weather snapshot
- `hourly` — temperature, precipitation, wind speed, cloud cover, pressure
- `daily` — temperature max/min, precipitation sum, sunrise, sunset, wind speed max
- `forecast_days=2` — today and tomorrow
- `timezone=America/Toronto`

For historical:
- Same location
- `start_date` — 7 days ago
- `end_date` — yesterday
- `daily` — temperature max/min, precipitation sum, wind speed max

### Plan Mode prompt

**Plan Mode prompt**: "Create `backend/services/weather.py`. One public function: `get_weather_context(lat: float, lon: float) -> dict`. Returns a structured dict with current conditions, next-48h forecast, and 7-day historical summary. Use Open-Meteo's free API (no auth needed). Cache results in memory keyed on (round(lat, 2), round(lon, 2), date) with 1-hour TTL for forecast, 24-hour TTL for historical. Two custom exceptions: `WeatherAPIError` and `WeatherTimeoutError(WeatherAPIError)`. Same hygiene as `services/mapbox.py` — never include any third-party data in exception messages beyond status code and a 200-char snippet. Show me the file structure, the dict shape returned, the cache implementation, and the example response before generating."

### Verify in the plan

- [x] Cache keys are coarsened to ~1km (round to 2 decimal places); not at full lat/lon precision
- [x] Cache TTL differs for forecast (1 hr) vs historical (24 hr) data
- [x] Two endpoints (forecast vs archive) are used appropriately
- [x] Exception handling parallels `services/mapbox.py` patterns
- [x] Returned dict has explicit schema (not raw Open-Meteo response)
- [x] Timezone is `America/Toronto` so day-of-week and time-of-day computations are local

### Verification

```bash
cd backend
python -c "
import sys; sys.path.insert(0, '.')
from services.weather import get_weather_context
ctx = get_weather_context(43.77, -79.26)
import json; print(json.dumps(ctx, indent=2, default=str))
"
```

Expected: structured dict with current conditions, forecast, and historical summary. Reasonable values for Scarborough.

Test caching:
```bash
python -c "
import sys, time; sys.path.insert(0, '.')
from services.weather import get_weather_context
t0 = time.time(); get_weather_context(43.77, -79.26); print(f'Cold: {time.time()-t0:.2f}s')
t1 = time.time(); get_weather_context(43.77, -79.26); print(f'Warm: {time.time()-t1:.2f}s')
"
```

Expected: cold ~0.5-2s (network call), warm <0.01s (cache hit).

### Definition of done

- Module imports cleanly
- Manual test returns valid weather data for Scarborough
- Cache hit on second identical call
- Failure modes tested: bad network → WeatherAPIError, timeout simulated → WeatherTimeoutError

### Branch: `phase-5/01-weather-ingestion`

---

## Part 2 — Conditions utilities: day-of-week, season, time-of-day (1-2 hours)

### Context

Some agent inputs are computed from `datetime.now()` rather than fetched from external services. Centralize these into a single utility module so all agents speak the same language.

### Files to create

- `backend/services/conditions.py`

### Decisions to lock

- All time computations use `America/Toronto` timezone (consistent with weather)
- Season boundaries: Spring (Mar 20 - Jun 20), Summer (Jun 20 - Sep 22), Fall (Sep 22 - Dec 21), Winter (Dec 21 - Mar 20). Use astronomical seasons (equinoxes/solstices), not meteorological.
- Day-of-week categories: weekday, saturday, sunday (3 categories, since Saturday and Sunday have different fishing-pressure profiles)
- Time-of-day categories: dawn (6-8am), morning (8am-noon), midday (noon-4pm), evening (4pm-8pm), dusk (8-10pm), night (10pm-6am)

### Plan Mode prompt

**Plan Mode prompt**: "Create `backend/services/conditions.py`. Three public functions: `get_day_category(dt: datetime | None = None) -> str` (returns 'weekday', 'saturday', 'sunday'), `get_season(dt: datetime | None = None) -> str` (returns 'spring', 'summer', 'fall', 'winter' using astronomical season boundaries), `get_time_of_day(dt: datetime | None = None) -> str` (returns 'dawn', 'morning', 'midday', 'evening', 'dusk', 'night'). When `dt` is None, use current time in America/Toronto timezone. Pure stdlib; no new dependencies. Include a `get_all_conditions(dt: datetime | None = None) -> dict` convenience function that returns all three plus the raw datetime. Show me the boundary constants and the test cases before generating."

### Verify in the plan

- [x] All functions accept optional `dt` for testability
- [x] Default behavior uses `zoneinfo.ZoneInfo("America/Toronto")` (stdlib timezone, not pytz)
- [x] Season boundaries are explicit constants, not magic strings
- [x] Time-of-day boundaries are explicit and don't overlap

### Verification

```bash
python -c "
import sys; sys.path.insert(0, '.')
from datetime import datetime
from zoneinfo import ZoneInfo
from services.conditions import get_all_conditions
print(get_all_conditions())
# Test specific dates
print(get_all_conditions(datetime(2026, 1, 15, 7, 30, tzinfo=ZoneInfo('America/Toronto'))))
print(get_all_conditions(datetime(2026, 7, 4, 14, 0, tzinfo=ZoneInfo('America/Toronto'))))
print(get_all_conditions(datetime(2026, 10, 31, 22, 30, tzinfo=ZoneInfo('America/Toronto'))))
"
```

Expected: correct categorization for each test datetime. Winter weekday dawn, summer saturday midday, fall saturday dusk, etc.

### Definition of done

- All three functions work correctly across season boundaries (test boundary dates explicitly)
- Default-now behavior produces the right result for current time
- Convenience function returns a complete conditions dict

### Branch: `phase-5/02-conditions-utils`

---

## Part 3 — Prompt design and storage (3-4 hours)

### Context

Each agent has a system prompt that defines its role, inputs, and output format. Prompts live in `backend/prompts/` as separate `.md` files, loaded at module import. Editing a prompt doesn't require touching agent code.

This part is more design than code. The prompts are the load-bearing thing; budget time to iterate on them.

### Files to create

- `backend/prompts/weather_agent.md`
- `backend/prompts/timing_agent.md`
- `backend/prompts/species_agent.md`
- `backend/prompts/coordinator_rerank.md`
- `backend/prompts/coordinator_trip_plan.md`
- `backend/prompts/peer_review.md` — shared instructions for the peer-review round
- `backend/services/prompts.py` — loader utility

### Decisions to lock

- One prompt per agent role
- All prompts are markdown for readability
- Prompts include explicit output JSON schema (Claude responds in structured JSON)
- Peer-review prompt is *shared* across specialists — same critique-then-revise instructions for all
- Prompt loader caches at module import (read once, reuse)

### Agent role definitions

**Weather Agent**

Role: assess how current and forecast weather conditions affect fishing potential at this candidate.

Input (per candidate, for each in top-N):
- Candidate metadata (name, type, FMZ, sub-scores)
- Weather context (current, next-48h forecast, 7-day history)

Output (per candidate):
- `weather_score`: 0.0-1.0 (how favorable weather is for fishing this specific candidate)
- `key_signals`: list of 2-3 key weather factors driving the score
- `rationale`: one-sentence explanation
- `confidence`: 'high', 'medium', 'low' (data quality / signal strength)

**Timing/Pressure Agent**

Role: assess fishing pressure and time-of-day favorability for this candidate.

Input (per candidate):
- Candidate metadata including `a_score` (accessibility = popularity proxy)
- Day-of-week, season, time-of-day from conditions module
- Candidate's name (named candidates get more pressure)

Output (per candidate):
- `timing_score`: 0.0-1.0 (how favorable timing is)
- `expected_pressure`: 'low', 'moderate', 'high'
- `best_window`: short text like "early morning" or "weekday only"
- `rationale`: one-sentence explanation
- `confidence`: 'high', 'medium', 'low'

**Species Agent**

Role: assess whether species likely present at this candidate are active in current conditions.

Input (per candidate):
- Candidate's `f_species`, `f_confidence`, `f_tier`
- Current season, water temperature estimate (derived from recent air temp)
- Weather context (recent precipitation affects water clarity and flow)

Output (per candidate):
- `species_score`: 0.0-1.0
- `active_species`: list of likely-active species from candidate's f_species
- `inactive_species`: list of present-but-inactive species
- `key_factors`: 2-3 factors affecting species activity
- `rationale`: one-sentence explanation
- `confidence`: 'high', 'medium', 'low'

**Coordinator (re-rank mode)**

Role: synthesize specialist outputs (post-peer-review) into a re-ranked list with one-line rationale per candidate.

Input:
- All candidates' Phase 2 scores
- All three specialists' final (post-revision) outputs per candidate
- Note of which specialists changed positions during peer review and why

Output:
- Ordered list of candidate IDs
- Per candidate: `rank`, `composite_call`, `one_line_why`, `specialist_agreement` (high/medium/low based on score variance across specialists)

**Coordinator (trip-plan mode)**

Role: produce structured trip-plan deep dive for single locked candidate.

Output structure (structured fields):
- `overall_call`: 'go now', 'good window coming', 'wait', 'skip'
- `best_window`: short text
- `expected_species`: list with brief activity notes per species
- `conditions_summary`: 2-3 sentence summary
- `things_to_watch`: list of 2-4 things to be aware of (weather changes, pressure, water clarity)
- `key_risks`: 1-2 things that could go wrong
- `confidence`: 'high', 'medium', 'low'

### Peer-review shared prompt

Used by each specialist in Round 2. Instructions:

> You previously analyzed [N] candidates in Round 1 (your output below). Two peer specialists also analyzed the same candidates from their perspectives (their outputs below). 
>
> Your task in this round:
> 1. Critique each peer's reasoning. Identify their weakest claim. Be specific.
> 2. Revise your own position where peer reasoning is compelling. Hold firm where it isn't.
> 3. Output JSON with three fields: `critique_of_peers`, `my_revised_position` (full revised scores for all candidates), `what_changed_from_round_1` (list of specific changes with reasons).
>
> Critique-then-revise: you must engage with peer reasoning before revising. Don't passively accept or reject; reason through it. If you stand by your original position on a candidate, say why explicitly.

### Plan Mode prompt

**Plan Mode prompt**: "Create the six prompt files in `backend/prompts/` (weather_agent.md, timing_agent.md, species_agent.md, coordinator_rerank.md, coordinator_trip_plan.md, peer_review.md). Each is a markdown file with: role description, input schema, output JSON schema, explicit instructions for the agent's reasoning. Also create `backend/services/prompts.py` with `load_prompt(name: str) -> str` that reads from the prompts directory and caches at module level. Show me the full text of each prompt before generating, and call out any schema decisions that affect downstream parsing. Don't generate yet — the prompts are the load-bearing artifact and I want to review each individually."

### Verify in the plan

- [x] Each agent prompt explicitly specifies the JSON output schema
- [x] Output schemas are parseable (no free-form prose where structured fields are needed)
- [x] Peer-review prompt is generic enough to work for all three specialists
- [x] Coordinator prompts produce schemas that match the eventual API response structure
- [x] Loader caches prompts (don't read file on every agent call)

### Verification

```bash
python -c "
import sys; sys.path.insert(0, '.')
from services.prompts import load_prompt
for name in ['weather_agent', 'timing_agent', 'species_agent', 'coordinator_rerank', 'coordinator_trip_plan', 'peer_review']:
    p = load_prompt(name)
    print(f'{name}: {len(p):,} chars')
"
```

Expected: all six prompts load, reasonable sizes (500-2000 chars each).

### Definition of done

- All six prompts written and reviewed
- Loader function works
- Each prompt includes explicit output JSON schema
- The peer-review prompt is reusable across specialists

### Branch: `phase-5/03-prompts`

---

## Part 4 — Anthropic client + agent runner (3-4 hours)

### Context

The Anthropic SDK is the bottom layer. Build a thin client that handles authentication, retries, JSON parsing, and error handling. All agents use it.

### Files to create

- `backend/services/anthropic_client.py` — thin client wrapper
- `backend/services/agents.py` — agent runner functions (one per role)

### Decisions to lock

- Use the official Anthropic Python SDK (`anthropic` package)
- Model: `claude-opus-4-7` or `claude-sonnet-4-6` (need to verify current via product-self-knowledge skill at implementation time)
- Default to Sonnet 4.6 for cost; allow override to Opus 4.7 for trip-plan if quality matters
- Max tokens: 4096 for specialists, 8192 for coordinator (coordinator has more context to synthesize)
- Temperature: 0.3 for specialists (consistent reasoning), 0.5 for coordinator (slightly more creative synthesis)
- JSON parsing: defensive try/except with one retry. Second failure returns graceful error to caller.
- Timeout: 30 seconds per call (specialist calls can be slow with large input)

### Plan Mode prompt

**Plan Mode prompt**: "Create `backend/services/anthropic_client.py` with a thin wrapper around the Anthropic SDK. One function: `call_claude(system_prompt: str, user_message: str, max_tokens: int = 4096, temperature: float = 0.3, model: str = 'claude-sonnet-4-6') -> dict`. Returns the parsed JSON from Claude's response. Handles: ANTHROPIC_API_KEY validation, structured JSON parsing with one retry on malformed JSON, timeout (30s), HTTP error mapping, rate limit detection. Two custom exceptions: `AnthropicAPIError` and `AnthropicTimeoutError(AnthropicAPIError)`. Same hygiene as the Mapbox client — never include the API key in exception messages.

Then create `backend/services/agents.py` with one runner function per agent role: `run_weather_agent(candidates, weather_ctx)`, `run_timing_agent(candidates, conditions)`, `run_species_agent(candidates, weather_ctx, conditions)`, `run_peer_review(agent_role, original_output, peer_outputs)`, `run_coordinator_rerank(candidates, specialist_outputs)`, `run_coordinator_trip_plan(candidate, specialist_outputs)`. Each loads its prompt from `services/prompts`, formats the user message with the input data, and calls `call_claude`. Show me the file structure before generating."

### Verify in the plan

- [x] API key validated at first call, not import time (importable for testing)
- [x] JSON parsing has retry logic with explicit "respond with valid JSON" reminder
- [x] Timeout configured (30s)
- [x] No API key leak in exception messages
- [x] Agent runners are pure functions — input → output, no side effects beyond the API call
- [x] Peer review function takes role + original output + peer outputs as separate args

### Verification

```bash
python -c "
import sys; sys.path.insert(0, '.')
from services.anthropic_client import call_claude
result = call_claude(
    system_prompt='You output JSON only.',
    user_message='Output JSON with one field: {\"hello\": \"world\"}',
    max_tokens=100
)
print(result)
"
```

Expected: `{'hello': 'world'}`. Verifies authentication, JSON parsing, basic round trip.

Test malformed-JSON retry:
```bash
# Set temperature high and ask for non-JSON response; verify retry kicks in
python -c "
import sys; sys.path.insert(0, '.')
from services.anthropic_client import call_claude
result = call_claude(
    system_prompt='Be conversational.',
    user_message='Tell me a joke. Just prose, no JSON.',
    max_tokens=200, temperature=0.7
)
print(result)
"
```

Expected: first call returns prose (not JSON); retry with stronger instruction produces JSON or returns graceful error.

### Definition of done

- Client module imports cleanly
- Basic round-trip works
- Malformed-JSON retry verified
- Authentication failure produces clean error (not API key leak)
- All six agent runner stubs exist (can be empty initially, populated in Part 5)

### Branch: `phase-5/04-anthropic-client`

---

## Part 5 — Orchestrator: 3-round multi-agent pattern (4-5 hours)

### Context

The orchestrator coordinates the 3-round pattern. It's the heart of Phase 5's architecture — the place where "specialists run in parallel," "specialists peer-review in parallel," and "coordinator synthesizes" all happen in sequence.

### Files to create

- `backend/services/orchestrator.py` — the 3-round runner
- `backend/services/topn.py` — top-N candidate selection logic

### Decisions to lock

- Parallel calls in Round 1 and Round 2 via `asyncio` (the SDK supports async) OR `concurrent.futures.ThreadPoolExecutor` (simpler, sync code)
- Recommendation: ThreadPoolExecutor for simplicity. asyncio adds complexity for one benefit (concurrent I/O), and the code is otherwise sync FastAPI.
- Round 1 timeout: 30s per specialist
- Round 2 timeout: 30s per specialist
- Round 3 timeout: 60s for coordinator (more synthesis work)
- Total worst case: 30 + 30 + 60 = 120s. Frontend shows loading state.
- Realistic case: ~15-25s total (Sonnet is fast)
- If any specialist fails in Round 1, log and continue with nulls in their column. Coordinator synthesizes with caveat.
- If 2+ specialists fail in Round 1, abort and return graceful error.

### Plan Mode prompt

**Plan Mode prompt**: "Create `backend/services/orchestrator.py` with two public functions: `run_rerank_orchestration(top_n_candidates, weather_ctx, conditions)` and `run_trip_plan_orchestration(candidate, weather_ctx, conditions)`. Both implement the 3-round pattern:

Round 1: parallel specialist calls (Weather, Timing, Species). Use ThreadPoolExecutor with 3 workers.
Round 2: parallel peer-review calls — each specialist gets its own R1 output + the other two specialists' R1 outputs.
Round 3: single coordinator call with all R2 outputs.

Handle failures gracefully: if any single specialist fails in R1, log and continue (coordinator gets nulls for that axis). If 2+ fail, abort and raise OrchestrationError. Return a structured result that includes the final coordinator output PLUS the per-round specialist outputs (for debugging/explanation purposes — the frontend can choose what to display).

Also create `backend/services/topn.py` with `select_top_n(candidates, mode='composite', n=30, max_n=50)` that takes the full filtered candidate list from the existing /candidates endpoint and returns the top N. Modes: 'composite' (current sorted order — the panel's default), 'f_score' (by F-score descending). Cap N at max_n.

Show me both files' structure before generating, including the OrchestrationError exception class and the result dict shape."

### Verify in the plan

- [x] ThreadPoolExecutor used cleanly (no thread leak risk)
- [x] Per-call timeouts enforced (don't let a slow agent block forever)
- [x] Graceful degradation: 1 specialist failure → continue; 2+ → abort
- [x] Result includes both final output AND per-round intermediates (debugging gold)
- [x] Top-N selection respects mode and cap
- [x] Orchestrator is pure: takes candidates + context, returns result. No DB access (orchestrator gets candidates from caller, doesn't fetch them)

### Verification

```bash
# Mock test — call orchestrator with hardcoded candidate list and conditions
python -c "
import sys; sys.path.insert(0, '.')
from services.orchestrator import run_rerank_orchestration
from services.weather import get_weather_context
from services.conditions import get_all_conditions

candidates = [...]  # 5 hardcoded test candidates with full Phase 2 score shape
weather = get_weather_context(43.77, -79.26)
conditions = get_all_conditions()
result = run_rerank_orchestration(candidates, weather, conditions)
import json; print(json.dumps(result, indent=2))
"
```

Expected: orchestrator runs the 3 rounds, returns a final ranking with per-candidate rationales. ~15-30 seconds wall time.

### Definition of done

- 3-round pattern works end-to-end
- Parallel specialist calls actually run in parallel (verify with timing)
- Peer-review round produces revised outputs
- Coordinator synthesizes final ranking
- Failure modes handled (1 specialist fail = degraded but works; 2 fail = aborts cleanly)

### Branch: `phase-5/05-orchestrator`

---

## Part 6 — Backend endpoints: /agents/rerank and /agents/trip-plan (2-3 hours)

### Context

Two new FastAPI endpoints expose the orchestrator. They accept top-N candidates (or candidate ID for trip-plan), gather context, run the orchestrator, return structured results.

### Files to modify

- `backend/api/main.py` — add two new endpoints

### Decisions to lock

- `POST /agents/rerank` accepts JSON body: `{candidate_ids: list[int], near_lat: float, near_lon: float, top_n_mode: 'composite' | 'f_score', top_n: int}`
- Endpoint fetches the candidates from DB by ID, sorts/selects top-N per mode, gathers weather + conditions, runs orchestrator, returns structured response
- `POST /agents/trip-plan` accepts JSON body: `{candidate_id: int, near_lat: float, near_lon: float}` — operates on a single candidate
- Both endpoints validate the lat/lon (Ontario bbox) and verify candidates exist (`is_active = TRUE`)
- Failures: orchestrator errors return 503 with detail; missing candidate returns 404
- Response includes a `request_id` (UUID) for debugging (log it server-side)

### Pydantic models

```python
class RerankRequest(BaseModel):
    candidate_ids: list[int]
    near_lat: float = Field(ge=41.0, le=50.0)
    near_lon: float = Field(ge=-85.0, le=-74.0)
    top_n_mode: Literal['composite', 'f_score'] = 'composite'
    top_n: int = Field(default=30, ge=5, le=50)

class RerankedCandidate(BaseModel):
    candidate_id: int
    new_rank: int
    one_line_why: str
    specialist_agreement: Literal['high', 'medium', 'low']

class RerankResponse(BaseModel):
    request_id: str
    ranked_candidates: list[RerankedCandidate]
    conditions_summary: str  # one-line summary of current conditions
    specialist_metadata: dict | None = None  # per-round outputs for debug; can be hidden in prod

class TripPlanRequest(BaseModel):
    candidate_id: int
    near_lat: float = Field(ge=41.0, le=50.0)
    near_lon: float = Field(ge=-85.0, le=-74.0)

class TripPlanResponse(BaseModel):
    request_id: str
    candidate_id: int
    overall_call: Literal['go now', 'good window coming', 'wait', 'skip']
    best_window: str
    expected_species: list[dict]  # [{species: str, activity_note: str}]
    conditions_summary: str
    things_to_watch: list[str]
    key_risks: list[str]
    confidence: Literal['high', 'medium', 'low']
    specialist_metadata: dict | None = None
```

### Plan Mode prompt

**Plan Mode prompt**: "Add `POST /agents/rerank` and `POST /agents/trip-plan` to `backend/api/main.py`. Both use the Pydantic models in the design doc. Algorithm for rerank:

1. Validate request (Pydantic handles this)
2. Fetch candidates by ID from DB (verify `is_active = TRUE`)
3. Apply top-N selection via `services.topn.select_top_n`
4. Fetch weather context via `get_weather_context(near_lat, near_lon)`
5. Get conditions via `get_all_conditions()`
6. Run orchestrator via `run_rerank_orchestration`
7. Format response per RerankResponse model
8. Log request_id, total time, token usage if available

Trip-plan is similar but operates on single candidate. Failure handling: 404 if candidate doesn't exist, 503 if orchestrator raises OrchestrationError, 503 if weather fetch fails. Show me the handler shape and the DB queries before generating."

### Verify in the plan

- [ ] Cross-param validation: candidate_ids non-empty, lat/lon both in Ontario range
- [ ] DB query verifies all requested IDs exist and are active (single query, not per-ID)
- [ ] Orchestrator is called AFTER all 422-checks (no wasted API calls)
- [ ] Response includes request_id for debugging
- [ ] `specialist_metadata` is opt-in via query param `?debug=true` (default off — production response is clean)
- [ ] Logging captures request_id, candidate count, total time, success/failure

### Verification

```bash
# Test rerank
curl -X POST http://localhost:8000/agents/rerank \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_ids": [1, 2, 3, 4, 5],
    "near_lat": 43.77,
    "near_lon": -79.26,
    "top_n_mode": "composite",
    "top_n": 30
  }'

# Test trip-plan
curl -X POST http://localhost:8000/agents/trip-plan \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": 1,
    "near_lat": 43.77,
    "near_lon": -79.26
  }'

# Test 404
curl -X POST http://localhost:8000/agents/trip-plan \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": 99999,
    "near_lat": 43.77,
    "near_lon": -79.26
  }'
# Expect 404
```

### Definition of done

- Both endpoints return valid structured responses
- 404 on missing candidate
- 422 on out-of-range lat/lon
- 503 on orchestrator failure (test by setting bad ANTHROPIC_API_KEY)
- Response time matches orchestrator expectations (~15-30s for re-rank, faster for trip-plan)

### Branch: `phase-5/06-api-endpoints`

---

## Part 7 — Frontend: "Get AI take" and "Plan this trip" buttons (3-4 hours)

### Context

Two new UI surfaces:
1. "Get AI take" button in the panel header — fires `/agents/rerank` on top-N currently visible
2. "Plan this trip" button in each candidate's detail card — fires `/agents/trip-plan` for that candidate

Both have loading states (~15-30s), error handling, result display.

### Files to modify

- `frontend/components/panel/CandidatePanel.tsx` — add "Get AI take" button to header
- `frontend/components/panel/CandidateDetail.tsx` — add "Plan this trip" button
- `frontend/lib/types.ts` — add types for both responses
- `frontend/app/page.tsx` — wire up state and fetch logic
- New: `frontend/components/panel/AiRerankResult.tsx` — display for re-rank results
- New: `frontend/components/panel/TripPlanResult.tsx` — display for trip-plan results

### Decisions to lock

- Both buttons disabled when no location is set (need near_lat/near_lon for weather)
- Loading state shows a clear spinner with "Reasoning..." text — set expectation that this takes 15-30 seconds
- Re-rank result: replaces the regular candidate list view temporarily with the re-ranked view. A "Back to default ranking" button returns to normal.
- Trip-plan result: replaces the detail card content with the structured trip plan. A "Back to scores" button returns to the standard detail view.
- Errors display in-place with a "Retry" button
- Results persist until user navigates away or explicitly dismisses

### Plan Mode prompt

**Plan Mode prompt**: "Update `frontend/components/panel/CandidatePanel.tsx` to add a 'Get AI take' button in the panel header (next to the FMZ selector). Button is disabled when `nearLocation` is null (with a tooltip 'Set a location to enable AI re-ranking'). Click handler fetches `POST /agents/rerank` with the current top-N candidate IDs and `near_lat`/`near_lon`. Loading state shows a spinner with 'Reasoning...' text. On success, the result replaces the candidate list view with a new `<AiRerankResult>` component. A 'Back to default ranking' button returns to the standard view.

Similarly, add 'Plan this trip' button in `CandidateDetail.tsx`. Click fetches `POST /agents/trip-plan` for the selected candidate. Loading state similar. On success, the structured fields replace the standard scores display (via `<TripPlanResult>` component).

Create `frontend/components/panel/AiRerankResult.tsx` and `frontend/components/panel/TripPlanResult.tsx` as new components. Both should match the existing visual style (serif typography for content, sans for chrome, generous spacing).

Add types to `lib/types.ts` matching the backend RerankResponse and TripPlanResponse. Wire state in `page.tsx`: `rerankResult` and `tripPlanResult` state, fetch functions, error state. Use AbortController for both fetches so navigating away cancels in-flight requests.

Show me the component shapes, state flow, and visual mockup (text-based) before generating."

### Verify in the plan

- [ ] Buttons disabled when location is null
- [ ] Loading spinner clearly indicates wait time (~15-30s isn't snappy)
- [ ] Errors displayed in-place, retry option
- [ ] AbortController cancels in-flight fetches on navigation
- [ ] Re-rank result is a *temporary* view, not a permanent replacement (user can go back)
- [ ] Trip-plan result preserves the detail card structure (header stays, body changes)
- [ ] Visual style matches existing panel (serif body, sans chrome)

### Verification

1. `npm run build` passes
2. Set location → buttons enable
3. Click "Get AI take" → spinner appears → 15-30s later, re-ranked list displays
4. Click "Back to default ranking" → returns to normal view
5. Open candidate detail → click "Plan this trip" → structured trip plan displays
6. Click "Back to scores" → standard detail card returns
7. Click button, navigate away during fetch → no orphaned requests, no console errors
8. With ANTHROPIC_API_KEY unset → 503 → friendly error displayed in panel

### Definition of done

- Both buttons work end-to-end
- Loading and error states display correctly
- Result components match visual style
- Build is clean

### Branch: `phase-5/07-frontend-buttons`

---

## Part 8 — Integration smoke test (1-2 hours)

### Context

Walk every UI path with the multi-agent layer active. Same shape as Phase 2 and 3 smoke tests.

### Test list

- [ ] Cold start: API up, frontend up, no errors
- [ ] Existing Phase 2/3 features all work (drive-time filter, candidate detail, etc.)
- [ ] Without location set: AI buttons disabled with tooltip
- [ ] Set location → buttons enable
- [ ] Click "Get AI take" with default top-N → spinner → ranked list displays in 15-30s
- [ ] Top-N mode toggle (composite vs F-score) produces different rankings
- [ ] "Back to default ranking" returns to normal view
- [ ] Click "Plan this trip" on a candidate → trip plan displays
- [ ] Specialist metadata available in debug mode (`?debug=true` query param)
- [ ] Error case: stop the Anthropic API (bad key) → friendly 503 in UI
- [ ] Error case: stop Open-Meteo network → friendly error
- [ ] Multiple rapid clicks on "Get AI take" → only one in-flight request (debounced)
- [ ] No console errors, no server tracebacks
- [ ] Cost log shows reasonable token usage per call

### Performance smoke

- [ ] Re-rank end-to-end: 15-30 seconds
- [ ] Trip-plan end-to-end: 10-15 seconds
- [ ] Subsequent calls hit weather cache (faster)

### Definition of done

- All checkboxes pass
- Any "almost" or "weird" finding documented in CLAUDE.md as known issue

---

## Part 9 — Reflection and commit (45-60 min)

### Document

- [ ] Update `README.md` with Phase 5 multi-agent capabilities
- [ ] Update `CLAUDE.md` with the multi-agent architecture decisions (3-round pattern, critique-then-revise, top-N cap)
- [ ] Create `docs/phase_5_reflection.md` with:
  - What worked smoothly?
  - What took longer than expected?
  - How well did the peer-review round actually work? (Look at `what_changed_from_round_1` outputs — are specialists meaningfully revising, or rubber-stamping?)
  - How does the cost actually compare to estimates?
  - Which agent feels most useful? Least?
  - Are the prompts in the right place, or do they need restructuring?
  - What surprised you about multi-agent reasoning vs single-call?
  - What would Phase 7 do differently?
  - Looking at Phase 4 trip data: did the AI take match reality, or was it confidently wrong?

### Commit and tag

- [ ] `git add -A && git commit -m "Phase 5: multi-agent reasoning layer"`
- [ ] Push to GitHub
- [ ] Tag: `git tag phase-5-complete && git push --tags`

---

## Done criteria

You're done with Phase 5 when:
- [ ] Both endpoints work end-to-end
- [ ] 3-round multi-agent pattern verified (specialists run parallel, peer-review happens, coordinator synthesizes)
- [ ] Cost stays within estimates (~$0.57 per re-rank, ~$0.08 per trip-plan)
- [ ] Frontend buttons work cleanly with loading and error states
- [ ] Top-N cap enforced (never more than 50 candidates to agents)
- [ ] Existing Phase 2/3 functionality intact
- [ ] Smoke test passes
- [ ] Repo committed, tagged, documented

You do **not** need to:
- Have agents that use tools (Phase 7+)
- Have agent learning from trip outcomes (Phase 6 calibration)
- Have more than 3 specialist axes (Phase 7+)
- Have direct agent-to-agent communication (locked: coordinator-routed only)
- Have water temperature sensors, moon phase, solunar (out of scope)
- Have prompt versioning beyond git (database-backed prompts are Phase 8+)

---

## If you get stuck

**JSON parsing failures from agents**: Claude occasionally produces malformed JSON despite explicit instructions. The retry logic in `call_claude` handles single failures. If a specific prompt produces malformed JSON consistently, tighten the system prompt's JSON-only instruction and add a concrete example of the expected output structure.

**Specialist outputs feel generic / aren't reasoning about specific candidates**: The prompt is too high-level. Include concrete candidate data in the user message (not just IDs and scores — actual species names, water type, surrounding context). Specialists need specifics to reason about specifics.

**Peer-review round produces no revisions ("specialists agree on everything")**: Either the prompts are pushing too hard toward consensus, or the candidates are easy cases. Try a re-rank on a deliberately mixed set (a high-H low-A candidate vs a low-H high-A candidate) — specialists should produce different views and peer review should surface the tension.

**Cost is higher than estimated**: Check token usage logs. Specialist input is the biggest variable — if you're sending too much candidate metadata, trim. The agents don't need every column; they need scores, name, type, species. Trim verbose fields.

**Latency is over 60s**: ThreadPoolExecutor parallelization isn't working as expected, or one specialist is consistently slow. Check the per-round timing in logs. If a specialist is slow, profile its prompt — it might be doing too much in one call.

**Multi-agent system feels like theater (not real reasoning)**: Review the `what_changed_from_round_1` outputs. If specialists rarely revise, the peer-review round isn't earning its keep. Tighten the critique prompt (require specific weaknesses to be identified, not generic acknowledgment).

**You feel mid-phase scope creep**: The "do not need to" list above is the boundary. Revisit it monthly.

---

## After Phase 5

Bring back to the next conversation:
- Your `phase_5_reflection.md` notes
- Screenshots of: re-rank result display, trip-plan result display, loading states, error states
- 3-5 sample re-rank outputs with the specialist metadata visible — so you can review whether the peer-review round produced meaningful changes
- 1-2 sample trip-plans for candidates you'd actually go visit on a Phase 4 trip
- Cost data from a week of typical use
- Any architectural decisions you're uncertain about
- Honest assessment: does the AI layer feel like it's adding real value, or is it AI for AI's sake? If specific axes aren't earning their keep, that's a Phase 7 signal to either improve them or remove them.

Then we plan Phase 6: weight calibration from accumulated Phase 4 trip data, plus revisiting the H-score "named-pond at 80%" issue, plus deciding whether walk-time can finally be addressed via re-ingested trail data.
