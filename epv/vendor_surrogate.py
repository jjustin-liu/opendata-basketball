"""Release-score surrogate. Whole-game holdouts; current-state previews only."""
import json
from pathlib import Path
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits
from .shooting import load_shots, SHOT_FEATURES, ShotModel


class VolumeModel:
    def __init__(self, shots, rates=None):
        three = shots.get('three', shots.shot_distance > 22.15)
        table = shots.assign(three=three)
        counts = table.groupby('shooter').three.agg(['sum', 'count'])
        self.pool = float(three.mean())
        self.rates = ((counts['sum'] + 15*self.pool)/(counts['count']+15)).to_dict()
        if rates is not None:
            self.rates.update(rates)
        self.model = HistGradientBoostingRegressor(max_iter=180, max_leaf_nodes=7, min_samples_leaf=10, l2_regularization=10, monotonic_cst=[-1,1,0,0,0,0], random_state=0)
        with threadpool_limits(limits=1):
            self.model.fit(self.design(shots[SHOT_FEATURES].to_numpy(), shots.shooter, three), shots.vendorQuality.to_numpy()/100)

        self.three_model = None
        if int(three.sum()) >= 30:
            self.three_model = HistGradientBoostingRegressor(max_iter=180, max_leaf_nodes=7, min_samples_leaf=10, l2_regularization=10, monotonic_cst=[-1,1,0,0,0,0], random_state=0)
            with threadpool_limits(limits=1):
                self.three_model.fit(self.design(shots.loc[three, SHOT_FEATURES].to_numpy(), shots.loc[three, 'shooter'], three[three]), shots.loc[three, 'vendorQuality'].to_numpy()/100)

    def design(self, x, shooters=None, three=None):
        x=np.array(x, dtype=float, copy=True)
        rate=np.array([self.rates.get(int(p),self.pool) for p in shooters]) if shooters is not None else np.full(len(x),self.pool)
        outside=np.asarray(three,dtype=float) if three is not None else ((x[:,0]>22.1457)|(x[:,2]>21.6535)).astype(float)
        # On threes, additional defender separation beyond nine feet adds no bonus.
        x[outside.astype(bool),1]=np.minimum(x[outside.astype(bool),1],9)
        return np.column_stack([x,outside,rate])

    def predict(self, x, shooters=None, three=None):
        with threadpool_limits(limits=1):
            design = self.design(x,shooters,three)
            result = self.model.predict(design)
            mask = design[:,4].astype(bool)
            if self.three_model is not None and mask.any():
                result[mask] = self.three_model.predict(design[mask])
            return result


def fit(shots, rates=None):
    return VolumeModel(shots, rates)


def season_evidence(game):
    """Descriptive season profiles, with this game's recorded attempts removed."""
    counts = {}
    for attempt in game.get('shotAttempts', []):
        pair = counts.setdefault(int(attempt['player']), [0, 0])
        pair[0] += 1
        pair[1] += int(attempt['three'])
    evidence = {}
    for pid, player in game['players'].items():
        fga, threes = counts.get(int(pid), [0, 0])
        n = max(0, player.get('sampleFga', 0) - fga)
        k = max(0, player.get('sampleThreePa', 0) - threes)
        evidence[int(pid)] = dict(attempts=k, rate=k/n if n else None)
    return evidence


def features(frame, shooter):
    player = next((p for p in frame['offense'] if p[0] == shooter), None)
    if not player or not frame['defense'] or frame.get('shotClock') is None:
        return None
    x,y=player[1:3]
    return [float(np.hypot(x+40.75,y)), min(float(np.hypot(x-d[1],y-d[2])) for d in frame['defense']), abs(y), frame['shotClock']]


