"""Experimental shooting-foul value; game-held-out, release geometry only.

SQ remains the marginal make probability. Separate conditional foul models
partition made/missed shots so FT and live-rebound branches cannot overlap.
Player identity uses regularized one-hot effects; unseen players use geometry.
"""
import csv
import json
from bisect import bisect_right
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

from .features import HOOP

FEATURES = ['rim_distance', 'court_y', 'court_x', 'defender_distance',
            'defender_toward_rim', 'defender_lateral', 'second_defender_distance', 'shot_clock']
MODEL_FEATURES = FEATURES + ['season_ftr']


def season_profiles(root):
    """Retrospective season evidence, excluding all ten tracked games.

    FTR is shooting FTA / box-score FGA, not a foul probability.
    """
    aliases = {int(r['player_id']): int(r['canonical_player_id'])
               for r in csv.DictReader((root/'data/player_id_aliases.csv').open())}
    groups, counts = {}, {}
    for r in csv.DictReader((root/'data/aggregates/acb_shotsaggregates_20252026.csv').open()):
        groups.setdefault(r['player_id'], []).append(r)
    for pid, rows in groups.items():
        selected = [r for r in rows if r['team_name'].lower() == 'total'] or rows
        key = str(aliases.get(int(pid), int(pid)))
        c = counts.setdefault(key, np.zeros(3))
        for r in selected:
            c += [float(r[k] or 0) for k in ('attempts','ft_attempts','ft_mades')]
    for path in (root/'data/matches').glob('*/*_dynamic_events.json'):
        events = json.loads(path.read_text())
        for s in events['shots']:
            key = str(aliases.get(s['shooterId'],s['shooterId']))
            if key in counts and (s['outcome'] or not s['fouled']):
                counts[key][0] -= 1
        for ft in events['free_throws']:
            key = str(aliases.get(ft['shooterId'],ft['shooterId']))
            if key in counts and ft.get('shotId'):
                counts[key][1:] -= [1, int(ft['outcome'])]
    valid = {p:c for p,c in counts.items() if min(c)>=0 and c[2]<=c[1]}
    total = np.sum(list(valid.values()),axis=0)
    pool_ftr, pool_ft = total[1]/total[0], total[2]/total[1]
    return {p:dict(season_ftr=float((c[1]+50*pool_ftr)/(c[0]+50)),
                   ft_rate=float((c[2]+30*pool_ft)/(c[1]+30)),
                   ft_attempts=int(c[1])) for p,c in valid.items()}


def geometry(frame, shooter):
    p = next((p for p in frame['offense'] if p[0] == shooter), None)
    if p is None or len(frame['defense']) != 5 or frame.get('shotClock') is None:
        return None
    xy = np.asarray(p[1:3], dtype=float)
    delta = np.asarray([d[1:3] for d in frame['defense']]) - xy
    distances = np.linalg.norm(delta, axis=1)
    direction = np.asarray(HOOP) - xy
    rim = float(np.linalg.norm(direction))
    direction /= max(rim, 1e-6)
    closest = delta[np.argmin(distances)]
    values = [rim, abs(xy[1]), xy[0], min(distances),
              float(closest @ direction), abs(float(direction[0]*closest[1]-direction[1]*closest[0])),
              float(np.sort(distances)[1]), frame['shotClock']]
    if not np.isfinite(values).all():
        return None
    return dict(zip(FEATURES, values), shooter=str(shooter))


def load_examples(root):
    aliases = {int(r['player_id']): int(r['canonical_player_id'])
               for r in csv.DictReader((root/'data/player_id_aliases.csv').open())}
    rows, free_throws = [], []
    source_count = 0
    for path in sorted((root/'data/matches').glob('*/*_dynamic_events.json')):
        events = json.loads(path.read_text())
        gid = int(path.parent.name)
        _, payload = joblib.load(root/f'.cache/epv/{gid}.joblib')
        for ft in events['free_throws']:
            free_throws.append(dict(gameId=gid, shooter=str(aliases.get(ft['shooterId'], ft['shooterId'])), made=int(ft['outcome'])))
        for shot in events['shots']:
            source_count += 1
            play = payload['plays'].get(shot['possessionId'])
            if not play:
                continue
            frames = play['frames']
            i = bisect_right([f['frame'] for f in frames], shot['startFrame']) - 1
            if i < 0 or shot['startFrame'] - frames[i]['frame'] > 5:
                continue
            shooter = aliases.get(shot['shooterId'], shot['shooterId'])
            x = geometry(frames[i], shooter)
            if x is None:
                continue
            rows.append(dict(x, gameId=gid, shotId=shot['id'], made=int(shot['outcome']),
                             fouled=int(shot['fouled']), points=3 if shot['three'] else 2,
                             sq=shot.get('shotQuality'),
                             ftPoints=sum(int(ft['outcome']) for ft in events['free_throws'] if ft.get('shotId') == shot['id'])))
    return pd.DataFrame(rows), pd.DataFrame(free_throws), source_count


