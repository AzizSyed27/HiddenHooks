# Phase 2 Reflection

Coverage: FMZ 16 and FMZ 17.
Scoring: Hiddenness (H), Accessibility (A), Fish potential (F), Ecology bonus (E).
Date completed: 2026-05-08.

---

## What worked smoothly?

_Your notes here._

**What Claude Code observed:**

The API rewrite was the smoothest major piece. The CTE pipeline — `scored → total → ranked`
— composed exactly right on the first attempt. `RANK() OVER (PARTITION BY fmz_zone)` and
`COUNT(*) OVER (PARTITION BY fmz_zone)` in the same window pass, with `COUNT(*) AS n FROM scored`
cross-joined for `total_count`, meant three things that could have required three separate
queries were handled in one pass. The `{fmz_filter}` / `{radius_filter}` Python-format
approach (hardcoded fragments, not nullable params) avoided the PostgreSQL null-comparison
ambiguity that a `:param IS NULL OR col = :param` pattern would have introduced.

The TypeScript build passed with zero errors after each code generation round. Five
files changed for the radius filter UI (types, page, panel, detail, LocationFilter) and
the build was clean on the first attempt. The explicitness of the `fetchCandidates`
parameter signature — passing all four state values as arguments rather than closing over
them — made the stale-closure problem easy to reason about across all call sites.

Plan mode caught several design decisions before code was written: the shared `debounceRef`,
the no-fitBounds-in-handler rule (letting `useEffect([candidates, mapReady])` own
positioning), the active-pill no-op. Each of those came out of pushback during plan review,
not from fixing broken code after the fact.

---

## What took longer than expected, and why?

_Your notes here._

**What Claude Code observed:**

The radius filter UI plan went through five rounds of revision before the user approved it.
The core issue was figuring out which fitBounds calls belonged where. The first draft had
fitBounds in `handleLocationChange` and `handleRadiusChange` zooming to the radius circle
before the fetch completed — which would race with the candidates-useEffect fitBounds
that fires after. The correct rule (handlers don't fitBounds; only handleFmzChange and
handleRadiusClear do, and handleFmzChange only when no radius is active) emerged from
the user's pushback across three successive ExitPlanMode rejections. Once the rule was
clear, removing `getRadiusBbox` entirely was an obvious consequence — it had no remaining
callers.

The `dist_to_road.py` bug — filtering on `candidate_type IN ('polygon', 'reach_full')`
instead of `is_active = TRUE` — excluded all `reach_segment` candidates from the hiddenness
score. It was invisible during Phase 1 (there were no reach_segments then) and only surfaced
in Phase 2 after segmentation ran. The fix was one line, but catching it required reading
the WHERE clause carefully against the new data model. Stale SQL predicates are the kind of
thing that looks correct on inspection because the logic is right for the old schema.

---

## What surprised you about the data, the tooling, or the process?

_Your notes here._

**What Claude Code observed:**

The isolated-node crash in `score_fish_potential.py` was genuinely surprising.
`G.add_edges_from()` only adds nodes that appear in at least one edge — a node with no
edges is silently absent from the graph. ARA-anchored candidates with no rows in
`candidate_edges` were present in `ara_map` but absent from `G`, so `G.neighbors()` would
raise `KeyError`. The fix was `G.add_nodes_from(ara_map.keys())` before the BFS loop — one
line, but the failure mode (crashing only on isolated candidates, silently passing on all
others) was the kind of bug that could have appeared to work on a sample and failed on the
full dataset.

---

## What architectural decisions are you uncertain about?

_Your notes here._

**What Claude Code flags as open questions:**

**Per-region vs. global composite normalization.** Scores are normalised within each FMZ
independently. This means rank 1 in FMZ 17 and rank 1 in FMZ 16 are not comparable — a
top FMZ 17 candidate might have a lower absolute composite than a mid-tier FMZ 16 candidate.
Whether this is the right choice depends on whether the regions have similar candidate
quality distributions. If FMZ 17 candidates are systematically weaker (sparser ARA data,
fewer trail connections), per-region normalization flatters FMZ 17 — the denominator
shrinks. Worth checking.

**COALESCE(w * score, 0) for partial pipeline state.** Treating a missing component score
as zero is safe during development but has a real effect: candidates where F-scoring
hasn't run yet will rank as if they have zero fish potential, suppressing them unfairly
relative to candidates that have been scored. If the pipeline is ever run incrementally
(some components scored, others not), this could produce misleading rankings without any
warning. An alternative would be to exclude candidates with NULL component scores from
composite computation — but that changes what "rank" means depending on which scripts
have run.

**Cross-region graph for ecology.** The connectivity graph spans both FMZs. A candidate's
ecology bonus can be influenced by connected reaches in the other region. This is
ecologically correct but makes the E-score hard to reason about in isolation — "why did
this FMZ 16 pond get an ecology bonus?" could have an answer that involves FMZ 17 topology.

