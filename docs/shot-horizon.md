# Projected shoot-now value at t+delta

Implemented in `epv/shot_horizon.py`; regenerate with
`.venv/bin/python -m epv.shot_horizon --validate` after the main EPV build and
`epv.vendor_surrogate`. Held-out metrics land in
`artifacts/shot-horizon-validation.json`; per-frame forecasts are written into the
replay JSON as `shotHorizon`. This adds a forecast beside the existing SHOT card
and changes no existing model.

## The problem it addresses

The per-frame SHOT number is a freeze-frame conditional: release from this exact
state. Along a drive that conditional collapses while the possession is improving.
One worked example, `possession-114086-1-22` (Q1 4:14, Spagnolo):

| rim ft | nearest def ft | speed ft/s | region | SHOT | EPV |
|---:|---:|---:|---|---:|---:|
| 24.0 | 9.9 | 6.9 | three | 1.33 | 1.18 |
| 22.3 | 7.2 | 9.9 | three | 1.30 | 1.18 |
| 19.9 | 4.6 | 12.8 | two | 0.91 | 1.04 |
| 17.2 | 2.9 | 14.3 | two | 0.92 | 1.08 |
| 7.8 | 2.9 | 16.2 | rim | 1.10 | 1.35 |
| 4.7 | 3.3 | 15.9 | rim | 1.40 | 1.39 |

The release itself scored 1.87. Make probability barely moves across the cliff
(0.363 to 0.332); what changes is `pointsIfMade`, 3 to 2. The holder is charged
for leaving the arc before he is paid for arriving at the rim. EPV dips with it,
so this is not only a display artifact. During those frames the card also reads
PASS 1.28 against SHOT 0.91, advising against a drive that produced a layup.

The realised 1.87 is **not** directly comparable to the frame numbers: the shot
event is scored with SkillCorner vendor quality, the per-frame card with the
geometry surrogate. The timing effect is the 1.33 to 0.91 to 1.40 arc.

## Method

1. Velocity is the mean over the trailing 0.4 seconds of tracking, previous
   samples only, broken across period changes and gaps over 10 ticks.
2. The holder continues on that heading at capped speed and gathers at the rim
   rather than running through it. Other attackers carry their own momentum.
3. Defenders answer three ways: `hold`, `momentum` (own velocity, stopping at
   closest approach to the holder's projected spot) and `close` (the defender
   nearest that spot abandons his velocity, waits 0.2 seconds and then recovers
   at his cap; others carry momentum). This mirrors `epv/movement.py`.
4. The projected state is rescored with the same released-shot surrogate and the
   same field-goal rebound continuation used by the live card, so the projection
   and its target come from one estimator.
5. A least-squares layer maps the three responses **and the current shoot-now
   value** onto the observed later value, fitted on the other nine games. The
   raw physics is reported alongside as `rawMean`.
6. `discounted` multiplies by the existing next-two-second turnover probability
   at constant hazard, so a projection is not credited as if possession were
   certain.

Speed caps are shrunk 99th-percentile player speeds from the other nine games.
They are a guardrail against tracking spikes, not personalisation: measured p95
speed spans only 13.5 to 15.9 ft/s across 205 players and does not separate
guards from bigs. In the example above the guard's p95 (13.9) is indistinguishable
from the centre's (13.7). A live speed mismatch is carried by observed velocity,
not by the cap.

## Held-out validation

Target: the same estimator's shoot-now value at the observed later frame.
Baseline: persistence, carrying the current value forward. Rows require the same
handler, a supported later frame and no tracking gap. 57,666 comparisons.

| horizon | group | n | MAE | persistence MAE | skill | direction |
|---|---|---:|---:|---:|---:|---:|
| +0.4s | all | 25,290 | 0.087 | 0.113 | +0.235 | 0.72 |
| +0.4s | holder ≥10 ft/s | 8,072 | 0.098 | 0.155 | +0.371 | 0.78 |
| +0.8s | all | 18,671 | 0.123 | 0.161 | +0.237 | 0.73 |
| +0.8s | holder ≥10 ft/s | 5,615 | 0.135 | 0.198 | +0.318 | 0.77 |
| +1.2s | all | 13,705 | 0.136 | 0.182 | +0.254 | 0.74 |
| +1.2s | holder ≥10 ft/s | 3,690 | 0.144 | 0.211 | +0.315 | 0.78 |

Per-game skill is +0.20 to +0.31 on nine games; game 114243 is an outlier near
zero (-0.02, +0.03, +0.07).

**The ablation that matters.** Persistence is a calibration input, so most of the
skill above can be shrinkage toward the mean rather than momentum. Refitting with
persistence alone isolates it:

| horizon | calibrated MAE | shrinkage-only MAE | share of that error momentum removes |
|---|---:|---:|---:|
| +0.4s | 0.0866 | 0.1099 | 21.2% (26.7% on fast holders) |
| +0.8s | 0.1231 | 0.1337 | 7.9% |
| +1.2s | 0.1356 | 0.1386 | 2.2% |

**Momentum carries information to about 0.8 seconds and then stops.** The +1.2s
column is nearly all regression to the mean and should not be presented as a
statement about that possession.

Raw physics on its own is worse than persistence at every horizon (skill -0.25,
-0.17, -0.13) with a -0.12 bias: constant-heading projection is systematically
pessimistic. Within it, `close` is near chance (direction 0.55, bias -0.26) while
`hold` is nearly unbiased (direction 0.67) - over 0.4 to 1.2 seconds real
defenders behave far more like holding position than like a capped sprint at the
ball. The calibration gives `close` roughly zero weight.

Arc crossings remain the weak case: skill -0.15 at +0.4s with a +0.18 bias,
recovering to +0.22 by +1.2s. Timing the exact frame of a 3-to-2 transition is
harder than projecting a drive.

## Guardrails and scope

- No future replay sample enters a projection, and calibration for a game is
  fitted only on the other nine.
- Validation measures state projection only. Both sides use the same shooting
  model, so shooting-model error cancels and is not evidence for it.
- Rows require the possession to continue with the same handler, so metrics are
  conditional on continuation and exclude drives ending in a turnover.
- No fouls, free throws, route feasibility, adaptive help or defensive rotations.
  A projected state is not checked for realism beyond the surrogate's support and
  the 32 ft distance limit.
- Positive skill against persistence is not evidence that acting on the number
  improves possessions. It is a forecast of the same estimator's later reading.
- Tests in `tests/test_shot_horizon.py` cover causal velocity, non-mutation of
  replay frames, zero-velocity invariance, clock expiry, the rim gather, speed
  caps, the reaction delay, future-frame matching and calibration behaviour.

## Payload

Each supported frame with a shoot-now value gains:

```
shotHorizon: {source, holder, capFeetPerSecond, now, bestSeconds, bestDiscounted,
              points: [{seconds, pps, rawMean, lo, hi, closePps, distance,
                        defenderFeet, three, survival, discounted}]}
```

`pps` is calibrated; `lo`/`hi` are the raw response band; `bestSeconds` is the
horizon with the highest discounted value, with 0.0 meaning shoot now.
