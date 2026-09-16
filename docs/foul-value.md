# Shooting-foul value

The SHOT estimate now includes expected free-throw points. Full-possession EPV
is unchanged: adding this component there would count free throws twice.

## Calculation

Let q be the existing SQ-derived make probability, v the shot's 2/3-point value,
m the modeled P(shooting foul | miss), a P(shooting foul | make), and f the
player's expected FT accuracy.

- Field-goal value = q × v (unchanged).
- Expected FTA = (1−q) × m × v + q × a.
- Expected FT points = expected FTA × f.
- Live field-goal miss probability = (1−q) × (1−m).
- Second chance = live-miss probability × existing ORB probability × continuation value.
- FT rebound value per foul trip = (1−f) × other-game FT ORB probability × continuation value.
- SHOT PPS = field-goal value + FT points + field-goal second chance + P(fouled) × FT rebound value per foul trip.

And-ones award one attempt; fouled misses award two/three. Unusual FT sequences
and non-shooting/bonus fouls are not modeled. A made or
missed foul is not assigned ordinary field-goal rebound value on the foul branch.
Observed foul/make outcomes never select the displayed forecast branch: the
display is an expectation, including in post-release replay.

The recap separates P(fouled) and P(not fouled) and shows conditional PPS for
each branch. These are calculated by dividing each branch's expected points by
its probability, not by reusing unconditional SQ in both branches. Zero-probability
branches have unavailable conditional PPS, not division by zero.

FT rebound probability uses directly linked, player-resolved missed-FT rebounds
from the other nine games with Jeffreys smoothing (k+0.5)/(n+1). There are 50
eligible misses and 6 ORBs across all ten games. Continuation value is borrowed
from the existing other-game FG-rebound model, not independently fitted to six
FT ORBs. Only a single final FT can yield a rebound per trip; retained-possession
penalties and unusual trips remain outside the model.

Expected play value in the recap = combined scoring-attempt PPS × (1−approximate
TOV before first shot). Risk accumulation stops at first release to avoid applying
post-shot turnover risk twice to continuation. Incomplete risk coverage is explicit;
missing intervals are excluded and can make the estimate optimistic. This is a
retrospective first-attempt replay decomposition, not a calibrated pre-play EPV.
No supported scoring attempt means no play-value estimate, including turnover-only
plays; absence of a shot forecast is not treated as zero shot quality.

## Evidence and validation

`epv/foul_value.py` fits separate regularized logistic models on made/missed shot
strata, with normalized court location, rim distance, nearest defender's distance
and relative rim/lateral position, second-nearest defender distance, shot clock,
regularized player identity, and season shooting FTA/FGA tendency.
Only tracking at/before release (at most 0.2 seconds old) is used.

Season aggregates supply player FTR and FT accuracy. Total rows replace team rows
for traded players, aliases are canonicalized, and all ten tracked games are
subtracted. FGA subtraction excludes fouled misses; FT subtraction uses shot-linked
attempts. Invalid residual counts are excluded. Rates use 50-FGA and 30-FTA
shrinkage respectively. Missing season evidence uses training-only fallback.
Season information is retrospective—not a pregame/time-causal prior.

Each displayed game is excluded from model fitting and training-FT fallbacks.
The generated `artifacts/foul-value-validation.json` records fold membership,
coverage, conditional foul Brier versus stratum base rates, and FT-point RMSE
versus pooled and zero-FT baselines. FT-point validation uses release SQ, not
the observed make to choose the forecast branch. Missing SQ uses training make rate.
This does not validate total PPS or live shoot-versus-pass decisions. The geometry
model has only ten games and is applied outside its observed-shot selection context.

## Rebuild

Run `.venv/bin/python -m epv.foul_value` after shot quality and rebound annotations,
then rebuild decision audits and touch history. The normal `epv.build` pipeline
includes it after the SQ surrogate and before those summaries.

Recap first-chance SQ remains field-goal-only; expected FT points are separate.
Total PPS and on-court SHOT/shot-ball labels share the same inclusive value.
