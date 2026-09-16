"""Empirical-Bayes steal priors from credited steals / defensive possessions.

Evidence is the player's official ACB season line (data/player_defense_acb.json)
rather than the ten tracking games alone, which leave most players on zero
credited steals. The tracking games are themselves ACB games, so each excluded
game's tracking contribution is subtracted back out of the season line before
shrinking; the displayed game never informs its own prior.
"""
import csv
import json
from collections import Counter
from pathlib import Path

from .acb_defense import PACE_PER_40, AcbDefense

PRIOR_POSSESSIONS = 100


def load_counts(root, event_kind="steal"):
    aliases = {int(r['player_id']): int(r['canonical_player_id']) for r in csv.DictReader((root/'data/player_id_aliases.csv').open())}
    counts = {}
    for path in sorted((root/'data/matches').glob('*/*_dynamic_events.json')):
        events = json.loads(path.read_text())
        exposures, steals = Counter(), Counter()
        for possession in events['possessions']:
            exposures.update({aliases.get(p,p) for p in possession['defPlayerIds']})
        targets = events['turnovers'] if event_kind == 'steal' else [s for s in events['shots'] if s.get('blocked')]
        for turnover in targets:
            pid = turnover.get('stealerId' if event_kind == 'steal' else 'blockerId')
            if pid is not None:
                steals[aliases.get(pid,pid)] += 1
        counts[int(path.parent.name)] = (exposures, steals)
    return counts


def load_season(root, names, kind='steal'):
    """Per-player ACB season events and estimated defensive possessions."""
    acb = AcbDefense(root)
    field = 'steals' if kind == 'steal' else 'blocks'
    season = {}
    for pid, name in names.items():
        profile = acb.profile(pid, name)
        if profile:
            season[pid] = (profile[field], profile['possessions'], profile)
    return season, acb


def fit_priors(counts, exclude=(), season=None):
    exposures, steals = Counter(), Counter()
    excluded_exposures, excluded_steals = Counter(), Counter()
    for gid, (n,k) in counts.items():
        if gid in exclude:
            excluded_exposures.update(n); excluded_steals.update(k)
        else:
            exposures.update(n); steals.update(k)
    evidence = {}
    for pid in exposures.keys() | steals.keys() | set(season or ()):
        if season and pid in season:
            events, possessions = season[pid][0], season[pid][1]
            # The season line already contains the excluded games; take them back out.
            evidence[pid] = (max(0.0, events - excluded_steals[pid]),
                             max(0.0, possessions - excluded_exposures[pid]),
                             'acb-season')
        else:
            evidence[pid] = (float(steals[pid]), float(exposures[pid]), 'tracking')
    total = sum(n for _,n,_ in evidence.values())
    pool = sum(k for k,_,_ in evidence.values()) / total if total else 0
    profiles = {}
    for pid,(k,n,source) in evidence.items():
        profiles[pid] = dict(steals=k, defensivePossessions=round(n,1),
            rawPer100=100*k/n if n else None,
            priorPer100=100*(k+PRIOR_POSSESSIONS*pool)/(n+PRIOR_POSSESSIONS),
            evidenceWeight=n/(n+PRIOR_POSSESSIONS),
            evidenceSource=source)
    return profiles, 100*pool


def annotate(root):
    counts=load_counts(root)
    path=root/'viewer/data/manifest.json'
    manifest=json.loads(path.read_text())
    names={int(pid):player['name'] for game in manifest['games'] for pid,player in game['players'].items()}
    season,acb=load_season(root,names)
    for game in manifest['games']:
        profiles,pool=fit_priors(counts,exclude={game['match']['id']},season=season)
        for pid,player in game['players'].items():
            player['stealPrior']=profiles.get(int(pid),dict(steals=0,defensivePossessions=0,rawPer100=None,priorPer100=pool,evidenceWeight=0,evidenceSource='pooled'))
            entry=season.get(int(pid))
            player['acbDefense']=entry[2] if entry else None
        game['stealPriorPoolPer100']=pool
    manifest.setdefault('metrics',{})['stealPrior']=dict(
        source=f'Official ACB {acb.season} box-score steals over defensive possessions estimated from minutes at {PACE_PER_40} possessions per 40 minutes; players without an ACB match fall back to credited stealerId in other tracking games',
        priorPossessions=PRIOR_POSSESSIONS,
        matched=len(season), players=len(names),
        scope='Displayed game excluded: its tracking-credited steals and on-court defensive possessions are subtracted from the season line before shrinking. Sparse players shrink toward the pooled player rate. Box-score credit only; no inference of speed, acceleration, reach or block ability. Possession exposure is estimated from minutes, not counted.')
    manifest['metrics']['acbDefense']=dict(season=acb.season,competition='Liga Endesa (ACB)',
        source='acb.com per-team statistics pages, editionId 90',
        pacePer40=PACE_PER_40,
        poolStealsPer100=round(100*acb.pool_steals,3),
        poolBlocksPer100=round(100*acb.pool_blocks,3),
        poolFoulsPer100=round(100*acb.pool_fouls,3),
        note='Season totals include the playoffs as published. Per-100 rates divide by possessions estimated from minutes at league pace, so they are rates over estimated exposure, not counted exposure.')
    path.write_text(json.dumps(manifest,separators=(',',':'),allow_nan=False))
    return counts, season


if __name__=='__main__':
    annotate(Path(__file__).resolve().parents[1])