def main():
    root=Path(__file__).resolve().parents[1]
    all_shots=load_shots(root)
    shots=all_shots[all_shots.vendorQuality.between(0,100)].copy()
    manifest=json.loads((root/'viewer/data/manifest.json').read_text())
    players={pid:p for g in manifest['games'] for pid,p in g['players'].items()}
    evidence_by_game={g['match']['id']:season_evidence(dict(g, players=players)) for g in manifest['games']}
    folds=[]; models={}; errors=[]
    for gid in sorted(shots.gameId.unique()):
        train=shots[shots.gameId!=gid]; test=shots[shots.gameId==gid]
        rates={pid:e['rate'] for pid,e in evidence_by_game[int(gid)].items() if e['rate'] is not None}
        model=fit(train, rates); models[int(gid)]=model
        y=test.vendorQuality.to_numpy()/100
        pred=np.clip(model.predict(test[SHOT_FEATURES].to_numpy(), test.shooter, test.three),0,1)
        baseline=test.region.map(train.groupby('region').vendorQuality.mean()).fillna(train.vendorQuality.mean()).to_numpy()/100
        old=ShotModel.fit(all_shots[all_shots.gameId!=gid]).predict(test)[0]
        errors.extend(abs(pred-y).tolist())
        folds.append(dict(gameId=int(gid),shots=len(test),mae=float(abs(pred-y).mean()),baselineMae=float(abs(baseline-y).mean()),oldModelMae=float(abs(old-y).mean()),threeMae=float(abs(pred[test.three]-y[test.three]).mean()),threeBias=float((pred[test.three]-y[test.three]).mean())))
    summary={key:float(np.mean([f[key] for f in folds])) for key in ['mae','baselineMae','oldModelMae','threeMae','threeBias']}
    enabled=summary['mae']<summary['baselineMae'] and summary['mae']<summary['oldModelMae']
    report=dict(target='SkillCorner SQ / 100',features=SHOT_FEATURES + ["season 3PA/FGA excluding displayed game where available; training-only fallback", "three-point indicator; defender gap saturated at 9 ft on threes"],shots=len(shots),folds=folds,summary=summary,enabled=enabled,absoluteError80=float(np.quantile(errors,.8)),scope='Release-score fit applied to current spacing; no gather or future motion projection. Separate three-point fit. Season profiles are retrospective, not pregame; minimum 20 other-game season three attempts for live threes. Residual error is held-out release error, not a calibrated live interval.')
    (root/'viewer/data/vendor-surrogate.json').write_text(json.dumps(report,indent=2))
    updated=0
    if enabled:
        manifest=json.loads((root/'viewer/data/manifest.json').read_text())
        for game in manifest['games']:
            gid=game['match']['id']; model=models[gid]
            train=shots[shots.gameId!=gid]
            lo=train[SHOT_FEATURES].min().to_numpy(); hi=train[SHOT_FEATURES].max().to_numpy()
            for entry in game['plays']:
                path=root/f"viewer/data/plays/{entry['id']}.json"; play=json.loads(path.read_text())
                rows=[]
                for frame in play['frames']:
                    shot=frame.get('shot') or frame.pop('unsupportedShot', None)
                    if not shot: continue
                    frame['shot']=shot
                    frame.pop('shotUnavailableReason', None)
                    evidence=evidence_by_game[gid].get(shot['shooter'], {})
                    if shot['pointsIfMade']==3 and evidence.get('attempts', 0)<20:
                        frame['unsupportedShot']=shot
                        frame['shot']=None
                        frame['shotUnavailableReason']='Insufficient player three-point evidence (fewer than 20 other-game season attempts)'
                        continue
                    x=features(frame,shot['shooter'])
                    if x is not None and x[0]<=32: rows.append((shot,x))
                if rows:
                    predictions=np.clip(model.predict(np.array([x for _,x in rows]), [shot["shooter"] for shot,_ in rows], [shot["pointsIfMade"]==3 for shot,_ in rows]),0,1)
                    for (shot,x),prob in zip(rows,predictions):
                        shot.setdefault('pooledMakeProbability',shot['makeProbability'])
                        shot['makeProbability']=round(float(prob),5)
                        shot['pooledProbability']=shot['makeProbability']
                        shot['fieldGoalValue']=round(float(prob)*shot['pointsIfMade'],4)
                        shot['source']='skillcorner-surrogate'
                        shot['extrapolated']=bool(np.any(np.array(x)<lo) or np.any(np.array(x)>hi))
                        if shot.get('secondChancePerMiss') is not None:
                            shot['secondChancePerShot']=round((1-float(prob))*shot['secondChancePerMiss'],4)
                            shot['shotPlusSecondChance']=round(shot['fieldGoalValue']+shot['secondChancePerShot'],4)
                        updated+=1
                path.write_text(json.dumps(play,separators=(',',':'),allow_nan=False))
    print(json.dumps(dict(**summary,enabled=enabled,updated=updated,shots=len(shots))))

if __name__=='__main__': main()
