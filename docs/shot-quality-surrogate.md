# Dynamic shot-quality estimates

The release-score surrogate predicts SkillCorner SQ/100 from current rim distance, nearest-defender separation, lateral location, clock, three-point status, and player three-point attempt share. It estimates shot quality, not a validated player-specific shooting probability or optimal decision.

Threes now have a separate gradient-boosted fit trained only on recorded threes. Easy two-point releases cannot influence this fit. Distance is monotonic decreasing; defender separation is monotonic increasing and saturates at nine feet on threes. These constraints are modeling assumptions.

Player attempt shares use the broader season profiles, removing the displayed game's recorded attempts. This prevents an unseen tracking-sample player such as Tomic from silently inheriting the average attempt share. Profiles are retrospective season information, not strictly pregame information; the evaluation is not a prospective backtest. Attempt share describes shot selection and does not itself establish shooting accuracy.

Live three-point previews require at least 20 season three-point attempts outside the displayed game. This is an explicit support threshold, not a claim that 20 attempts establishes accuracy. Unsupported cases show no shot percentage/PPS and explain the missing evidence. Original frame forecasts are retained as unsupportedShot for reproducible rebuilds; observed release scores are unchanged.

Exploratory leave-game-out evaluation of 1,426 scored releases: equal-game MAE 9.40 percentage points overall and 3.97 points for threes; mean three-point score bias +0.08 points. These errors compare predictions with vendor scores, not actual shooting outcomes or live counterfactuals. Season context and repeated model selection limit the validation claim. Full folds are in viewer/data/vendor-surrogate.json.

First chance is estimated probability times shot value; second chance is (1-probability) times the existing live-miss continuation forecast. Possession EPV and catch EPV remain separate models. Actual shot reviews continue using observed vendor release scores. No future tracking enters current geometry.

Rebuild with `python -m epv.vendor_surrogate`, then `node scripts/build_decision_audit.mjs`. Tests cover geometry, outcome independence of score fitting, separation from two-point targets, distance/defender constraints, and exclusion of the displayed game from season attempt counts.
