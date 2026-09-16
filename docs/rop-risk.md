# Conservative remaining-possession risk

ROP now uses 75% other-game training prevalence and 25% geometry-model prediction. The result is floored at the next-two-second forecast so the horizons remain coherent. Training prevalence gives each possession equal weight and excludes the displayed game. This is a conservative fallback, not a newly validated situational model.

The old held-out Brier score was 0.134949; the constant baseline was 0.134241. The blend scores 0.134014 on the same ten games. Its average forecast is 15.92% versus 15.93% observed. These weights were selected after examining these games, so the small improvement is exploratory and needs fresh-game confirmation.

Only ROP changes. Next-two-second risk, pass risk, cumulative exposure, and the PPA × survival recap calculation are unchanged. The original exported ROP is retained in `turnoverRestRaw`; repeat refreshes do not compound shrinkage.

Refresh existing exports with `PYTHONPATH=. .venv/bin/python scripts/refresh_rop.py`. The main build applies the same blend on future exports. The refresh also updates the model-validation metrics and preserves the original summary under `ropBeforeAdjustment`.