class FoulModel:
    def __init__(self, table, free_throws, profiles=None):
        self.profiles = profiles or {}
        self.ftr_pool = float(np.mean([p['season_ftr'] for p in self.profiles.values()])) if self.profiles else len(free_throws)/max(1,len(table))
        table = self.design(table)
        self.training_games = sorted(int(g) for g in table.gameId.unique())
        self.models = []
        self.rates = []
        for made in (0, 1):
            subset = table[table.made == made]
            self.rates.append(float(subset.fouled.mean()))
            design = ColumnTransformer([
                ('geometry', make_pipeline(SimpleImputer(), StandardScaler()), MODEL_FEATURES),
                ('player', OneHotEncoder(handle_unknown='ignore'), ['shooter']),
            ])
            model = make_pipeline(design, LogisticRegression(C=.2, max_iter=1000))
            model.fit(subset, subset.fouled)
            self.models.append(model)
        self.ft_pool = float((free_throws.made.sum() + 1) / (len(free_throws) + 2))
        self.ft_rates = {str(player): float((group.made.sum() + 30*self.ft_pool)/(len(group)+30))
                         for player, group in free_throws.groupby('shooter')}

    def predict(self, table):
        table = self.design(table)
        return (self.models[0].predict_proba(table)[:, 1],
                self.models[1].predict_proba(table)[:, 1],
                np.array([self.profiles.get(str(p), {}).get('ft_rate', self.ft_rates.get(str(p), self.ft_pool)) for p in table.shooter]))

    def design(self, table):
        table = table.copy()
        table['season_ftr'] = [self.profiles.get(str(p),{}).get('season_ftr', self.ftr_pool) for p in table.shooter]
        return table


def ft_rebound_examples(root):
    rows = []
    for path in (root/'data/matches').glob('*/*_dynamic_events.json'):
        events = json.loads(path.read_text())
        throws = {f['id']:f for f in events['free_throws']}
        for r in events['rebounds']:
            f = throws.get(r.get('shotId'))
            if r['fgReb'] or not r['rebounded'] or not f or f['outcome'] or r['frame'] < f['frame']:
                continue
            rows.append(dict(gameId=int(path.parent.name), offensive=int(not r['defensive'] and r['teamId']==f['offTeamId'])))
    return pd.DataFrame(rows)


def components(make, points, foul_miss, foul_make, ft_rate, rebound_per_miss,
               ft_orb_probability=0, continuation=0):
    """All probabilities unconditional except the explicitly conditional inputs."""
    q = float(np.clip(make, 0, 1))
    fm, fa = float(np.clip(foul_miss, 0, 1)), float(np.clip(foul_make, 0, 1))
    fta = (1-q)*fm*points + q*fa
    live_miss = (1-q)*(1-fm)
    ft = fta*ft_rate
    second = live_miss*rebound_per_miss if rebound_per_miss is not None else None
    foul = (1-q)*fm+q*fa
    # One potentially live final free throw per foul trip, not every FT attempt.
    ft_second_if_fouled = (1-ft_rate)*ft_orb_probability*continuation
    ft_second = foul*ft_second_if_fouled
    fouled_value = (q*fa*points+ft)/foul+ft_second_if_fouled if foul>0 else None
    clean_value = (q*(1-fa)*points+second)/(1-foul) if foul<1 and second is not None else None
    return dict(foulProbability=foul, foulGivenMiss=fm, foulGivenMake=fa,
                fouledPps=fouled_value, notFouledPps=clean_value,
                ftOffensiveReboundProbability=ft_orb_probability,
                ftSecondChanceIfFouled=ft_second_if_fouled, ftSecondChancePerShot=ft_second,
                expectedFta=fta, freeThrowMakeProbability=ft_rate, freeThrowValue=ft,
                liveMissProbability=live_miss, secondChancePerShot=second,
                shotPlusSecondChance=q*points+ft+second+ft_second if second is not None else None)


