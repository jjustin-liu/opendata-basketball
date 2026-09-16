# Official ACB defensive box score

## What this is

Per-player steals, blocks and personal fouls for Liga Endesa 2025-26, scraped
from acb.com and used as the evidence behind the steal prior. Before this, the
prior was built only from credited `stealerId` events in our ten tracking
games, which left most players on **zero steals over zero defensive
possessions** — every one of them landed on the pooled league rate, and the
prior carried no player information at all.

## Fetching

```bash
python3 scripts/fetch_player_defense.py
```

Reads the Next.js flight payload on each club's `/estadisticas?editionId=90`
page — `editionId` 90 is season 2025-26, the same edition
`scripts/fetch_player_bios.py` already uses. A player who changed clubs
mid-season has one row per club; the script sums them into a single season
line. Output is `data/player_defense_acb.json`.

Current pull: **20 team pages · 335 players (326 with minutes) · 4651 steals ·
1835 blocks · 14781 personal fouls**, which is ~7.3 steals, ~2.9 blocks and
~23 fouls per team per game.

Per player the file carries `numGames`, `timePlayed`, `steals`, `blocks`,
`shotsRejected`, `personalFouls`, `foulsReceived`, `turnovers` and the rebound
splits, plus the source URL of every page the row came from.

## Joining to tracking ids

`epv/acb_defense.py` resolves an acb.com row for each tracking player in three
passes, most specific first:

1. `acb_player_id` in `data/player_id_aliases.csv`.
2. Exact normalized name.
3. Unique two-token overlap on the name parts, which bridges SkillCorner's
   legal names to acb.com nicknames (`Usman Garuba Alari` → `Usman Garuba`,
   `Leonardo Simoes Meindl` → `Leo Meindl`). Generational suffixes are dropped.

A tie at the same depth is refused rather than guessed. Two different **Jaime
Fernández** played in 2025-26 — one at Tenerife, one at Zaragoza — so both are
pinned explicitly in the alias file.

**207 of 208** tracking players resolve. The one miss, Aimar Mintegui, is
rostered at Bilbao but logged no ACB minutes, so there is nothing to match.

## Possession exposure is estimated, not counted

The box score counts steals per *game*; the model needs them per *defensive
possession*. Exposure is estimated from minutes at
`PACE_PER_40 = 78.2` defensive possessions per team per 40 minutes, measured
from our own tracking sample (1564 possessions over 10 games, both teams).

This is the only modelled step — the counts themselves are official. It has an
independent check: the season steal pool computed this way lands at
**1.809 per 100**, against **1.834 per 100** measured over counted possessions
in the tracking games. Agreement to 1.4% across two unrelated denominators.
`tests/test_acb_defense.py` asserts that agreement so a bad pace constant or a
broken join cannot pass silently.

## Leakage

The tracking games *are* ACB games, so the season line already contains the
game on screen. `fit_priors` subtracts each excluded game's tracking-credited
steals and its on-court defensive possessions from the season line before
shrinking. The displayed game never informs its own prior, exactly as before.

The subtraction uses tracking-credited steals, which need not match acb.com's
official credit for that game to the event. The mismatch is at most a steal or
two against a 30-game line.

## Effect on the prior

Across the 208 players:

| | before | after |
|---|---|---|
| mean evidence weight on the player | 0.058 | 0.85 |
| `priorPer100` spread (sd) | ~0 | 0.65 |
| `priorPer100` range | 1.83 for nearly everyone | 0.52 – 4.35 |

Concretely, in the first game's rotation: Retin Obasohan goes 1.83 → 2.82
steals/100 on 35 steals in 30 games, Kaodirichi Akobundu-Ehiogu goes 1.83 →
0.70 on 5 steals in 34 games. Both read 1.83 before.

## Effect on the held-out gates

`priorPer100` feeds `epv/steal_probability.py`, `epv/action_defense.py` and the
`lane_steal_prior` feature in `epv/steal_risk.py`. Blocks deliberately stay on
tracking-only counts, which is why the block numbers below are unchanged — a
useful control on the wiring.

| report | metric | before | after |
|---|---|---|---|
| `steal-probability.json` (enabled) | log loss | 0.072993 | 0.072962 |
| | Brier | 0.0208137 | 0.0208078 |
| | any-steal Brier | 0.0103544 | 0.0103455 |
| `action-defense.json` steal (enabled) | log loss | 0.08192 | 0.08118 |
| | Brier | 0.0237420 | 0.0237368 |
| `action-defense.json` block (enabled) | log loss | 0.16716 | 0.16716 |
| `steal-risk.json` (**disabled**) | log loss | 0.08909 | 0.07907 |
| | Brier | 0.020387 | 0.017770 |

Every improvement here is small, but the `steal-risk` row is not small and is
worth reading carefully, because its headline hides the result.

