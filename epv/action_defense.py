"""Conditional-on-observed-action defender attribution; not a causal action model."""
import csv,gzip,json
from pathlib import Path
from collections import Counter
import joblib
import numpy as np
from threadpoolctl import threadpool_limits
from .defense import load_counts,fit_priors
from .passing import load_passes
from .steal_probability import JointStealModel,with_priors,score


def action_features(frame,actor,kind,profiles,receiver=None):
    off={p[0]:np.array(p[1:3],float) for p in frame['offense']}
    if actor not in off or len(frame['defense'])!=5:return None
    a=off[actor];rim=np.array([-40.75,0.])
    if kind=='steal' and (receiver not in off or receiver==actor):return None
    b=off[receiver] if kind=='steal' else rim
    delta=b-a;length=np.linalg.norm(delta)
    if length<.1:return None
    rows=[]
    for p in frame['defense']:
        d=np.array(p[1:3],float);t=float((d-a)@delta/(length*length));q=np.clip(t,0,1)
        separation=float(np.linalg.norm(d-a));clearance=float(np.linalg.norm(d-(a+q*delta)))
        height=(profiles.get(str(p[0]),{}).get('heightCm') or 200)/100
        rows.append([separation,clearance,t,np.linalg.norm(d-b),length,np.linalg.norm(d-rim),height,0])
    return np.array(rows)


def training(root,manifest):
    cache=root/'.cache/epv/action_defense_v1.joblib'
    if cache.exists():return joblib.load(cache)
    aliases={int(r['player_id']):int(r['canonical_player_id']) for r in csv.DictReader((root/'data/player_id_aliases.csv').open())}
    canon=lambda p:aliases.get(p,p)
    accepted,_=load_passes(root);accepted={r.passId:int(r.receiver) for r in accepted.itertuples()}
    output={k:dict(x=[],y=[],ids=[],gids=[]) for k in ['steal','block']};audit=Counter()
    for game in manifest['games']:
        gid=game['match']['id'];folder=root/f'data/matches/{gid}'
        events=json.loads((folder/f'{gid}_dynamic_events.json').read_text());meta=json.loads((folder/f'{gid}_game_data.json').read_text())
        possessions={p['id']:p for p in events['possessions']}
        actions=[('steal',p) for p in events['passes'] if p['id'] in accepted]+[('block',p) for p in events['shots']]
        needed={p['startFrame']-1 for _,p in actions};snapshots={}
        with gzip.open(root/f'.cache/tracking/{gid}_tracking_data.jsonl.gz','rt') as f:
            for line in f:
                raw=json.loads(line)
                if raw['frameIdx'] in needed:snapshots[raw['frameIdx']]=raw
        for kind,event in actions:
            raw=snapshots.get(event['startFrame']-1);pos=possessions.get(event['possessionId'])
            if raw is None or pos is None:continue
            sign=1 if pos['leftHoop'] else -1;home=event['offTeamId']==meta['homeTeam']['teamId']
            side=lambda name:[[canon(p['playerId']),p['xyz'][0]*sign,p['xyz'][1]*sign] for p in raw[name]]
            frame={'offense':side('homePlayers' if home else 'awayPlayers'),'defense':side('awayPlayers' if home else 'homePlayers')}
            actor=canon(event['passerId'] if kind=='steal' else event['shooterId'])
            receiver=accepted.get(event['id']) if kind=='steal' else None
            credited=None
            if kind=='block':
                if event.get('blocked') and event.get('blockerId') is None:audit['unknown_blocker']+=1;continue
                credited=canon(event.get('blockerId')) if event.get('blocked') else None
            elif event.get('turnover'):
                candidates=[t for t in events['turnovers'] if t['possessionId']==event['possessionId'] and t.get('touchId')==event.get('touchId') and event['startFrame']<=t['frame']<=event['endFrame']]
                if len(candidates)!=1:audit['ambiguous_pass_turnover']+=1;continue
                credited=canon(candidates[0].get('stealerId'))
            x=action_features(frame,actor,kind,game['players'],receiver)
            if x is None:continue
            ids=[p[0] for p in frame['defense']]
            if credited is not None and credited not in ids:audit['credited_off_court']+=1;continue
            out=output[kind];out['x'].append(x);out['y'].append(ids.index(credited)+1 if credited is not None else 0);out['ids'].append(ids);out['gids'].append(gid)
        print('Action training',gid,flush=True)
    output={k:{field:np.array(v) for field,v in data.items()} for k,data in output.items()}
    joblib.dump((output,dict(audit)),cache);return output,dict(audit)


