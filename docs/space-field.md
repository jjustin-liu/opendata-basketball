# Exploitable-space field

A port of the probabilistic control field from Luke Blommesteyn's
[Holes in the Defense](https://github.com/lblommesteyn/opendata-basketball/tree/main/analysis)
study of the same SkillCorner release, adapted to this repo's replay data and
evaluated against our own EPV models. Code: `epv/space.py` (field),
`epv/space_field.py` (per-game build and exports), `epv/space_eval.py`
(leave-one-game-out evaluation), `epv/action_values.py` (event-aligned deltas).

## Definition

For every 1 ft cell `q` of the offensive half court and every player, the arrival
time is a reaction delay of 0.2 s at the current velocity, then bang-bang
acceleration (16 ft/s²) toward `q` capped at 20 ft/s; a player moving away must
first stop. Constants come from the 99th/99.9th percentiles of detected 25 Hz
tracking (`scripts/fit_movement_constants.py`, `artifacts/movement-constants.json`).
Arrival times are Gaussian with variance `0.15² + (predError / 2.146 / 10)² +
(0.1·t)²`, inflated by 1.5 when the position is extrapolated. Each team's first
arrival is the Clark (1961) moment-matched minimum of its five normals, and
control is `C = Φ((μ_def − μ_off) / √(σ_off² + σ_def²))`. On real frames the
approximation is within 0.02 of a 300-draw Monte Carlo of the same model.

The field is `H = C × V`, where `V` is the open-shot value map: points per
open or lightly contested shot from the other nine games, kernel-smoothed
(4 ft) within the same 2/3-point zone, mirrored across the court axis and shrunk
toward a parametric prior (rim 1.35 → 0.85 at 15 ft, three 1.05 → 0.35 at 35 ft)
with a prior weight of six shots. Every cell is populated. The scalar
`A = Σ max(0, H − 0.5)` (point·ft²) is split into `space_occ` (cells within 5 ft
of an attacker) and `space_hole` (empty valuable space), plus rim, three, corner
and paint components, connected-component count and largest region.

Differences from the original: velocities are causal (previous replay sample
only, ≤ 0.4 s apart), never centred differences; the grid is 1 ft at 5 Hz; the
value map has a parametric prior so no cell is missing.

## Outputs

- `viewer/data/space-value.json`: per-game leave-one-game-out value grids
  (integer cell corners, `[x, y, points]`), consumed by the valuable-space overlay
  and the movement search. Replaces `scripts/build_space_value.py`.
- `viewer/data/plays/*.json`: `frame.space = {a, hole, occ}` on ten-player frames.
- `viewer/data/holes/{gameId}.json`: empty valuable regions per play and frame
  (`[cx, cy, mass, cells]`, at least six cells), used as movement candidates.
- `.cache/epv/space-{gameId}-{hash}.joblib`: per-frame summaries for analysis.
- `artifacts/space-validation.json`, `artifacts/action-values.json`,
  `docs/action-values.md`.

## Does it improve our models?

`epv.space_eval` adds the thirteen field summaries to the EPV feature sets and
refits the same HistGradientBoosting estimator, weights and leave-one-game-out
split as the main build (39,664 training states). Lower is better.

| target | geometry | geometry + space | games improved |
|---|---|---|---|
| points (RMSE) | 1.1749 | 1.1747 | 7/10 |
| turnover2 (log loss) | 0.1270 | 0.1276 | 6/10 |
| turnover_rest (log loss) | 0.4411 | 0.4406 | 8/10 |
| shot in next 3 s (log loss) | 0.3683 | 0.3645 | 10/10 |
| open shot in next 3 s | 0.2258 | 0.2212 | 8/10 |
| rim shot in next 3 s | 0.2059 | 0.2007 | 10/10 |
| paint touch in next 3 s | 0.3868 | 0.3838 | 7/10 |
| assist opportunity in next 3 s | 0.3718 | 0.3678 | 9/10 |

Space-only models (clock and location plus the field) are worse than geometry on
every target. Conclusion: the field carries no additional information about
possession points or turnovers beyond our handler-centred geometry, so the EPV
models are unchanged. It does add small, consistent information about what
happens in the next three seconds, which is where it is used: event-aligned
action values, hole candidates for the movement search, and the viewer overlay.

## Event-aligned action values

`docs/action-values.md` reports, for every tagged action, the change in `A`, in
its hole and occupied parts, and in our EPV and two-second turnover risk from the
second before the anchor frame to the 1.5 s after, against a null of random
no-action frames. Picks and drives open the most space (about +48 and +40
point·ft² above the null, p ≪ 0.001), off-ball screens a little, handoffs and
isolations none; passes and closeouts reduce it. Coverage splits (pick and screen
coverage, closeout action, pass length) are in the same report. The robustness
section recomputes the deltas with positions jittered by the SkillCorner error
bound and with the motion constants varied by ±20–30 %: per-event deltas
correlate at 0.97–0.997 with the baseline and keep their sign in 94–99 % of
events, so the action ranking does not depend on the exact constants.

## Rebuild and tests

```sh
.venv/bin/python -m epv.space_field
.venv/bin/python -m epv.space_eval
.venv/bin/python -m epv.action_values --perturb
.venv/bin/python -m unittest tests.test_space
node --test tests/space-control.test.js
```

`epv.build` runs `space_field` and `action_values` after the model build; the
evaluation and the perturbation study are run on demand.
