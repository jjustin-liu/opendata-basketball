"""Joint six-outcome model: no credited steal / one of five defenders, next 2 s."""
import csv
import json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp
from threadpoolctl import threadpool_limits
from .defense import load_counts, load_season, fit_priors
from .passing import velocities, lane_weights

FEATURES=['ball_distance','holder_distance','nearest_receiver_distance','maximum_lane_proximity','closing_speed','steals_per_100_prior']


def geometry(frame, previous):
    holder=frame.get('geometry',{}).get('handler')
    off={p[0]:np.array(p[1:3],float) for p in frame['offense']}
    if holder not in off or len(frame['defense'])!=5 or not frame.get('ball'):
        return None
    defenders=np.array([p[1:3] for p in frame['defense']],float)
    other=[p for p in off if p!=holder]
    if not other:return None
    lane=np.max([lane_weights(frame,holder,p) for p in other],axis=0)
    v=velocities(frame,previous)
    rows=[]
    for i,p in enumerate(frame['defense']):
        delta=off[holder]-defenders[i];distance=np.linalg.norm(delta)
        relative=v.get(p[0],np.zeros(2))-v.get(holder,np.zeros(2))
        closing=float(relative@delta/max(distance,.1))
        rows.append([np.linalg.norm(defenders[i]-np.array(frame['ball'][:2])),distance,min(np.linalg.norm(defenders[i]-off[k]) for k in other),lane[i],closing,0])
    return np.array(rows)


class JointStealModel:
    def __init__(self, regularization=.01):
        self.regularization=regularization

    def fit(self,x,y):
        self.mean=x.mean(axis=(0,1));self.scale=x.std(axis=(0,1));self.scale[self.scale<1e-6]=1
        z=np.concatenate([np.ones((*x.shape[:2],1)),(x-self.mean)/self.scale],axis=2)
        def objective(w):
            logits=np.column_stack([np.zeros(len(z)),z@w])
            norm=logsumexp(logits,axis=1)
            p=np.exp(logits-norm[:,None]);p[np.arange(len(y)),y]-=1
            loss=np.mean(norm-logits[np.arange(len(y)),y])+self.regularization*np.sum(w[1:]**2)/2
            grad=np.einsum('nd,ndk->k',p[:,1:],z)/len(z);grad[1:]+=self.regularization*w[1:]
            return loss,grad
        initial=np.zeros(z.shape[-1]);initial[0]=np.log(max((y>0).mean(),.0001)/5)
        result=minimize(objective,initial,jac=True,method='L-BFGS-B')
        if not result.success:raise RuntimeError(result.message)
        self.coef=result.x
        return self

    def predict(self,x):
        z=np.concatenate([np.ones((*x.shape[:2],1)),(x-self.mean)/self.scale],axis=2)
        logits=np.column_stack([np.zeros(len(z)),z@self.coef])
        return np.exp(logits-logsumexp(logits,axis=1)[:,None])


def with_priors(x,ids,gids,counts,excluded=(),season=None):
    result=x.copy()
    for gid in np.unique(gids):
        profiles,pool=fit_priors(counts,set(excluded)|{int(gid)},season=season)
        for i in np.flatnonzero(gids==gid):
            result[i,:,-1]=[profiles.get(int(pid),{}).get('priorPer100',pool) for pid in ids[i]]
    return result


def score(y,p):
    target=np.eye(6)[y]
    return dict(logLoss=float(-np.log(np.maximum(p[np.arange(len(y)),y],1e-12)).mean()),brier=float(((p-target)**2).sum(axis=1).mean()),anyStealBrier=float(np.mean(((1-p[:,0])-(y>0))**2)))