`steal-risk` learns a coefficient on `lane_steal_prior` per fold. The gate
requires held-out log loss *and* Brier to improve against a 0.079419 / 0.017701
baseline, and every learned coefficient to be non-negative.

| | tracking-only prior | ACB season prior |
|---|---|---|
| log loss | 0.08909 (**12% worse** than baseline) | 0.079068 (beats baseline) |
| Brier | 0.020387 | 0.017770 (misses by 0.00007) |
| coefficient sign | negative in **8 of 10** folds | positive in **10 of 10** |
| coefficient range | −0.232 … +0.152 | +0.116 … +0.222 |

The sign flip is the real finding. With ten games of evidence the model wanted
a *negative* weight on the steal prior most of the time — the feature was noise
and the fit was chasing it. With the season line every fold agrees on the
direction and the magnitudes cluster tightly. That is the difference between a
feature that means nothing and a feature that means something.

The feature nonetheless stays **disabled**, and the reason is a limit of the
gate, not a verdict on the prior. See below.

## The gate cannot resolve this, and the prior is not the reason

`steal-risk` is evaluated on pass turnovers: **39 positive labels in 2060
passes**, 2–7 per fold. Paired per-fold deltas against baseline:

| | mean delta | t | folds improved |
|---|---|---|---|
| log loss | −0.000350 | **−0.77** | 7 of 10 |
| Brier | +0.000070 | **+0.79** | 3 of 10 |

Both sit inside one standard error of zero. `steal-probability` is the same
story on 187 positives — every per-fold |t| < 1.3. The 0.00007 Brier miss that
keeps the feature off is a coin flip, not a measurement: at this label volume
the gate would reject a genuinely good feature roughly as often as it accepted
it. Reading "fails the Brier gate" as "the prior does not help" is the error.

So the prior has to be tested on a question the sample can actually answer.
`epv/steal_prior_validation.py` does that, using every credited steal rather
than only pass turnovers:

```bash
python3 -m epv.steal_prior_validation
```

**Who steals?** For each of the 134 credited steals with a clean five-man
defensive lineup, rank the five defenders by prior and record where the actual
stealer landed. 3.00 is no signal; lower is better. The tracking comparison
excludes each event's own game.

| prior | mean rank of the stealer | t | stealer in top 2 |
|---|---|---|---|
| ACB season line | **2.679** | **+2.55** (permutation p = 0.008) | 47.8% |
| tracking-only | 3.179 | −1.48 | 35.8% |
| chance | 3.000 | — | 40.0% |

The tracking-only prior is on the *wrong side of chance*. Ten games do not
merely under-inform it; they point it backwards, which is what the 8-of-10
negative coefficients were reporting.

**Do high-steal lineups steal more?** Split all 1312 clean-lineup possessions
into quartiles by the mean ACB steal rate of the five defenders:

| lineup STL/100 | possessions | steals | rate |
|---|---|---|---|
| Q1 0.98 – 1.56 | 328 | 23 | 7.01% |
| Q2 1.56 – 1.78 | 328 | 23 | 7.01% |
| Q3 1.78 – 1.94 | 328 | 34 | 10.37% |
| Q4 1.94 – 3.39 | 328 | 55 | **16.77%** |

Monotone, and Q4 − Q1 = **+9.76 points, z = +3.86**.

Both tests are observational: credited steals are box-score credit rather than
forced-turnover attribution, and neither controls for opponent, lineup quality
or game state. Quartile 4 lineups are disproportionately good defences overall,
so part of that gap is not the steal rate itself. They establish that the prior
orders players correctly — not a causal estimate.

`tests/test_acb_defense.py` asserts all three outcomes, so a regression that
guts the prior fails a test instead of passing a gate quietly.

## What this does not measure

Box-score credit only. A steal is credited to one player; it says nothing about
who forced the turnover. Personal fouls mix shooting fouls, reach-ins, off-ball
and offensive fouls, and are carried for display, not wired into any model.
None of these counts imply speed, acceleration, reach or contest quality.
Season totals include the playoffs as published, so a deep-run player has more
exposure than a 34-game regular season alone.

## Where it surfaces

- `stealPrior` on every manifest player, with `evidenceSource` naming
  `acb-season`, `tracking` or `pooled`.
- `acbDefense` on every manifest player: games, minutes, estimated possessions,
  raw counts and per-100 rates for steals, blocks and fouls.
- `metrics.acbDefense` in the manifest: season, source, pace constant and the
  three league pool rates.
- `viewer/data/steal-prior-validation.json`, written by
  `python3 -m epv.steal_prior_validation`.
- The defender hover tooltip in the viewer, which now reads e.g. `Retin
  Obasohan · PG · … · 2.82 steals/100 shrunk prior (0.92 weight on the player,
  displayed game removed) · ACB 2025-26: 35 STL · 1 BLK · 95 PF in 30 G`.
