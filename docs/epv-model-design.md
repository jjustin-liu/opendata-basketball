# EPV model inspired by The Shot That Exists

Research and local data inspection: September 12, 2026. This records the proposed design. The baseline model and viewer have since been implemented; see [the prototype documentation](epv-prototype.md) for the current scope and validation results. See [the literature review](epv-literature-review.md) for primary papers and implementation references.

## The question to build around

Estimate the expected remaining points from shooting now, passing to each feasible teammate, or retaining the ball to create, given the same pre-decision state. The central output should be the shooting-versus-continuation margin, accompanied by uncertainty and evidence that the alternatives are actually supported by the data.

I read the full article from the Databallr repository at `apps/web-legacy/src/content/the-shot-that-exists.json`; the `apps/web/src/content/` mirror was byte-identical. Resolve the checkout using the basketball workspace's `bin/ws path databallr`. The article's sections 1–4 establish the decision problem, sections 5–7 develop access and reliable creation, section 8 adds defensive adaptation, and section 9 specifies the desired model outputs.

The most useful research connection is Skinner's optimal-stopping formulation: the threshold for shooting depends on future opportunities and turnover risk. Its simplified opportunity process is a conceptual baseline, not a substitute for tracking-based state transitions. [Skinner, 2012](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0030776).

## What the article implies mathematically

Let `s` include the observed history needed to describe the current situation, including the clocks. Let `G_t` be all points the current offense scores **after time t** until the modeled possession ends, including earned free throws and offensive-rebound continuation.

Three quantities need separate names:

- `V_behavior(s) = E[G_t | s]`: expected return under the behavior represented in the training data.
- `Q_behavior(s,a)`: expected return if action `a` is taken now and subsequent play follows that behavior. An action-conditioned regression estimates an observational association; treating it as this intervention requires additional assumptions about confounding and coverage.
- `V_optimal(s) = max_a Q_optimal(s,a)`: optimal control, including optimal subsequent decisions. This is the interpretation of the article's maximum equation; it is not what ordinary outcome prediction automatically learns.

For the first decision comparison, use `Q_behavior` consistently across all candidates. Maximizing these values gives a one-step improvement relative to the continuation policy, not a globally optimal offense.

Define:

```
continuation_best(s) = max(Q_behavior(s, retain),
                           Q_behavior(s, pass_to_j) for supported feasible j)
shooting_margin(s) = Q_behavior(s, shoot) - continuation_best(s)
decision_gap(s,a) = Q_behavior(s,a) - max_b Q_behavior(s,b)
```

The decision gap is nonpositive by definition. A positive shooting margin favors shooting only within the modeled action set and uncertainty. Also report shooting versus the *usual mixture* of nonshooting actions: this differs from comparison with the best continuation.

Define `retain` precisely: retain control for a proposed short interval (initially 0.5 seconds, or until an earlier forced event), then re-evaluate. It must not mean "the entire remaining possession," which overlaps the pass and shot alternatives. A semi-Markov formulation can accommodate actions of different durations.

Use a coherent reward recursion:

```
Q(s,a) = E[r + I(offense continues) * V(s_next) | s, action a]
```

Here `r` is points scored before the next modeled decision. Mutually exclusive branches include made shots and and-ones, misses with defensive or offensive rebounds, shooting fouls, retained dead balls, and turnovers. Do not double-count free throws through both shot and foul labels. A missed shot does not automatically terminate the possession. Time costs enter through the next state and clocks; do not also subtract an arbitrary per-second penalty.

The article also discusses opponent transition scoring and changes to defensive strategy in later possessions. Those need broader horizons. Keep the initial target offensive points; a future net-points version must apply the same opponent-possession horizon to every action, and long-run defensive adaptation needs a policy/game model. Maximizing points also differs from maximizing late-game win probability.

## What is actually available here

The local event files were counted directly, before any quality filtering:

| Item | Count |
|---|---:|
| Games | 10 |
| Possessions | 1,564 |
| Chances | 2,055 |
| Chances marked usable | 1,911 |
| Shot events, including fouled misses | 1,459 |
| Passes | 4,786 |
| Touches | 6,662 |
| Turnovers | 248 |
| Free throws | 430 |

All ten tracking paths currently contain **133-byte Git LFS pointers**, not gzip data. Their declared objects total 360,725,256 bytes (about 361 MB). Downloading the LFS objects is a prerequisite for spatial training. No raw-coordinate quality audit was performed in this research pass. The event JSON and aggregate CSVs are present. Summing made field goals at their two/three-point values and made free throws by team reproduced the scores in `matches.json` for all 20 team-games; this verifies local score consistency, not every possession assignment or an independent official feed.

The [README](../README.md) describes 25 Hz tracking for these games and offensive aggregates covering 293 games. The aggregates add player-level context but do not supply the missing games' spatial transitions. Millions of correlated frames would still represent only 1,564 possession outcomes.

The [tracking dictionary](data_dictionary/tracking_data.md) describes extrapolated positions, `isDetected`, `predError`, missing ball/player objects during dead time, and clock fields. These are important model inputs and audit strata. Player height is fixed at zero; do not claim to observe body pose, balance, gaze, or shooting-pocket quality directly.

## Data preparation before fitting

