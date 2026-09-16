"""Conservative backcut stress test for defensive position hints, not policy value."""
import argparse
import copy
import json
import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from .movement import ROOT, catch_features, supported, defensive_ideas
from .passing import pass_features, PASS_FEATURES
from .shooting import attach_predictions, EPV_SHOT_FEATURES
from .features import EPV_GEOMETRY_FEATURES

def response_pair(frame, candidate, receiver=None, length=0):
    """Two-second matched horizon; shift then cut then pass. No future frames."""
    holder=frame['geometry']['handler']
    if frame['shotClock']<=2 or frame['gameClock']<=2:return None
    pair=[]
    for moving in (False,True):
        state=copy.deepcopy(frame)
        state['shotClock']-=2;state['gameClock']-=2;state['frame']+=50
        if moving:
            next(p for p in state['defense'] if p[0]==candidate['player'])[1:3]=candidate['to'][:]
        if receiver is not None:
            cutter=next(p for p in state['offense'] if p[0]==receiver)
            start=np.array(cutter[1:3]);delta=np.array([-40.75,0])-start
            distance=np.linalg.norm(delta)
            if length and distance<length+2:return None
            if length:cutter[1:3]=(start+delta*length/distance).tolist()
            source=next(p for p in state['offense'] if p[0]==holder)
            flight=.12+np.linalg.norm(np.array(source[1:3])-cutter[1:3])/40
            shift=np.linalg.norm(np.array(candidate['to'])-candidate['origin'])/12
            if .2+shift+length/10+flight>2:return None
            pf=pass_features(state,holder,receiver)
            if pf is None:return None
        else:pf=None
        features=catch_features(state,copy.deepcopy(state),receiver or holder)
        if features is None:return None
        pair.append({'state':features,'pass':pf})
    return pair

def robust_reduction(pairs):
    """Reject any cut made easier; headline is the worst-response envelope gain."""
    if len(pairs)<2 or not np.isfinite(pairs).all():return None
    if any(after>before+.005 for before,after in pairs[1:]):return None
    before=max(a for a,b in pairs);after=max(b for a,b in pairs)
    gain=before-after
    return (before,after,gain) if gain>=.01 else None

def screen_defense(game,data,models):
    output={};tested=0;rejected=0
    for pid,times in data['plays'].items():
        play=json.loads((ROOT/f'viewer/data/plays/{pid}.json').read_text())
        frames={str(f['frame']):f for f in play['frames']}
        rows=[];refs=[]
        for time,candidates in times.items():
            f=frames[time];holder=f['geometry']['handler']
            h=next(p for p in f['offense'] if p[0]==holder)
            if h[1]>-10 or any(p[1]>=-1 for p in f['offense']+f['defense']):continue
            for c in candidates:
                d=next(p for p in f['defense'] if p[0]==c['player'])
                if d[1]>h[1]+2 or c['to'][0]>h[1]+2:continue
                c={**c,'origin':d[1:3]};tested+=1
                scenarios=[(None,0)]+[(p[0],length) for p in f['offense'] if p[0]!=holder for length in (0,4,8)
                    if not length or np.hypot(p[1]+40.75,p[2])>=length+2]
                batch=[]
                for receiver,length in scenarios:
                    pair=response_pair(f,c,receiver,length)
                    # Never interpret an unscorable offensive response as safe.
                    if pair is None or not all(supported(r['state'],models['bounds']) for r in pair):break
                    batch.extend(pair)
                if len(batch)!=len(scenarios)*2:rejected+=1;continue
                refs.append((time,c,len(rows),len(batch)));rows.extend(batch)
        if not rows:continue
        table=attach_predictions(pd.DataFrame([r['state'] for r in rows]),models['shot'])
        values=np.maximum(0,models['epv'].predict(table[EPV_GEOMETRY_FEATURES+EPV_SHOT_FEATURES]))
        indices=[i for i,r in enumerate(rows) if r['pass'] is not None]
        if indices:
            risk=models['pass'].predict_proba(pd.DataFrame([rows[i]['pass'] for i in indices])[PASS_FEATURES])[:,1]
            values[indices]*=1-risk
        for time,c,start,n in refs:
            pairs=values[start:start+n].reshape(-1,2)
            result=robust_reduction(pairs)
            if result is None:rejected+=1;continue
            before,after,gain=map(float,result)
            c.update(before=before,after=after,gain=gain,low=gain,high=gain,responseChecked=True,
                     responses=[dict(before=float(a),after=float(b)) for a,b in pairs])
            output.setdefault(pid,{}).setdefault(time,[]).append(c)
    return dict(version=2,plays=output,count=sum(len(c) for t in output.values() for c in t.values()),tested=tested,rejected=rejected,
                note='Two-second matched horizon: hold plus every off-ball player cutting 4/8 ft toward rim, then pass with turnover risk. Reject if any cut gains >0.005 EPV from the shift or any response is unsupported. Others fixed; no defensive recovery modeled. Experimental stress test, not validated policy value.')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--game',type=int,required=True);parser.add_argument('--model-signature',required=True);args=parser.parse_args()
    game=next(g for g in json.loads((ROOT/'viewer/data/manifest.json').read_text())['games'] if g['match']['id']==args.game)
    models=joblib.load(ROOT/f'.cache/epv/movement-{args.game}-{args.model_signature}.joblib')
    assert args.game not in models['trainingGames']
    path=ROOT/f'viewer/data/movement/{args.game}-defense.json'
    data=screen_defense(game,defensive_ideas(game,models),models)
    path.write_text(json.dumps(data,separators=(',',':'),allow_nan=False))
    print(args.game,data['tested'],data['count'],'response-screened candidates',flush=True)

if __name__=='__main__':
    with threadpool_limits(limits=2):main()
