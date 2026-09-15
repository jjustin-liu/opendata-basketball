# EPV prototype and Possession Lab

This implementation fits a descriptive expected-remaining-points model, two turnover classifiers, and a player-adjusted shot-making model, then exports held-out predictions into an animated court viewer. The EPV model now includes shooting inputs. It remains an observational model, not the counterfactual shoot/pass/retain model proposed in [the design](epv-model-design.md).

## Run locally

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
python3 scripts/download_tracking.py
.venv/bin/python -m epv.build
.venv/bin/python -m http.server 8765 --bind 127.0.0.1 --directory viewer
```

Open [Possession Lab](http://127.0.0.1:8765). Training and exporting are offline; the viewer needs only a static HTTP server. The lock file records the tested Python 3.14 environment; `requirements.txt` lists broader supported dependency ranges.

The download script uses the official public GitHub media endpoint and verifies both size and SHA256 against each checked-in LFS pointer. It caches about 361 MB in `.cache/tracking/` without changing the pointers. Extracted feature/replay caches live in `.cache/epv/`. Use `--rebuild` after changing extraction or features. Final models, states, and validation metrics live in `artifacts/`; browser data lives in `viewer/data/`. All generated data and the virtual environment are ignored by Git.

## Viewer

- Choose among all ten games and 1,467 possessions with supported predictions. Filter for turnovers, scoring possessions, or highest predicted short-term risk; search by team or quarter.
- Play, pause, change speed, move frame by frame with arrow keys, or scrub the timeline. Space toggles playback outside form controls. Click the charts or event buttons to seek. The URL preserves the game and possession.
- The court shows all players and the ball. Hover a player for their name. Teal attacks toward the left basket; coral defends. Dashed rings identify extrapolated positions.
- The pressure overlay connects the inferred ballhandler to the closest defender and shows a 6 ft neighborhood. Potential passing lanes are marked by geometric clearance: a crowded lane has a defender within 3 ft of its interior segment. This is not a learned per-pass interception probability.
- Select **With shooting skill** or **Geometry baseline** under EPV to compare the two models on the same play. A separate shooting panel shows the current ballhandler, make probability, pooled probability, field-goal points, and the number of other-game attempts supporting that player's estimate.
- EPV and both turnover estimates are synchronized with the selected frame. Charts show EPV and next-2-second turnover risk. Actual outcomes appear separately for replay navigation.
- The validation dialog compares constant, clock/location, and full-geometry models, with held-out turnover calibration. EPV and rest-of-possession turnover risk are explicitly marked experimental because they do not beat the constant baseline overall.

This is tracking animation; the release does not include broadcast video. Missing/dead-ball frames are skipped during playback. Unsupported prediction states remain visible as court frames but show no values; chart gaps are not interpolated. Free throws remain part of the target even when their stopped-clock frames are omitted from playback. Player and ball positions are linearly interpolated at the display refresh rate between 5 Hz samples. Model values remain on the earlier observed state. No interpolation crosses tracking gaps or period changes. Each available replay sample advances by 0.2 seconds at 1×; the elapsed display uses the original video timeline and may jump over omitted intervals.

## Model and target definitions

`epv/features.py` computes 26 pooled state features: clocks, ball location/height, basket distance, trailing velocity, defender proximity and closing speed, local crowding, rim protection, spacing, potential passing-lane clearance, and tracking quality. The base geometry features contain no player identity, season aggregates, vendor shot quality, or future outcome features. The augmented EPV model adds three shooting features: player-adjusted make probability, expected field-goal points, and the regularized player adjustment. Motion uses only a preceding frame within 0.5 seconds; vendor speed fields are not used.

`epv/build.py` fits histogram gradient boosting with fixed conservative settings (100 iterations, 7 leaves, L2 regularization, no internal random-frame early stopping). It compares the same model family with six clock/location features, all 26 geometry features, and 29 geometry-plus-shooting features, as well as a constant prediction. Turnover models continue to use geometry without player skill.

- **EPV:** remaining points scored by the current offense under the recorded possession ID, including made field goals, free throws, and subsequent offensive-rebound chances. Points already scored are subtracted at each state. Opponent free throws are excluded by team identity. The model predicts behavior in the data, not optimal offense or net points including the opponent's next possession.
- **Turnover, next 2 seconds:** a recorded turnover or offensive foul strictly after the state and within two running-game-clock seconds, before this possession ends.
- **Turnover, rest of possession:** a recorded turnover or offensive foul strictly after the state, before the recorded possession ends.

The two turnover models are fitted separately. Their predictions are projected onto `0 <= short-term <= remaining <= 1`: if the ordering is violated, both become their average. This is the least-squares projection; it enforces probability coherence, not calibration. Reported errors and displayed predictions both include this step. Apply `epv.build.coherent_risks` when using the saved models for new predictions.

The model predicts only supported controlled-ball states: complete player/ball tracking, a usable chance, an available shot clock, a plausible nearest offensive ballhandler, and no recorded shot/pass in flight. Ball control is a geometric approximation. Chance usability and event segmentation are retrospective annotations; this is an offline analysis pipeline, not a proven live-deployment system. The source tracking itself may also be retrospectively smoothed.

Training samples every 10th tracking frame (2.5 Hz); replay/prediction samples every fifth frame (5 Hz). Each possession gets equal total training/evaluation weight within a game, preventing long possessions from dominating. This defines a possession-weighted random eligible-state estimand; it is not a possession-start-only score.

## Shooting model and player skill

`epv/shooting.py` trains on 1,433 of the 1,459 shot events; 26 lack required context. Fouled misses remain included as unsuccessful field goals. The target is a made field goal on a shot event, not official box-score FG% conditional on an attempt counting. No final contest categories (which can encode blocks), assisted outcomes, or vendor `shotQuality` fields are features.

The pooled model is a regularized logistic regression over quadratic spline transforms of basket distance, closest-defender distance, absolute lateral location, and shot clock. A second step estimates a player effect on the log-odds scale after accounting for that context, separately for rim attempts (under 8 ft), other twos, and threes. A zero-centered Gaussian prior with precision 8 pulls small samples toward the pooled probability. This is a fixed-prior regularized estimate; no hyperparameter search or empirical-Bayes variance estimation is claimed. Unseen players or player/zone combinations receive the pooled estimate exactly. Of 37,909 eligible held-out shooting states, 7,885 (20.8%) have other-game player/zone evidence; the remaining states use the pooled fallback. This limited coverage constrains the effect of player personalization in the current release.

The viewer's shooting scenario applies this release-context model to the current ballhandler's location and nearest defender. It is approximate: body pose, gather time, shooter movement type, and defensive response during release are not modeled. No scenario is shown beyond 32 ft or without a supported controlled-ball state. Two/three-point status is inferred from current position, using the FIBA 6.75 m arc and 6.60 m corner offset; near-line scenarios are flagged because tracked body coordinates are not shoe positions. [FIBA 2024 rules, article 2.5.4](https://assets.fiba.basketball/image/upload/documents-corporate-fiba-official-rules-2024-v10a.pdf).

SkillCorner's event `distance` is exactly reproduced with the offensive basket at `(-40.75, 0)` feet. This corrects the original prototype's `-41.75` assumption. Extraction caches are now versioned so the corrected geometry is recomputed automatically.

`expected field-goal points = P(made FG) × inferred 2-or-3 point value`. It excludes free throws and rebound continuation. It therefore cannot be subtracted from full EPV and called decision regret. EPV uses this quantity as an input to its direct remaining-points regression, rather than explicitly summing action branches. Teammate shooting skill and individual defender ability are not yet modeled.

Each outer held-out game's shooting model uses only the other nine games. Within EPV training, each row gets shooting inputs from a model excluding both its own game and the outer test game (eight-game fits). The final deployment EPV model uses leave-one-game-out shooting inputs for training. This prevents self-outcome leakage through player skill estimates. These are game-held-out, retrospective estimates; other training games can occur later in the season, so this is not a chronological forecasting backtest.

## Evaluation and limitations

Every displayed game is held out from its nine-game training set. Hyperparameters are fixed, and no aggregate priors are used. Summary errors give games equal weight; per-game results and their training game IDs are saved in `artifacts/metrics.json`. Final all-game models are saved separately in `artifacts/models.joblib`; the viewer never substitutes their fitted predictions. That bundle contains `shotModel`, `epvFeatures` (29 columns), and `features` (26 turnover columns). Enrich a new state and apply the saved shooting model before predicting with the augmented EPV model.

The current result is modest short-term turnover signal from player geometry and useful held-out shot-making signal. Player adjustments add only a small further improvement to shot accuracy. Full-possession EPV has not improved from the shooting inputs and does not outperform a constant baseline overall. Ten games cannot establish stable individual-player effects or causal value for hypothetical passes. A probability changing alongside nearby defenders is not proof that those defenders caused the change.

| Held-out error (lower is better) | Constant | Clock/location | Geometry | + Shooting |
|---|---:|---:|---:|---:|
| EPV RMSE | 1.17359 | 1.17824 | 1.17533 | 1.17857 |
| Next-2-second turnover Brier | 0.02822 | 0.02831 | 0.02802 | — |
| Next-2-second turnover log loss | 0.13186 | 0.13142 | 0.12657 | — |
| Remaining turnover Brier | 0.13424 | 0.13496 | 0.13490 | — |

The geometry model averages 2.62% predicted next-2-second risk against 2.90% observed under the evaluation weights, so its probabilities still show some underprediction. No statistical-significance claim is made from ten games.

| Held-out shooting model | Brier | Log loss |
|---|---:|---:|
| constant | 0.24316 | 0.67942 |
| pooled | 0.23071 | 0.65290 |
| personalized | 0.23009 | 0.65156 |

A separate turnover probability for each hypothetical teammate pass is a future model. The present labels predict turnover under observed play, including keeping the ball. Failed passes do not reliably record their intended recipient, so a recipient-specific training set would need annotated or defensibly reconstructed destinations and validation of those labels.

Audit findings:

- All 20 team-game point totals reconcile between shot/free-throw events and `matches.json`.
- Tracking is camera-oriented, unlike event locations. `leftHoop` determines a 180° rotation for the model and viewer; 547 exact-frame comparisons have a median offset of 0.0004 ft and a maximum of 2.88 ft. This validates orientation while retaining small source event/tracking discrepancies.
- The event data contain 68 passes with missing end frames. Their first second after release is conservatively masked as in-flight; missing end frames are not imputed as known catches.
- Six offensive fouls without a duplicate turnover within one second were added to turnover labels. Two made free-throw points attached to a possession with a different offensive team were excluded from that possession's offensive reward. They remain in the team score reconciliation.
- 1,551 possessions have replay frames; 1,467 have at least one supported prediction. Missing/rejected states are not treated as zero-risk outcomes.

## Checks

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/validate_artifacts.py
npm test
node --check viewer/app.js
```

