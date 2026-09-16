"""Held-out move-then-pass experiment, conditional on retaining the ball while waiting.

Compare the same receiver staying or moving, under hold/momentum/close responses.
Both branches are scored at the later projected catch time. No future replay states
or outcomes enter a simulation. This is a scenario sensitivity test, not policy value.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from .build import estimator, weights
from .features import EPV_GEOMETRY_FEATURES, spatial_features
from .passing import PASS_FEATURES, fit_pass_model, load_passes, pass_features, project_catch, velocities
from .pass_timing import TimingModel, load_timing
from .shooting import EPV_SHOT_FEATURES, ShotModel, attach_predictions, load_shots, location_is_three, shot_region

ROOT=Path(__file__).resolve().parents[1]
RESPONSES=('hold','momentum','close')
MIN_GAIN=.01

def projected_state(frame, previous, receiver, destination, seconds, response):
    """Holder/other teammates hold; receiver stops at destination; defenders respond."""
    state=copy.deepcopy(frame)
    state['frame']=frame['frame']+seconds*25
    state['shotClock']=frame['shotClock']-seconds
    state['gameClock']=frame['gameClock']-seconds
    if min(state['shotClock'],state['gameClock'])<=0:return None
    source=next(p for p in frame['offense'] if p[0]==receiver)
    nearest=min(frame['defense'],key=lambda d:np.linalg.norm(np.array(d[1:3])-source[1:3]))[0]
    velocity=velocities(frame,previous)
    for d in state['defense']:
        start=np.array(d[1:3],float)
        v=np.array(velocity.get(d[0],np.zeros(2)),float)
        speed=np.linalg.norm(v)
        if speed>12:v*=12/speed
        if response=='hold':end=start
        elif response=='close' and d[0]==nearest:
            delta=np.array(destination)-start
            length=np.linalg.norm(delta)
            end=start+delta*min(1,12*max(0,seconds-.2)/max(length,1e-9))
        else:end=start+v*seconds
        d[1:3]=np.clip(end,[-45.932,-24.606],[45.932,24.606]).tolist()
    next(p for p in state['offense'] if p[0]==receiver)[1:3]=list(destination)
    # Discard recorded action/forecast fields from the hypothetical state.
    for key in ('passOptions','shot','actionDefense','stealForecast','blockForecast'):
        state.pop(key,None)
    return state

def catch_features(state, history, receiver):
    for f in (state,history):
        p=next(p for p in f['offense'] if p[0]==receiver)
        f['ball']=[p[1],p[2],3,1,0]
    result=spatial_features(state,history)
    if result is None or result[1]['handler']!=receiver:return None
    features=result[0]
    p=next(p for p in state['offense'] if p[0]==receiver)
    features.update(shooter=receiver,holder_x=p[1],holder_y=p[2],shot_distance=features['handler_rim_distance'],shot_defender=features['nearest_defender'],shot_abs_y=abs(p[2]))
    features['three']=bool(location_is_three(features['shot_distance'],features['shot_abs_y']))
    features['region']=str(shot_region(np.array([features['shot_distance']]),np.array([features['three']]))[0])
    return features

def simulate_pair(frame, previous, receiver, destination, move_seconds, response, timing):
    source=next(p for p in frame['offense'] if p[0]==receiver)
    destinations=(list(source[1:3]),destination)
    release=[]
    for target in destinations:
        state=projected_state(frame,previous,receiver,target,move_seconds,response)
        history=projected_state(frame,previous,receiver,target,max(0,move_seconds-.2),response)
        if state is None or history is None:return None
        pf=pass_features(state,frame['geometry']['handler'],receiver)
        catch=project_catch(state,history,receiver,timing)
        if pf is None or catch is None:return None
        release.append((pf,catch[0]))
    horizon=move_seconds+max(r[1] for r in release)
    pair=[]
    for target,(pf,flight) in zip(destinations,release):
        state=projected_state(frame,previous,receiver,target,horizon,response)
        history=projected_state(frame,previous,receiver,target,horizon-.2,response)
        if state is None or history is None:return None
        features=catch_features(state,history,receiver)
        if features is None:return None
        pair.append({'state':features,'pass':pf,'seconds':horizon,'flight':flight})
    return pair

def summarize(values):
    if len(values)!=3 or not all(np.isfinite(v['gain']) for v in values):return None
    low=min(v['gain'] for v in values)
    if low<MIN_GAIN:return None
    return {'gain':float(np.mean([v['gain'] for v in values])),
            'low':float(low),'high':float(max(v['gain'] for v in values)), 'responses':values}

def models_for(gid,states,shots,passes,timings,signature):
    path=ROOT/f'.cache/epv/movement-{gid}-{signature}.joblib'
    if path.exists():return joblib.load(path)
    parts=[]
    for inner in sorted(states.gameId.unique()):
        if inner==gid:continue
        model=ShotModel.fit(shots[~shots.gameId.isin([gid,inner])])
        parts.append(attach_predictions(states[(states.gameId==inner)&states.train],model))
    train=pd.concat(parts,ignore_index=True)
    assert gid not in set(train.gameId)
    epv=estimator('points')
    epv.fit(train[EPV_GEOMETRY_FEATURES+EPV_SHOT_FEATURES],train.points,sample_weight=weights(train))
    bounds={k:(float(train[k].quantile(.005)),float(train[k].quantile(.995))) for k in ('shot_clock','handler_rim_distance','nearest_defender','teammate_spacing')}
    bundle={'epv':epv,'shot':ShotModel.fit(shots[shots.gameId!=gid]),
            'pass':fit_pass_model(passes[passes.gameId!=gid]),'timing':TimingModel.fit(timings[timings.gameId!=gid]),
            'bounds':bounds,'trainingGames':sorted(int(g) for g in train.gameId.unique())}
    joblib.dump(bundle,path)
    return bundle

def supported(features,bounds):
    return all(np.isfinite(features[k]) and lo<=features[k]<=hi for k,(lo,hi) in bounds.items())

def defensive_shift(frame, defender, dx, dy):
    """Same-clock position sensitivity; other players fixed, not a movement policy."""
    state=copy.deepcopy(frame)
    player=next((p for p in state['defense'] if p[0]==defender),None)
    if player is None:return None
    player[1]+=dx;player[2]+=dy
    if abs(player[1])>45 or abs(player[2])>24:return None
    if any(p[0]!=defender and np.hypot(p[1]-player[1],p[2]-player[2])<2 for p in state['defense']):return None
    if any(np.hypot(p[1]-player[1],p[2]-player[2])<1 for p in state['offense']):return None
    return catch_features(state,copy.deepcopy(state),frame['geometry']['handler'])

def defensive_ideas(game, models):
    output={};count=0
    for entry in game['plays']:
        play=json.loads((ROOT/f"viewer/data/plays/{entry['id']}.json").read_text())
        rows=[];refs=[]
        for frame in play['frames']:
            if frame['frame']%25 or frame.get('reason') or not frame.get('geometry',{}).get('handler'):continue
            holder=frame['geometry']['handler']
            base=catch_features(copy.deepcopy(frame),copy.deepcopy(frame),holder)
            if base is None or not supported(base,models['bounds']):continue
            start=len(rows);rows.append(base)
            for p in frame['defense']:
                if not p[3]:continue
                for length in (2,4):
                    for dx,dy in ((length,0),(-length,0),(0,length),(0,-length)):
                        features=defensive_shift(frame,p[0],dx,dy)
                        if features is None or not supported(features,models['bounds']):continue
                        refs.append((frame,p,[p[1]+dx,p[2]+dy],start,len(rows)))
                        rows.append(features)
        if not refs:continue
        table=attach_predictions(pd.DataFrame(rows),models['shot'])
        values=np.maximum(0,models['epv'].predict(table[EPV_GEOMETRY_FEATURES+EPV_SHOT_FEATURES]))
        for frame,p,target,a,b in refs:
            reduction=float(values[a]-values[b])
            if reduction<MIN_GAIN:continue
            result=dict(player=p[0],to=target,frame=frame['frame'],gain=reduction,low=reduction,high=reduction,
                        before=float(values[a]),after=float(values[b]),side='defense',origin=p[1:3],ball=frame['ball'][:2])
            output.setdefault(entry['id'],{}).setdefault(str(frame['frame']),[]).append(result);count+=1
    return {'plays':output,'count':count,'note':'Same-clock positional sensitivity: 2/4 ft cardinal shifts, others fixed. Not a causal policy benefit; travel time and offensive response are not modeled.'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--game',type=int);args=parser.parse_args()
    states=pd.read_pickle(ROOT/'artifacts/states.pkl')
    shots=load_shots(ROOT);passes,_=load_passes(ROOT);timings=load_timing(ROOT)
    signature=hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in ['epv/movement.py','epv/build.py','epv/passing.py','epv/shooting.py'])+str((ROOT/'artifacts/states.pkl').stat().st_mtime_ns).encode()).hexdigest()[:12]
    manifest=json.loads((ROOT/'viewer/data/manifest.json').read_text())
    out=ROOT/'viewer/data/movement';out.mkdir(exist_ok=True)
    reports=[]
    for game in manifest['games']:
        gid=game['match']['id']
        if args.game and gid!=args.game:continue
        candidates=json.loads((ROOT/f'artifacts/movement-candidates/{gid}.json').read_text())
        models=models_for(gid,states,shots,passes,timings,signature)
        plays={}
        rows=[];refs=[];rejected=0
        for candidate in candidates:
            pid=candidate['playId']
            if pid not in plays:plays[pid]=json.loads((ROOT/f'viewer/data/plays/{pid}.json').read_text())
            play=plays[pid];i=candidate['index'];frame=play['frames'][i];previous=play['frames'][i-1] if i else None
            batch=[]
            for response in RESPONSES:
                pair=simulate_pair(frame,previous,candidate['player'],candidate['to'],candidate['seconds'],response,models['timing'])
                if pair is None or not all(supported(p['state'],models['bounds']) for p in pair):break
                batch.extend(pair)
            if len(batch)!=6:rejected+=1;continue
            refs.append((candidate,frame,len(rows)));rows.extend(batch)
        output={}
        if rows:
            table=attach_predictions(pd.DataFrame([r['state'] for r in rows]),models['shot'])
            values=np.maximum(0,models['epv'].predict(table[EPV_GEOMETRY_FEATURES+EPV_SHOT_FEATURES]))
            risks=models['pass'].predict_proba(pd.DataFrame([r['pass'] for r in rows])[PASS_FEATURES])[:,1]
            for candidate,frame,start in refs:
                scenarios=[]
                for j,response in enumerate(RESPONSES):
                    a=start+2*j;b=a+1
                    stay=(1-risks[a])*values[a];move=(1-risks[b])*values[b]
                    scenarios.append({'response':response,'stay':float(stay),'move':float(move),'gain':float(move-stay),
                                      'stayTov':float(risks[a]),'moveTov':float(risks[b]),'seconds':rows[a]['seconds']})
                result=summarize(scenarios)
                if result:
                    result.update(player=candidate['player'],to=candidate['to'],seconds=candidate['seconds'],frame=frame['frame'],source=candidate.get('source','grid'))
                    output.setdefault(candidate['playId'],{}).setdefault(str(frame['frame']),[]).append(result)
        accepted=sum(len(v) for p in output.values() for v in p.values())
        report={'gameId':gid,'trainingGames':models['trainingGames'],'candidates':len(candidates),'unsupported':rejected,'evaluated':len(refs),'accepted':accepted}
        (out/f'{gid}.json').write_text(json.dumps({'version':1,'report':report,'plays':output},separators=(',',':'),allow_nan=False))
        defense=defensive_ideas(game,models)
        from .defensive_responses import screen_defense
        defense=screen_defense(game,defense,models)
        (out/f'{gid}-defense.json').write_text(json.dumps(defense,separators=(',',':'),allow_nan=False))
        report['defensiveShifts']=defense['count']
        reports.append(report);print(report,flush=True)
    report_name=f'movement-validation-{args.game}.json' if args.game else 'movement-validation.json'
    (ROOT/'artifacts'/report_name).write_text(json.dumps({'reports':reports,'minimumGain':MIN_GAIN,'note':'Scenario consistency only; movement-policy benefit has not been validated against outcomes.'},indent=2))

if __name__=='__main__':
    with threadpool_limits(limits=2):main()