def main(kind='steal'):
    if kind not in ('steal','block'): raise ValueError(kind)
    root=Path(__file__).resolve().parents[1];counts=load_counts(root,kind)
    manifest=json.loads((root/'viewer/data/manifest.json').read_text())
    aliases={int(r['player_id']):int(r['canonical_player_id']) for r in csv.DictReader((root/'data/player_id_aliases.csv').open())}
    # Only steals have an official season line wired in; blocks stay tracking-only.
    season=None
    if kind=='steal':
        names={int(pid):player['name'] for game in manifest['games'] for pid,player in game['players'].items()}
        season,_=load_season(root,names)
    xs=[];ys=[];ids=[];gids=[];references=[];sample=[]
    for game in manifest['games']:
        gid=game['match']['id']
        events=json.loads((root/f'data/matches/{gid}/{gid}_dynamic_events.json').read_text())
        steals={}
        targets = events['turnovers'] if kind == 'steal' else [dict(t, frame=t['endFrame'], gameClock=t['endGameClock'], stealerId=t.get('blockerId')) for t in events['shots'] if t.get('blocked') and t.get('endFrame') is not None]
        for t in sorted(targets,key=lambda t:t['frame']):
            if t.get('stealerId') is not None:
                steals.setdefault(t['possessionId'],[]).append(t)
        for entry in game['plays']:
            path=root/f"viewer/data/plays/{entry['id']}.json";play=json.loads(path.read_text())
            last_sample=-float('inf')
            for j,f in enumerate(play['frames']):
                if f.get('reason'):continue
                x=geometry(f,play['frames'][j-1] if j else None)
                if x is None:continue
                if kind == 'block':
                    holder=next(p for p in f['offense'] if p[0]==f['geometry']['handler'])
                    rim=np.array([-40.75,0])
                    extra=np.array([[np.linalg.norm(np.array(p[1:3])-rim),np.linalg.norm(np.array(holder[1:3])-rim),(game['players'].get(str(p[0]),{}).get('heightCm') or 200)/100] for p in f['defense']])
                    x=np.column_stack([x[:,:-1],extra,x[:,-1]])
                people=[p[0] for p in f['defense']]
                future=[t for t in steals.get(entry['id'],[]) if t['frame']>f['frame'] and 0<=f['gameClock']-t['gameClock']<=2]
                outcome=0
                if future:
                    pid=aliases.get(future[0]['stealerId'],future[0]['stealerId'])
                    if pid not in people:continue
                    outcome=people.index(pid)+1
                sample.append(f['frame']-last_sample>=25)
                if sample[-1]:last_sample=f['frame']
                xs.append(x);ys.append(outcome);ids.append(people);gids.append(gid);references.append((path,j))
    x=np.array(xs);y=np.array(ys);ids=np.array(ids);gids=np.array(gids);sample=np.array(sample)
    folds=[];predictions=np.zeros((len(x),6))
    with threadpool_limits(limits=1):
        for gid in np.unique(gids):
            train=(gids!=gid)&sample;test=(gids==gid)&sample;alltest=gids==gid
            z=with_priors(x,ids,gids,counts,{int(gid)},season)
            model=JointStealModel().fit(z[train],y[train])
            p=model.predict(z[test]);predictions[alltest]=model.predict(z[alltest])
            rate=float((y[train]>0).mean());baseline=np.full_like(p,rate/5);baseline[:,0]=1-rate
            folds.append(dict(gameId=int(gid),states=int(test.sum()),stealStates=int((y[test]>0).sum()),model=score(y[test],p),baseline=score(y[test],baseline)))
    summary={kind:{key:float(np.mean([f[kind][key] for f in folds])) for key in ['logLoss','brier','anyStealBrier']} for kind in ['model','baseline']}
    enabled=all(summary['model'][k]<summary['baseline'][k] for k in ['logLoss','brier','anyStealBrier'])
    report=dict(enabled=enabled,horizonSeconds=2,features=FEATURES,folds=folds,summary=summary,sampledStates=int(sample.sum()),positiveStates=int(((y>0)&sample).sum()),scope='Observational next-two-game-clock-second credited steal, not forced-pass risk. Six mutually exclusive outcomes. Whole-game holdouts; training player priors exclude both the evaluation game and their own game. Evaluation sampled at most once per recording second. Sparse positives and repeated tuning limit confidence.')
    if kind == 'block':
        report['features']=FEATURES[:-1]+['defender_rim_distance','holder_rim_distance','listed_height_metres','blocks_per_100_prior']
        report['scope']=report['scope'].replace('steal','block')
        report=json.loads(json.dumps(report).replace('stealStates','blockStates').replace('anyStealBrier','anyBlockBrier'))
    (root/f'viewer/data/{kind}-probability.json').write_text(json.dumps(report,indent=2))
    # Save estimates even when rejected, but mark them explicitly experimental and
    # keep them out of the live UI unless the held-out gate passes.
    current=None;play=None
    for (path,j),p in zip(references,predictions):
        if path!=current:
            if current:current.write_text(json.dumps(play,separators=(',',':'),allow_nan=False))
            current=path;play=json.loads(path.read_text())
        play['frames'][j][kind+'Forecast']={'enabled':enabled,'horizonSeconds':2,'no'+kind.title()+'Probability':float(p[0]),'any'+kind.title()+'Probability':float(1-p[0]),'defenders':[dict(player=int(pid),probability=float(prob)) for pid,prob in zip([a[0] for a in play['frames'][j]['defense']],p[1:])]}
    if current:current.write_text(json.dumps(play,separators=(',',':'),allow_nan=False))
    print(json.dumps(dict(enabled=enabled,summary=summary,sampledStates=int(sample.sum()),positiveStates=int(((y>0)&sample).sum()))))

if __name__=='__main__':main()
