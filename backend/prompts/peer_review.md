# Round 2 — Peer Review and Revision

You have completed Round 1 analysis. Two peer specialists have analyzed the same candidates
from their perspectives. Their Round 1 outputs appear below alongside yours.

The peer agents are identified by name in the input (e.g., "weather_agent", "timing_agent",
"species_agent"). Use these exact names as keys in your critique output.

Your task has two parts, in order:

**Part 1 — Critique**
Each specialist scores a different dimension (weather favorability, timing favorability,
species activity). A score gap between you and a peer does not by itself indicate
disagreement — you are measuring different things. What matters is whether a peer's
analysis of their dimension reveals something that should shift YOUR analysis of your dimension.

For each candidate where your score and a peer's score diverge by more than 0.30,
assess: does the peer's reasoning for THEIR score reveal a signal you should have weighted
in YOUR score? Focus on the top 5 most-divergent candidate-peer pairs.

Example: if the timing agent gives a candidate a low timing_score (midday Saturday), ask
whether the poor timing window should have caused you to lower your weather score —
since good weather conditions during a dead window are less actionable than during a
prime window. If yes, revise. If your weather score reflects conditions regardless of
window, hold your position and say why.

A substantive critique names:
- The candidate_id
- Your score and the peer's score
- The specific signal in THEIR domain that should (or should not) affect YOUR domain
- Why you hold or revise your position

Do not critique style or phrasing. Engage with the cross-dimensional substance.

**Part 2 — Revision**
Revise your own position based on peer reasoning. You must:
- Consider each peer critique seriously before accepting or rejecting it
- Revise your score where a peer argument is genuinely compelling
- Hold your original position where it is not — and explain why explicitly

## Output

> **IMPORTANT**: The output schema below REPLACES the output schema from your specialist
> prompt above. Do not return the specialist's normal output format in this round —
> return the peer-review schema only.

Return ONLY a JSON code block. No text before or after.

```json
{
  "critique_of_peers": {
    "weather_agent": [
      {
        "candidate_id": 456,
        "my_score": 0.72,
        "their_score": 0.35,
        "spread": 0.37,
        "my_read": "Their low timing score (midday Saturday) correctly signals a dead window — good weather during a dead window is less actionable, so I'm revising my weather score down slightly.",
        "their_apparent_gap": "The weather signal is genuinely strong; timing limits its value but doesn't negate it entirely for a remote lake with low pressure."
      }
    ],
    "species_agent": []
  },
  "my_revised_position": [],
  "what_changed_from_round_1": [
    {
      "candidate_id": 123,
      "field": "weather_score",
      "old_value": 0.60,
      "new_value": 0.72,
      "reason": "Timing agent correctly flagged the post-rain clearing signal I had weighted too conservatively."
    }
  ]
}
```

Rules:
- critique_of_peers: keyed by peer agent names exactly as provided in the input.
  Each value is a list; empty list `[]` if no candidates exceed the 0.30 threshold
  for that peer. An empty list is a valid "no significant cross-dimensional impact"
  signal — the orchestrator treats it as such, not as an error.
- Each critique entry: candidate_id (int), my_score, their_score, spread (two decimal
  places), my_read (one sentence), their_apparent_gap (one sentence naming the specific
  cross-dimensional signal).
- my_revised_position: complete array in your Round 1 output schema. All candidates.
  The orchestrator replaces your Round 1 output entirely with this array.
- what_changed_from_round_1: changed fields only. Empty array if all positions held.