Tests cover remaining rewards, horizon boundaries, risk coherence, possession weighting, player-order invariance, passing geometry, unavailable tracking, causal motion history, the basket coordinate, player-specific shooting adjustments, unseen-player fallback, held-out attempt counts, shooting range limits, and visual interpolation. The artifact check validates fold provenance, bounds, replay counts, and alignment of normalized tracking with observed shot locations. Browser checks cover playback, seeking, validation details, and responsive layout.

## Pass-to-teammate scenarios

Run `.venv/bin/python -m epv.build` to rebuild the pass model and all replay
scenarios along with EPV. `epv/passing.py` contains extraction, reconstruction,
pre-release risk features, and the catch projection. The cached pass table is
`.cache/epv/pass_training_v1.joblib`.

The current reconstruction uses the ball displacement from one frame before
release to eight frames after release (or one frame before the recorded end,
whichever is earlier). It selects the teammate whose pre-release position is
closest in angle to that ray. It rejects displacement under 3 ft, best angle
above 25 degrees, and a top-two angular margin below 10 degrees. This is a
simple ray reconstruction, not a trained trajectory model; it does not use
interceptor identity as an inference feature. The interceptor is not mislabeled
as the intended receiver. All future tracking is restricted to destination
label reconstruction, never risk predictors.

