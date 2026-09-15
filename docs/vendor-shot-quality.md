# SkillCorner shot-quality interpretation check

1433 of 1459 shot events have a score, across 10 available games.
Treating SQ/100 as P(make) gives mean predicted 43.21% vs actual 41.66%.
For non-fouled attempts (1290), predicted 43.88% vs actual 43.80%.
For threes (519), predicted 34.68% vs actual 33.33%.
Fouled attempts (143) diverge: predicted 37.12% vs actual 22.38%.

Overall Brier score is 0.2071 vs 0.2399 for a leave-game-out 2PT/3PT
base-rate predictor. No calibration transformation was fitted to the vendor
scores. The vendor training sample is unknown: this is an interpretation and
calibration check on our dataset, not proof of external generalization.

A game-cluster bootstrap gives a 95% interval of -1.10 to +4.22 percentage
points for mean predicted minus observed make rate. Score bands broadly track
observed rates, with large uncertainty in sparse high-score bins.

The evidence supports interpreting SQ/100 as a make-probability estimate, but
does not establish the vendor's precise target definition or shooter adjustment.
First-chance expected points under that interpretation are SQ/100 times 2 or 3;
free throws and rebound continuation are separate. The vendor field describes
an observed shot, not every hypothetical shot from an arbitrary replay state.

Reproduce: `.venv/bin/python scripts/check_vendor_quality.py`.
Detailed counts: `artifacts/vendor_quality_check.json`.
