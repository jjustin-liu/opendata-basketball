"""Directly powered tests of the steal prior, independent of the model gates.

The pass-level gate in steal_risk.py evaluates on 39 pass turnovers, which
cannot resolve an effect of the size the prior actually carries: both its
log-loss and Brier deltas sit inside one standard error. These two tests ask
the prior's own questions on every credited steal in the tracking sample
instead, so a real prior and a noise prior are told apart on evidence rather
than on a coin flip.

Both are observational. Credited steals are box-score credit, not forced-
turnover attribution, and neither test controls for opponent, lineup quality or
game state.
"""

import csv
import json
import random
import statistics as st
from math import sqrt
from pathlib import Path

from .acb_defense import AcbDefense
from .defense import fit_priors, load_counts

PERMUTATIONS = 2000


def load_events(root, aliases):
    """Credited steals and possessions that have a clean five-man defence."""
    steals, possessions = [], []
    for path in sorted((root / "data/matches").glob("*/*_dynamic_events.json")):
        events = json.loads(path.read_text())
        gid = int(path.parent.name)
        by_id = {p["id"]: p for p in events["possessions"]}
        stolen = {t["possessionId"] for t in events["turnovers"] if t.get("stealerId") is not None}
        for possession in events["possessions"]:
            defenders = [aliases.get(d, d) for d in possession["defPlayerIds"]]
            if len(defenders) == 5:
                possessions.append((gid, defenders, possession["id"] in stolen))
        for turnover in events["turnovers"]:
            stealer = turnover.get("stealerId")
            possession = by_id.get(turnover["possessionId"])
            if stealer is None or possession is None:
                continue
            defenders = [aliases.get(d, d) for d in possession["defPlayerIds"]]
            stealer = aliases.get(stealer, stealer)
            if len(defenders) == 5 and stealer in defenders:
                steals.append((gid, stealer, defenders))
    return steals, possessions


def rank_of(stealer, defenders, rate, default):
    """1 = the actual stealer had the highest rate of the five on the floor."""
    order = [p for _, p in sorted(((rate.get(p, default), p) for p in defenders), reverse=True)]
    return order.index(stealer) + 1


def rank_test(steals, rate, default, seed=0):
    ranks = [rank_of(s, d, rate, default) for _, s, d in steals]
    mean = st.mean(ranks)
    # Permutation null: the credit lands on a uniformly random man on the floor.
    rng = random.Random(seed)
    null = [st.mean(rng.randint(1, 5) for _ in ranks) for _ in range(PERMUTATIONS)]
    better = sum(1 for m in null if m <= mean)
    return dict(
        events=len(ranks),
        meanRank=round(mean, 3),
        noSignalRank=3.0,
        standardError=round(st.stdev(ranks) / sqrt(len(ranks)), 3),
        t=round((3.0 - mean) / (st.stdev(ranks) / sqrt(len(ranks))), 2),
        topTwoShare=round(100 * sum(1 for r in ranks if r <= 2) / len(ranks), 1),
        topTwoChance=40.0,
        permutationP=round((better + 1) / (PERMUTATIONS + 1), 4),
    )


def lineup_test(possessions, rate, default):
    rows = sorted(
        (st.mean(rate.get(p, default) for p in defenders), stolen)
        for _, defenders, stolen in possessions
    )
    n = len(rows)
    quarter = n // 4
    quartiles = []
    for i in range(4):
        chunk = rows[i * quarter : (i + 1) * quarter] if i < 3 else rows[3 * quarter :]
        hits = sum(1 for _, s in chunk if s)
        quartiles.append(
            dict(
                quartile=i + 1,
                lineupRatePer100=[round(chunk[0][0], 2), round(chunk[-1][0], 2)],
                possessions=len(chunk),
                steals=hits,
                stealRate=round(100 * hits / len(chunk), 2),
            )
        )
    top, bottom = rows[3 * quarter :], rows[:quarter]
    p1 = sum(1 for _, s in top if s) / len(top)
    p0 = sum(1 for _, s in bottom if s) / len(bottom)
    pooled = (sum(1 for _, s in top if s) + sum(1 for _, s in bottom if s)) / (len(top) + len(bottom))
    se = sqrt(pooled * (1 - pooled) * (1 / len(top) + 1 / len(bottom)))
    return dict(
        possessions=n,
        steals=sum(1 for _, s in rows if s),
        quartiles=quartiles,
        topMinusBottomPoints=round(100 * (p1 - p0), 2),
        z=round((p1 - p0) / se, 2),
    )


def main():
    root = Path(__file__).resolve().parents[1]
    with (root / "data/player_id_aliases.csv").open() as handle:
        aliases = {int(r["player_id"]): int(r["canonical_player_id"]) for r in csv.DictReader(handle)}
    manifest = json.loads((root / "viewer/data/manifest.json").read_text())
    names = {
        int(pid): player["name"]
        for game in manifest["games"]
        for pid, player in game["players"].items()
    }
    acb = AcbDefense(root)
    season = {}
    for pid, name in names.items():
        profile = acb.profile(pid, name)
        if profile:
            season[pid] = profile["stealsPer100"]
    season_pool = 100 * acb.pool_steals

    steals, possessions = load_events(root, aliases)
    counts = load_counts(root)
    # The tracking comparison must not see the game its own event came from.
    tracking = {}
    for gid in {g for g, _, _ in steals} | {g for g, _, _ in possessions}:
        profiles, pool = fit_priors(counts, {gid})
        tracking[gid] = ({p: v["priorPer100"] for p, v in profiles.items()}, pool)

    def tracking_rank(entry):
        gid, stealer, defenders = entry
        rate, pool = tracking[gid]
        return rank_of(stealer, defenders, rate, pool)

    tracking_ranks = [tracking_rank(e) for e in steals]
    tracking_mean = st.mean(tracking_ranks)
    report = dict(
        scope=__doc__.strip(),
        season=acb.season,
        whoSteals=dict(
            acbSeason=rank_test(steals, season, season_pool),
            trackingOnly=dict(
                events=len(tracking_ranks),
                meanRank=round(tracking_mean, 3),
                noSignalRank=3.0,
                standardError=round(st.stdev(tracking_ranks) / sqrt(len(tracking_ranks)), 3),
                t=round(
                    (3.0 - tracking_mean) / (st.stdev(tracking_ranks) / sqrt(len(tracking_ranks))), 2
                ),
                topTwoShare=round(100 * sum(1 for r in tracking_ranks if r <= 2) / len(tracking_ranks), 1),
                topTwoChance=40.0,
            ),
            note="Mean rank of the player actually credited with the steal among the five defenders on the floor, ordered by prior. 3.0 is no signal; lower is better.",
        ),
        lineupSteals=dict(
            acbSeason=lineup_test(possessions, season, season_pool),
            note="Possessions split into quartiles by the mean ACB season steal rate of the five defenders, against the share ending in a credited steal.",
        ),
    )
    (root / "viewer/data/steal-prior-validation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "scope"}, indent=1))
    return report


if __name__ == "__main__":
    main()