def evaluate(data,counts,regularization=.01):
    x,y,ids,gids=(data[k] for k in ['x','y','ids','gids']);folds=[];models={}
    for gid in np.unique(gids):
        train=gids!=gid;test=~train;z=with_priors(x,ids,gids,counts,{int(gid)})
        model=JointStealModel(regularization).fit(z[train],y[train]);p=model.predict(z[test]);rate=(y[train]>0).mean()
        base=np.full_like(p,rate/5);base[:,0]=1-rate
        folds.append(dict(gameId=int(gid),actions=int(test.sum()),positives=int((y[test]>0).sum()),model=score(y[test],p),baseline=score(y[test],base)))
        models[int(gid)]=model
    summary={kind:{key:float(np.mean([f[kind][key] for f in folds])) for key in ['logLoss','brier','anyStealBrier']} for kind in ['model','baseline']}
    enabled=all(summary['model'][key]<summary['baseline'][key] for key in summary['model'])
    return models,dict(enabled=enabled,regularization=regularization,actions=len(y),positiveActions=int((y>0).sum()),folds=folds,summary=summary)


def main():
    root=Path(__file__).resolve().parents[1];manifest=json.loads((root/'viewer/data/manifest.json').read_text())
    data,audit=training(root,manifest);models={};reports={};counts={}
    with threadpool_limits(limits=1):
        for kind in ['steal','block']:
            counts[kind]=load_counts(root,kind);models[kind],reports[kind]=evaluate(data[kind],counts[kind],.1 if kind=='steal' else .01)
        report=dict(models=reports,audit=audit,scope='One pre-action tracking state per observed shot/pass. Six exclusive outcomes per action. Other-game priors exclude evaluation game and own training game. Pass sample retains conservative early-flight receiver reconstruction and its selection bias. Forecasts describe similar observed actions, not validated forced-action effects. None class for passes includes uncredited/non-steal turnovers; interception is not all pass TO.')
        (root/'viewer/data/action-defense.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({k:{key:v for key,v in r.items() if key!='folds'} for k,r in reports.items()}),flush=True)
        for game in manifest['games']:
            gid=game['match']['id'];priors={k:fit_priors(counts[k],{gid}) for k in counts}
            for entry in game['plays']:
                path=root/f"viewer/data/plays/{entry['id']}.json";play=json.loads(path.read_text());rows={k:[] for k in counts};refs={k:[] for k in counts}
                for f in play['frames']:
                    f['actionDefense']={'passes':[]}
                    if f.get('reason') or not f.get('geometry'):continue
                    actor=f['geometry']['handler'];f['actionDefense']={'passes':[]}
                    for kind in counts:
                        if not reports[kind]['enabled']:continue
                        receivers=[o['player'] for o in f.get('passOptions',[])] if kind=='steal' else [None]
                        for receiver in receivers:
                            x=action_features(f,actor,kind,game['players'],receiver)
                            if x is None:continue
                            if kind=='block' and x[0,4]>32:continue
                            profile,pool=priors[kind];x[:,-1]=[profile.get(p[0],{}).get('priorPer100',pool) for p in f['defense']]
                            rows[kind].append(x);refs[kind].append((f,receiver))
                for kind in counts:
                    if not rows[kind]:continue
                    predictions=models[kind][gid].predict(np.array(rows[kind]))
                    for (f,receiver),p in zip(refs[kind],predictions):
                        forecast=dict(enabled=True,noEventProbability=float(p[0]),anyEventProbability=float(1-p[0]),defenders=[dict(player=d[0],probability=float(prob)) for d,prob in zip(f['defense'],p[1:])])
                        if kind=='block':f['actionDefense']['shot']=forecast
                        else:f['actionDefense']['passes'].append(dict(forecast,receiver=receiver))
                path.write_text(json.dumps(play,separators=(',',':'),allow_nan=False))

if __name__=='__main__':main()