Of 3,770 eligible live-ball completed passes, 2,021 pass the reconstruction
screen and 1,804 match the known receiver (89.3%). Of 83 eligible live-ball pass
turnovers, 39 pass the same screen. Training uses the actual receiver on accepted
completions and the inferred receiver on accepted turnovers: 2,060 examples.
Inbounds, self-passes, unknown outcomes and ambiguous destinations are excluded.
Accuracy on completions does **not** establish accuracy on intercepted passes.
This selection can bias the fitted turnover rate, and roughly one in ten
accepted completion reconstructions is wrong. Displayed percentages are
experimental conditional estimates, not calibrated all-pass probabilities.

A standardized, regularized logistic model (C=0.1, without class reweighting)
uses pass distance, interior-lane clearance, defender distance to passer and
receiver, count of defenders within 4 ft of the segment, and receiver distance
to the sideline. Every replay's pass model excludes that entire game. The model
does not yet include passer skill, receiver hands, defender identity, pass type,
body pose or movement as risk inputs. Motion affects projected catch EPV only.
Held-out Brier error and a training-prevalence baseline are in the model dialog
and `artifacts/metrics.json`. These assess accepted observed passes, not the
unselected counterfactual destinations shown on court.

Each hypothetical completion advances all players with their current velocity,
using only the preceding tracking sample (at most 0.4 s old), capped at 25 ft/s.
Without usable history, players remain stationary. Pass flight assumes 40 ft/s
plus 0.12 s release delay; iteration accounts for receiver movement. These are
explicit prototype assumptions, not fitted flight parameters. Projections over
1.5 s, past either clock expiry, with an intended catch outside court bounds, or without a supported
catch state are omitted. Other players’ projected coordinates stop at the
boundary instead of invalidating unrelated pass options. No defender reaction or acceleration is predicted.

