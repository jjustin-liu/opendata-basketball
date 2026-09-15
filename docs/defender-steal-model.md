# Defender steal priors and next-two-second probabilities

Credited steals come from `turnovers.stealerId`; exposure is each player's on-court defensive possessions (`defPlayerIds`). Aliases are canonicalized. Rates are steals per 100 defensive possessions, shrunk toward the pooled player rate with 100 possession equivalents. A missing player receives the pooled rate and zero evidence weight. These are retrospective other-game rates, not measured reaction times or mobility.

The localized pass-risk experiment adds a lane-weighted steal prior to the existing selected-pass logistic model. It did not pass validation: equal-game log loss worsened from 0.07942 to 0.08909; Brier worsened from 0.01770 to 0.02039. It remains disabled. Pass risk and physical interception radii were not changed. See `viewer/data/steal-risk.json`.

The separate joint model estimates six exclusive outcomes: no credited steal or a steal credited to each of the five current defenders within two game-clock seconds, during the current defensive possession. Inputs are current ball distance, holder distance, nearest other offensive player distance, maximum passing-lane proximity, relative closing speed from prior tracking, and the shrunk steal prior. It uses shared defender coefficients and a joint softmax, so reordering defenders only reorders their probabilities and the six outcomes sum to one. It predicts observed behavior, not the result of forcing a particular pass or drive.

Whole-game held-out fitting excludes the test game's outcomes from all priors. Each training row's prior also excludes its own game. Evaluation uses at most one state per recording second: 17,890 states, including 187 positive states (not 187 independent steals). Shared coefficients have L2 regularization 0.01; this is an exploratory specification, not a tuned production model.

Equal-game joint log loss is 0.07299 versus 0.07534 for a training-only constant steal rate allocated equally to defenders. Joint Brier is 0.02081 versus 0.02086. Any-steal Brier is 0.010349 versus 0.010387. The improvement is small and does not establish strong player attribution or calibrated counterfactual probabilities. The UI marks the forecast experimental and separates it from pass TO and possession EPV. Full per-game results are in `viewer/data/steal-probability.json`.

Run `python -m epv.steal_risk` to rebuild priors and evaluate the pass feature, then `python -m epv.steal_probability` to rebuild per-defender forecasts. Both are called by the full build. Tests cover game exclusion, shrinkage, local feature weighting, sum-to-one, defender permutation, and ignoring outcome/forecast fields in geometry extraction.

## Per-defender blocks

`python -m epv.block_probability` fits the same six-outcome architecture for credited blocks. Labels use blocked shots with a blockerId and the shot end frame/game clock. Predictors additionally include defender-to-rim distance, ballhandler-to-rim distance and listed height. The prior is now credited blocks per defensive possession, with the same exclusion and shrinkage rules. All targets are future events; predictors use the current or preceding tracking state only.

The source has 51 credited block events. The sampled modeling set has 17,893 states and 53 positive states, not 53 independent block events. Equal-game held-out joint log loss is 0.02232 versus 0.02523 baseline; joint Brier 0.005934 versus 0.005952. Small absolute gains and sparse positives mean this remains experimental. Exported `blockForecast` values cover 79,354 supported frames. Both models use a two-second horizon; neither estimates risk conditional on choosing a particular shot/pass. Steal and block forecasts are separate, so their probabilities should not be added.

Defender chip captions display player name plus STL and BLK percentages in 2D and 3D, refreshed on each replay state. Missing/disabled forecasts show a dash. The defense panel and hover details use the same frame forecasts. These values do not modify chip size, interception radius, shot quality or EPV.
