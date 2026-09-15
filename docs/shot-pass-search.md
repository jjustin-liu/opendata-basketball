# Shot, pass and search: first observed-transition model

Implemented in `epv/search.py`; regenerate with `.venv/bin/python -m epv.search` after the main EPV build. The full `epv.build` pipeline also invokes it. Results live in `artifacts/search_validation.json`; anchors in `artifacts/search_examples.pkl`; per-state held-out forecasts are exported into replay JSON. This model adds forecasts rather than replacing existing EPV or action values.

## What is separated

- Immediate SHOT: existing estimated field-goal points plus miss-weighted live-miss continuation. This is an approximate immediate-release scenario, excluding free throws.
- PASS: existing projected catch EPV times pass survival. Player positions at catch still use constant-velocity projection and learned flight time. It does not simulate adaptive defense.
- Shot creation: the new probability of a broad shot family occurring after a dribble start, and conditional mean release distance, defender separation and elapsed time. These describe observed behavior, not whether a move is feasible or optimal. We do not convert the average release into SQ: evaluating a nonlinear shot model at an average state would not equal the expected value across releases.
- SEARCH: a new observed first-dribble reference. Its experimental points regression predicts remaining possession scoring after states where a dribble was actually initiated. It is not an identified causal action value and is kept in an expandable detail section, out of court rankings.

The new point estimate is not added to current EPV, SHOT or PASS. Search may terminate in a shot or pass; these are successive actions rather than independent additive rewards. The first-event partition gives precedence to pass attempts over ensuing pass turnovers, and to shots over their shooting fouls. Its separate turnover/foul branches therefore exclude those already represented under a pass/shot.

## Data and inclusion

The ten games contain touch, dribble, pass, drive, closeout, foul and shot events. There are only 30 stepbacks in the entire shot dataset. This cannot establish a player-specific stepback repertoire. No NBA Harden/Hauser/Brown abilities are inferred from these ACB games.

One anchor per touch: use the first recorded dribble and the latest supported tracking snapshot strictly BEFORE it, at most five 25-Hz frames (0.2 seconds) earlier and after touch start. Require matching ballhandler identity, rim distance <=32 ft and shot clock >=2.2 sec. Features are only contemporaneous/past-derived EPV geometry, including holder speed, toward-rim movement and defender closing speed. No shot type, future trajectory, future shot clock, dribble count over the touch, touch ending or shot outcome enters the feature vector.

Of 3,354 dribble touches, 1,198 are accepted (187 players). Exclusions: 1,719 wrong holder/outside scope; 312 without a strictly prior supported state; 125 missing touch/tracking. These are independent touch anchors, not 1,198 independent possessions; sample weights give each possession equal total weight in event/points fitting and evaluation.

First-event labels within two seconds of dribble onset on the same touch:

| Label | Count |
|---|---:|
| Pass attempt | 499 |
| Still same touch | 433 |
| Pull-up / stepback / fadeaway family | 101 |
| Rim / floater / hook family | 93 |
| Foul before pass/shot | 33 |
| Turnover before pass/shot | 22 |
| Other touch ending | 14 |
| Other shot | 3 |

No detected event plus a touch ending inside the horizon is `other`, not continued control. Applying this initiation model midway through a dribble sequence is an extrapolation and is labeled as such in the viewer. Rare branches, particularly other-shot, must not be interpreted as well-calibrated move-specific probabilities.

## Fitting and player evidence

A median imputer and standard scaler precede regularized multinomial logistic regression (C=0.1). Ridge regressions (alpha=100) estimate remaining possession points and, only among shot branches, mean release distance/separation/time. Remaining points use the original actual-possession reward target, including later free throws/rebounds. This does not separately identify foul drawing skill or recovery after interrupted moves.

Player effects are residual observed-choice/points adjustments relative to context. Residuals are computed using inner leave-one-game-out predictions, not in-sample fits. Require >=20 touch anchors across >=2 training games, then shrink by n/(n+80). Otherwise weight is exactly zero and the UI displays the pooled fallback and evidence counts. Release geometry remains pooled even for eligible players.

For each outer held-out game, every model, imputer, scaler, player count and residual excludes that game. Inner residual models exclude both the outer test game and the residual row's game. There were ZERO held-out touch anchors qualifying for a player effect, so we have not empirically validated personalization. Identical context/player metrics do not constitute evidence that player differences are absent.

## Held-out evaluation

Ten outer folds, averaging metrics equally across games. Baselines use only outer training data. No hyperparameter search on held-out results.

| Metric (lower is better) | Constant | Context model |
|---|---:|---:|
| Next-event log loss | 1.4354 | 1.4012 |
| Remaining-points RMSE | 1.1614 | 1.1756 |
| Release distance MAE | 8.063 ft | 5.893 ft |
| Release defender separation MAE | 1.498 ft | 1.384 ft |
| Release elapsed time MAE | 0.332 s | 0.310 s |

Release metrics condition on shots actually occurring within the horizon; they do not validate move feasibility or full rollout accuracy. Approximate paired bootstrap over ten games (10,000 draws, fixed seed): next-event context-minus-constant log loss 95% interval [-0.0607,-0.0085]; points RMSE delta [+0.0075,+0.0208]. With only ten games, these are exploratory intervals, not population guarantees.

The pooled 80% outcome-error range uses the 80th percentile absolute inner out-of-game points residual in outer training data. It covered 81.0% of held-out outcomes averaged over games. It is a broad prediction-error range, not uncertainty of the expected value and not a personalized range. We do not present confidence intervals for individual branch probabilities.

The defensible improvement is context-sensitive next-action and conditional release forecasting. The points head did not improve prediction and is not promoted to an actionable SEARCH score.

## What a real capability model still needs

1. Many repeated games per player, with enough examples of each move in overlapping contexts. A pooled fallback avoids inventing missing skill, but cannot replace this evidence.
2. A move-conditioned stochastic transition model: initiation, elapsed time, ball/receiver/defender trajectories, resulting release, turnovers, fouls and interrupted continuations. Release distributions must be propagated through scoring, not replaced with mean geometry.
3. Better movement state: acceleration, direction changes, body orientation/stance and release mechanics where available. Current tracking summaries do not establish actual head direction, balance or defender intent.
4. Distinguish behavior policy P(action | state, player) from potential value Q(state, action, player). Frequent use does not establish feasibility or superiority; unchosen moves have no observed outcome. Counterfactual evaluation requires overlap diagnostics and defensible assumptions about selection, with new held-out games and sensitivity checks. An optimal-action recommendation is premature.
5. Test transition errors, event calibration by branch, outcome value, and player-specific improvement separately. Then assess option creation and choice quality separately; avoid defining regret as the maximum of noisy, incomparable estimates.

## Verification

34 Python tests and four playback tests pass. New tests cover strict pre-dribble anchoring, future geometry exclusion, shot/foul and pass/turnover exclusivity, horizon/unknown-end handling, and player shrinkage/fallback. Replay artifact checks verify probabilities sum to one, finite values, unique training touch anchors, strict timestamps, and held-out game isolation. The viewer panel was inspected in Chrome at game 179612 / possession 1-26.