The recipient becomes the holder at the projected catch; the same held-out,
shooting-aware EPV model evaluates the resulting geometry and receiver shooting
skill. New-holder motion is carried forward, while ball-flight speed is not
mistaken for dribble speed. The displayed value is `(1 - pass TO) * catch EPV`,
with zero remaining offensive points on the turnover branch. Future turnovers
**after** the catch remain part of catch EPV; these are separate from losing
this pass. This is an offensive-point objective, not a net-score objective
charging opponent transition points. Existing evidence still does not show
that the EPV model beats the constant baseline; rankings are exploratory.

Court teammates show discounted EPV and pass TO%, with BALL for the holder.
Click a teammate or its accessible card to pause and overlay gold projected
positions at the catch; details show arrival time and undiscounted EPV. Defense
jerseys remain visible; full offensive names and jerseys remain in the lineup.
Unsupported options show an em dash. The pass values always use shooting-aware
EPV regardless of the separate chart's geometry/skill comparison selector.

### Interception timing update

The pass model now also includes maximum defender time advantage, number of
reachable defenders, and number already within reach of the route. At 24
points covering 8–95% of the direct segment, compare ball arrival (0.12 s plus
travel at 40 ft/s) with defensive arrival (zero inside 2.5 ft reach; otherwise
0.18 s reaction plus remaining distance at 12 ft/s). These fixed assumptions
are **not** measured defender reactions or calibrated interception chances.
Current positions alone feed this calculation; no future tracking is used.

