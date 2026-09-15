"""Empirical-Bayes steal priors from credited steals / defensive possessions."""
import csv
import json
from collections import Counter
from pathlib import Path

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


def fit_priors(counts, exclude=()):
    exposures, steals = Counter(), Counter()
    for gid, (n,k) in counts.items():
        if gid not in exclude:
            exposures.update(n); steals.update(k)
    total = sum(exposures.values())
    pool = sum(steals.values()) / total if total else 0
    profiles = {}
    for pid in exposures.keys() | steals.keys():
        n,k = exposures[pid],steals[pid]
        profiles[pid] = dict(steals=k, defensivePossessions=n,
            rawPer100=100*k/n if n else None,
            priorPer100=100*(k+PRIOR_POSSESSIONS*pool)/(n+PRIOR_POSSESSIONS),
            evidenceWeight=n/(n+PRIOR_POSSESSIONS))
    return profiles, 100*pool


def annotate(root):
    counts=load_counts(root)
    path=root/'viewer/data/manifest.json'
    manifest=json.loads(path.read_text())
    for game in manifest['games']:
        profiles,pool=fit_priors(counts,exclude={game['match']['id']})
        for pid,player in game['players'].items():
            player['stealPrior']=profiles.get(int(pid),dict(steals=0,defensivePossessions=0,rawPer100=None,priorPer100=pool,evidenceWeight=0))
        game['stealPriorPoolPer100']=pool
    manifest.setdefault('metrics',{})['stealPrior']=dict(source='Credited stealerId / on-court defensive possessions in other tracking games',priorPossessions=PRIOR_POSSESSIONS,scope='Displayed game excluded. Sparse players shrink toward pooled player rate. No inference of speed, acceleration, reach or block ability.')
    path.write_text(json.dumps(manifest,separators=(',',':'),allow_nan=False))
    return counts


if __name__=='__main__':
    annotate(Path(__file__).resolve().parents[1])