1. Materialize tracking, normalize player aliases, align events by frame/wall clock, and orient every attack consistently. Use frame-specific players, since possession roster arrays can include substitutes.
2. Reconstruct offense-specific rewards from made `shots` and `free_throws`, retaining original team identities and reconciling to `matches.json`. Resolve special free throws and questionable possession boundaries explicitly. At an intermediate state, subtract points already scored; do not give every frame the full possession's points.
3. Preserve offensive rebounds as continuation under `possessionId`; `chanceId` is a finer unit. Keep a separate count of usable training possessions after filtering and joining.
4. Build decision observations from live, controlled-ball states, including ordinary retained-ball intervals. Training only immediately before observed shots or passes would select on the action being predicted. Start with a modest regular sampling rate plus event boundaries; avoid giving long possessions disproportionate weight accidentally.
5. Compute features from a trailing history only. Use causal smoothing for velocities. Record missingness and tracking uncertainty, and compare results across quality strata rather than silently treating extrapolated coordinates as exact.

See [known issues](KNOWN_ISSUES.md): `passes.toReceiverId` is the intercepting defender, not the intended teammate. Failed-pass destinations must remain unknown unless independently reconstructed. Self-passes and missing rebound links require audit rules rather than automatic acceptance.

## Features and leakage boundaries

Start with clocks, court location, ballhandler and teammate geometry, trailing velocities, defender approach, distance to the basket and rim protection, passing-lane geometry, elapsed touch time, past dribbles, and observed recent screens/drives. Add bonus/foul context only after a reliable as-of reconstruction. Use pooled skill estimates with strong shrinkage; ten games are too little for unconstrained player-by-action effects.

Many event fields summarize the future. At touch start, total `touchTime`, `numDribbles`, `endLoc`, `ledToShot`, and `outcomes` are unavailable. Likewise, final chance quality or a defender assigned using average distance over the entire touch may use later frames. Such fields may be labels or retrospective audit filters, but cannot silently become live-state predictors.

A shot-quality model using release geometry is useful for valuing *observed attempts*. Applying it to an earlier decision state requires accounting for the gather, release delay, defender response, and whether that attempt can be executed. `contestLevel` can include "blocked"; this outcome-bearing label must not enter a pre-shot make-probability model. Treat SkillCorner's `shotQuality` as an external comparison until its scale, inputs, and calibration are established, not as a probability merely because it ranges from 0 to 100.

Season aggregates include these sample games and later games. The clean baseline should omit them. An exploratory model may use season context with an explicit retrospective label. For honest held-out or chronological prediction, use prior-only data or remove held-out contributions from compatible sufficient statistics; never assume all aggregate fields can be safely decontaminated.

## Recommended build order

**Stage 1: data and a descriptive EPV baseline.** Create the reward/decision table and a pooled, regularized predictor of remaining points using state features. Compare against constant and clock/location baselines. This tests whether the dataset can support useful predictions and supplies a behavior-value estimate for later continuation.

**Stage 2: a small action-transition model.** Estimate pooled probabilities and next-state distributions for shots, pass completion/interception, retained control, fouls, and rebounds. Use regularized generalized models or small boosted trees first. Fit shooting outcomes separately from how often a shot is selected. Evaluate pass destinations at arrival, including travel time and defensive movement; the receiver's current shot value is not the value of a pass.

**Stage 3: shooting versus continuing.** Combine branch probabilities with continuation values, compare only feasible and sufficiently supported actions, and report uncertainty. Include both taken and declined shooting opportunities. A sparse candidate should produce an unsupported result, not a confident ranking. Recipient-specific failed-pass risk is especially weakly identified in this release.

**Stage 4: player access and decision summaries.** Only after validation, examine how often a player reaches a viable attempt before turnover/expiry, time to that opportunity, and the associated state value. Adjust for starting state and creation burden. Decompose observed value changes for exploration, but do not assign all movement in team EPV to the ballhandler as causal credit.

A graph or sequence model is a later comparison if more tracking becomes available or suitable pretraining is obtained. The initial bottleneck is independent data and counterfactual support, not representational capacity. The literature review explains what modern architectures contribute and what their targets omit.

## Validation and a first useful deliverable

Split by whole game, never by random frames. A leave-one-game-out evaluation can use this small release efficiently; tune only within training games. Report each game's result, not only a pooled score. Game-clustered uncertainty will itself be unstable with ten clusters, so avoid precise player rankings.

Check outcome calibration, error in expected points, probability calibration for action branches, stability by shot-clock band, and sensitivity to tracking quality. Reconcile rewards and check for leakage before comparing architectures. Predictive calibration is necessary but does not validate unobserved alternative actions. Counterfactual conclusions also require credible state sufficiency, action overlap, and sensitivity to unmeasured factors; observational data cannot verify every hypothetical pass or shot.

The first presentation should show a small set of held-out possessions with court state, clocks, behavior EPV, and—only where supported—shoot/pass/retain estimates with uncertainty. Include late-clock pull-ups, early-clock pull-ups, resets after passes, and continuations ending in turnovers. This directly examines the article's thesis without presupposing that midrange attempts are good or bad.

The initial research deliverable was this design and the companion literature review. The subsequent baseline implementation is documented in [EPV prototype and Possession Lab](epv-prototype.md). The Databallr repository was only read.