def main():
    root = Path(__file__).resolve().parents[1]
    table, fts, source_count = load_examples(root)
    profiles = season_profiles(root)
    ft_rebounds = ft_rebound_examples(root)
    manifest_path = root/'viewer/data/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    contexts = table.set_index('shotId').to_dict('index')
    folds, observed, predicted, baseline = [], [], [], []
    ft_errors, ft_baseline_errors, ft_zero_errors = [], [], []
    updated = 0
    for game in manifest['games']:
        gid = game['match']['id']
        train, test = table[table.gameId != gid], table[table.gameId == gid]
        model = FoulModel(train, fts[fts.gameId != gid], profiles)
        rebound_train = ft_rebounds[ft_rebounds.gameId != gid]
        ft_orb = float((rebound_train.offensive.sum()+.5)/(len(rebound_train)+1))
        fm, fa, accuracy = model.predict(test)
        # Conditional validation uses the branch outcome only to choose the
        # appropriate evaluation stratum, never as an input feature.
        p = np.where(test.made, fa, fm)
        b = np.where(test.made, model.rates[1], model.rates[0])
        observed.extend(test.fouled.tolist()); predicted.extend(p.tolist()); baseline.extend(b.tolist())
        q = (test.sq/100).where(test.sq.between(0,100), train.made.mean()).to_numpy()
        ft_pred = ((1-q)*fm*test.points.to_numpy()+q*fa)*accuracy
        ft_base = ((1-q)*model.rates[0]*test.points.to_numpy()+q*model.rates[1])*model.ft_pool
        ft_errors.extend((ft_pred-test.ftPoints.to_numpy())**2)
        ft_baseline_errors.extend((ft_base-test.ftPoints.to_numpy())**2)
        ft_zero_errors.extend(test.ftPoints.to_numpy()**2)
        folds.append(dict(gameId=gid, shots=len(test), fouls=int(test.fouled.sum()),
                          trainingGames=model.training_games,
                          ftReboundMisses=len(rebound_train), ftOrbProbability=ft_orb,
                          brier=float(brier_score_loss(test.fouled,p)),
                          baselineBrier=float(brier_score_loss(test.fouled,b))))
        for entry in game['plays']:
            path = root/f"viewer/data/plays/{entry['id']}.json"
            play = json.loads(path.read_text())
            targets = []
            for frame in play['frames']:
                shot = frame.get('shot')
                if not shot:
                    continue
                x = geometry(frame, shot['shooter'])
                if x is not None:
                    targets.append((shot, shot, x))
            for event in play['events']:
                forecast = event.get('shotForecast')
                if not forecast or forecast.get('quality', {}).get('makeProbability') is None:
                    continue
                x = contexts.get(forecast.get('shotId'))
                if x is not None:
                    targets.append((forecast, forecast['quality'], x))
            if targets:
                fm, fa, ft = model.predict(pd.DataFrame([x for _,_,x in targets]))
                for (target, quality, _), miss, made, rate in zip(targets, fm, fa, ft):
                    result = components(quality['makeProbability'], quality['pointsIfMade'],
                                        miss, made, rate, target.get('secondChancePerMiss'), ft_orb,
                                        target.get('pointsAfterOffensiveRebound') or
                                        (target['secondChancePerMiss']/target['offensiveReboundProbability']
                                         if target.get('offensiveReboundProbability',0)>0 and target.get('secondChancePerMiss') is not None else 0))
                    target.update({k:round(float(v),6) if v is not None else None for k,v in result.items()})
                    target['foulModel'] = 'held-out-shooting-foul-v2'
                    target.pop('foulValueUnavailable', None)
                    updated += 1
            path.write_text(json.dumps(play,separators=(',',':'),allow_nan=False))
        print('Foul value annotated', gid, flush=True)
    report = dict(sourceShots=source_count, eligibleShots=len(table), fouls=int(table.fouled.sum()),
                  ftReboundMisses=len(ft_rebounds), ftOffensiveRebounds=int(ft_rebounds.offensive.sum()),
                  features=MODEL_FEATURES+['regularized shooter identity'], folds=folds,
                  brier=float(brier_score_loss(observed,predicted)),
                  baselineBrier=float(brier_score_loss(observed,baseline)), updated=updated,
                  ftPointsRmse=float(np.sqrt(np.mean(ft_errors))),
                  pooledFtPointsRmse=float(np.sqrt(np.mean(ft_baseline_errors))),
                  noFtPointsRmse=float(np.sqrt(np.mean(ft_zero_errors))),
                  definition='Conditional shooting-foul models for made and missed shots; SQ is the marginal make probability. FTA = SQ × P(foul|make) + (1−SQ) × P(foul|miss) × shot points. FT% is player-specific with 30-attempt shrinkage. Live-miss chance = (1−SQ) × (1−P(foul|miss)).',
                  limitations='Experimental release model applied to shoot-now states. Validation is conditional foul Brier, not total PPS validation. No non-shooting/bonus fouls or unusual FT awards. FT rebound rate is pooled across other games with Jeffreys smoothing; continuation value is borrowed from the held-out FG-rebound model. Assumes the last FT is live. Season FTR and FT% exclude all ten tracked games but are retrospective, not pregame. Existing full-possession EPV is unchanged.')
    manifest['metrics']['shootingFouls'] = report
    manifest_path.write_text(json.dumps(manifest,separators=(',',':'),allow_nan=False))
    (root/'artifacts/foul-value-validation.json').write_text(json.dumps(report,indent=2))
    joblib.dump(FoulModel(table,fts,profiles),root/'artifacts/foul-value-model.joblib')
    print(json.dumps({k:v for k,v in report.items() if k not in ('folds','features')},indent=2))


if __name__ == '__main__':
    with threadpool_limits(limits=2):
        main()