Ten-game mean held-out log loss improves from 0.08068 to 0.07942, while Brier
worsens from 0.01758 to 0.01770. This mixed exploratory comparison does not
establish better calibration. The original selection bias and 39-positive
sample limitation remain. We do not multiply probabilities by an arbitrary
penalty when a route is reachable. Instead, amber rings and explicit route
warnings expose this uncertainty alongside the fitted mixed-pass TO%.
Bounce passes, lobs, body orientation and actual defender reactions are still
unmodeled. The catch-position projection remains constant velocity.

`python -m epv.refresh_passes` refreshes pass risks, warnings, discounted values,
validation and the deployment pass model after a full build, reusing unchanged
catch EPV. A full `python -m epv.build` also generates the new features and
warnings. The new training cache is `.cache/epv/pass_training_v2.joblib`.


### Catch boundary correction

An unrelated player projected past a sideline or baseline no longer removes a
pass option. Their projected position is clamped to the court boundary as a
simple movement approximation. The intended receiver is still evaluated at
their unmodified projected catch position: an out-of-bounds catch is omitted.
In possession-114243-1-0 at frame 1120 this restores two unrelated pass options,
leaving only the catch projected beyond the sideline unavailable. Regression
tests cover an unrelated offensive player and defender crossing boundaries.

### Learned release-to-catch timing

Catch projections now use a regularized regression trained on 3,547 completed,
non-inbound passes across the ten games. For each event, take only the last
tracking sample strictly before release (no more than 0.2 s old), with earlier
tracking for velocity. The target is `(endFrame - startFrame) / 25`; no end
location, recorded pass distance, flight trajectory, or later defender position
is a predictor. Self-passes, unavailable context, and durations outside
0.04–3 seconds are excluded. Unlike the interception-label sample, this training
set does not require early-flight recipient reconstruction.

Inputs are pre-release distance and distance squared, receiver velocity along
and across the pass, receiver and passer speed, defender distances to passer
and receiver, interior lane clearance, and availability of motion history.
Standardized Ridge regression uses fixed alpha=20 and bounds predicted flight
time to 0.04–3 seconds. Every replay uses a fit excluding its entire game;
the separately saved deployment model uses all games. Predictions remain
conditional on completion, and pass type is unobserved.

Equal-game mean held-out timing MAE is 0.1022 seconds versus 0.1465 for the
previous 40 ft/s moving-receiver calculation; RMSE is 0.1969 versus 0.2229.
The comparison removes the separate 0.12-second release delay from the old
calculation, so both are scored against release-to-catch time. That delay is
still an assumption, not a learned decision-to-release model. No empirical
prediction interval or mixture over pass types is claimed.

Each candidate receiver gets its own learned flight time plus the release
delay. Everyone's catch position and the catch-state EPV are recomputed for
that horizon. Player movement remains constant velocity, with the existing
boundary handling and 1.5-second supported-horizon limit. Learning timing alone
does not validate those movement projections or counterfactual EPV values.
The interception-risk model and amber/green route diagnostics retain their
separate fixed-speed reach assumptions; they have not been silently refitted
using new timing features. Selected-pass details show learned flight time and
release delay separately; the model dialog reports timing validation.

### Comparable observed and projected EPV inputs

EPV now uses holder coordinates consistently and excludes ball x/y, height,
flight speed, hand-to-ball control distance, tracking detection/error fields,
and the history-availability flag. These inputs were not observable in the
same way for a hypothetical controlled catch. Turnover models retain their
original inputs. Both shooting-aware and geometry EPV models are retrained
with the new EPV feature list, `EPV_GEOMETRY_FEATURES`.

Projected catches construct a preceding 0.2-second state using only the
pre-pass velocities. The shared spatial feature extractor then calculates
holder motion and defender closing speed, including the boundary constraints.
It does not use actual later tracking. Missing motion is NaN for both training
and projected states instead of a fake zero. Ball fields still exist for
rendering and geometry extraction, but synthetic ball measurements are no
longer inputs to EPV.