**Nominatim address search with no User-Agent control.** The browser restricts `User-Agent`
as a forbidden header — the browser's own UA is sent, not an app-specific one. For personal
low-volume use this is within Nominatim's ToS, but it's a gotcha if the app ever scales.

---

## Looking at top-ranked candidates within FMZ 16: do they look defensible? How about in FMZ 17?

_Your notes here. Things to check: are the top candidates in plausible locations (deep
forest, far from settlement, near known productive water)? Or are they scoring high for
the wrong reasons (e.g., polygon with no road access simply because it's a farm pond in an
area with few roads)? Are the high-H + high-F candidates the most interesting, or are
high-H + low-F candidates surfacing things that might be overlooked for good reason?_

---

## How different are the two regions in terms of confidence distribution? Did F-scoring degrade gracefully on the data-sparse side?

_Your notes here. Things to check: what fraction of each FMZ's candidates are strong /
plausible / speculative? If one FMZ has dramatically more speculative candidates, is that
because the ARA data is sparse there, or because the connectivity graph didn't propagate
well? Did speculative-confidence candidates end up ranked high enough to be annoying, or
did the F-weight keep them below the threshold of notice?_

---

## Did adding FMZ 17 in Phase 2 (rather than waiting) feel worth it? Specifically: did cross-region graph inference help any FMZ 16 candidates? How many?

_Your notes here. Things to check: run a query like `SELECT COUNT(*) FROM candidates WHERE
fmz_zone = 'FMZ16' AND f_confidence IS NOT NULL AND f_score > 0` before and after the
cross-region graph was built — if the number changed, the cross-region inference helped
those candidates. Alternatively, look for FMZ 16 candidates whose nearest ARA anchor is
in FMZ 17 (i.e., BFS crossed the boundary). The value of adding FMZ 17 depends partly on
whether this happened often enough to matter._

---

## Which of the four components is doing the most work in the rankings? Which feels weakest?

_Your notes here. One approach: run the API with weights skewed heavily toward one
component at a time (e.g., w_h=1, w_a=0, w_f=0, w_e=0) and see how much the top-10 list
changes. If the ranking barely changes when you zero out a component, that component is
either redundant with another or has low variance across candidates. A weak component is
one where most candidates cluster near the same score — it adds noise to the composite
without differentiating anything._

---

## Was per-region H normalization the right call, or did it make scores feel weird?

_Your notes here. Specifically: did candidates in the "easier" region (whichever has more
roads, more development) end up with H scores that feel inflated compared to the other
region? H is normalised so the most hidden candidate in each FMZ gets H=1.0 — but if FMZ
16 has candidates 12 km from the nearest road and FMZ 17's furthest is 3 km, the FMZ 17
1.0 doesn't mean the same thing. Does that bother you in practice, or does it feel right
because you're not comparing across regions anyway?_

---

## Is the species_values weighting producing the rankings you wanted, or do you need to revisit the weights?

_Your notes here. The species_values dict in score_fish_potential.py assigns relative value
to different species — the exact weights drive which candidates surface as high-F even when
ARA coverage is thin. If trout-potential candidates are scoring lower than you expected, or
if a species you care less about is dominating the top-F slots, the weights need revisiting.
Worth exporting the top-20 by F-score and checking what species is attached to each._

---

## What did you learn about Claude Code's working pattern on a multi-workstream, multi-region phase?

_Your notes here._

**What Claude Code observed:**

The plan-mode revision loop was more useful for UI than for backend. Backend changes (the
API rewrite, the scoring scripts) had clear input/output specs and the plans converged in
one or two rounds. The LocationFilter UI plan went through five rounds because the design
choices — which handler owns fitBounds, when the radius pill is a no-op, whether to share
debounceRef — each had interaction effects that weren't obvious until articulated. Planning
a stateful UI component is harder than planning a SQL query.

Context compaction changed the dynamic. By late Phase 2 the session had run long enough
that earlier decisions were no longer in the active context. CLAUDE.md and the plan file
were the continuity mechanism — decisions that were documented there survived compaction;
ones that weren't had to be re-derived. The `is_active = TRUE` convention being in CLAUDE.md
meant it didn't get silently dropped when the dist_to_road WHERE clause was revisited.

The user's pushback discipline was valuable. Several of the best architectural decisions in
this phase came from the user saying "that's wrong, here's why" rather than accepting the
first plan. The fitBounds race condition, the active-pill no-op, the single shared
debounceRef — all emerged from pushback, not from the initial draft.

---

## What's one thing you'd do differently starting Phase 2 over?

_Your notes here._

**What Claude Code would change:**

Run `npm run build` after every individual component change, not after all components are
written. In this phase five files were written before the build ran. Any TypeScript error
in file three would have required re-reading the state of files one, two, four, and five
to understand the conflict. The build took 12 seconds — the cost of running it five times
is a minute; the cost of debugging a type conflict across five simultaneously-changed files
is much longer. The same principle applies to the Python scripts: running each scoring
script on a small test candidate set immediately after writing it, before the next script
is written, catches isolation bugs (like the missing `G.add_nodes_from`) before they
compound with the next script's assumptions.