`scripts/validate_catches.py` compares predicted conditional catch EPV with the
same held-out model's first supported observed state within 0.32 seconds of a
completed catch. It uses only a pre-release state within 0.2 seconds of release,
requires the actual receiver to be the observed holder, and compares only the
selected receiver. Actual post-catch frames enter this diagnostic, never
prediction inputs or training for their own held-out game. The report includes
receiver position error and mean post-catch observation delay. Consistency
with another model output is not ground-truth EPV accuracy; ordinary held-out
remaining-point error remains a separate metric. Full builds publish the
report in `artifacts/catch_validation.json` and the model dialog.

For this correction, paired catch consistency across 2,722 passes improved
from 0.05222 to 0.04640 mean absolute EPV gap; bias changed from -0.01463 to
-0.00329. Shooting-aware held-out remaining-point RMSE improved slightly from
1.17857 to 1.17752, still worse than the 1.17359 constant baseline. The Webb
example remains inaccurate: predicted conditional catch EPV 1.0566 versus
observed-state EPV 1.2720. Its projected nearest-defender closing speed is
-9.13 ft/s versus observed +12.27 ft/s. Replacing only that feature in a
same-fold diagnostic changes predicted EPV by +0.171; this is a model
sensitivity check, not a causal attribution or a permissible prediction-time
use of future information. Constant-velocity defense remains a limitation.

## Shot release and second-chance display

`python -m epv.second_chance` annotates exported shot events without retraining
EPV; full builds call it after exporting catches. The court marks the recorded
shooter SHOT for 0.6 seconds, then shows rounded make probability with SQ for
the rest of a 2-second release window. The shot panel shows release-context
make probability and expected field-goal points from our held-out shot model,
not SkillCorner's vendor shotQuality. Estimates do not change with the actual
make/miss outcome. Release annotations also work while possession-state EPV
is unavailable during ball flight.

The second-chance model trains on 627 non-fouled missed field goals with an
explicit resolved live rebound, including 173 offensive rebounds. Geometry
comes from tracking at or immediately before release (at most 0.2 seconds old):
shooter location, both teams' nearest basket distances, counts within 8/15 ft,
and nearby offensive-player/defender pairs. Standardized logistic regression
(C=0.1) predicts offensive-rebound probability. Multiply by the other games'
mean remaining points after an offensive rebound to estimate points per live
miss. Continuation value is pooled, not location-specific. Future made field
goals and free throws after the rebound in the same offensive possession form
the continuation target. No rebound landing location or outcome enters inputs.

Each game is excluded from its shot and rebound fits. Mean held-out rebound
Brier is 0.2011 versus 0.2002 constant; second-chance points RMSE is 0.7569 versus
0.7563 constant. The positional model has not demonstrated improvement over
baseline. Its probabilities and point values are experimental. Fouled misses,
dead-ball outcomes, and unresolved rebounds are outside the training estimand.
The per-shot number is `(1 - make probability) * points per live miss`, under
the explicit assumption that a miss stays live; it is not an unconditional
forecast of every foul/dead-ball outcome. These values are not added to full
EPV, which already incorporates continuation. The method dialog contains the
validation and definitions.

Ballhandler action nodes: the main circle retains selected-model EPV. Two smaller attached circles show the highest supported turnover-discounted pass value and hypothetical field-goal points plus miss-weighted second-chance points. Rebound probabilities are now exported for every supported current shooting scenario using the same other-game model and both teams' current locations. Shot totals assume a live miss and exclude free throws; they are separate from full EPV. Nodes choose an uncrowded, in-bounds direction and disappear during unsupported control or the shot annotation. Validated arithmetic across 37,909 states and checked both node labels and layout in the browser.

### Shot preview and release timing

The live SHOT preview uses current spacing. The fixed 0.5-second set-shot
projection was withdrawn after introducing misleading differences from recorded
shot forecasts. It assumed a stationary shooter and constant defender velocity
without validated release timing or defender responses. The experimental
`epv/shot_release.py` helper remains unused by the export pipeline.

Actual shot forecasts use shot-event geometry. Preview and actual values can
still differ; current spacing is not a validated forecast of the eventual release.
A learned release-state model needs held-out validation before replacing it.
