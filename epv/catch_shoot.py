"""Pre-pass, conditional catch-and-shoot scenario; not a learned action policy."""
import copy
import json
from pathlib import Path
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from . import second_chance as rebounds
from .shooting import load_shots, location_is_three
from .vendor_surrogate import fit, features, season_evidence

def catch_shoot_value(make, points, orb, continuation):
    """Shot-only scoring plus expected field-goal rebound continuation; no fouls."""
    first=float(make)*points
    second=(1-float(make))*float(orb)*float(continuation)
    return dict(pps=round(first+second,4),firstChancePps=round(first,4),
                secondChanceValue=round(second,4),offensiveReboundProbability=round(float(orb),4))


def project_release(frame, option):
    clock=frame.get('shotClock')
    if clock is None or clock<=option['arrivalSeconds']+.5:
        return None
    state=dict(offense=copy.deepcopy(option['offense']), defense=copy.deepcopy(option['defense']),
               shotClock=clock-option['arrivalSeconds']-.5)
    player=next((p for p in state['offense'] if p[0]==option['player']),None)
    if player is None or len(state['defense'])!=5:return None
    nearest=min(state['defense'],key=lambda d:np.hypot(d[1]-player[1],d[2]-player[2]))
    delta=np.asarray(player[1:3])-nearest[1:3]
    gap=float(np.linalg.norm(delta))
    step=min(max(0,gap-2),12*(.5-.2))
    if gap>0:nearest[1:3]=(np.asarray(nearest[1:3])+delta*step/gap).tolist()
    return state


def main():
    root=Path(__file__).resolve().parents[1]
    manifest_path=root/'viewer/data/manifest.json'
    m=json.loads(manifest_path.read_text())
    shots=load_shots(root);shots=shots[shots.vendorQuality.between(0,100)]
    rt,_=rebounds.load_examples(root)
    total=0
    for game in m['games']:
        gid=game['match']['id']
        evidence=season_evidence(game)
        sq=fit(shots[shots.gameId!=gid],{p:e['rate'] for p,e in evidence.items() if e['rate'] is not None})
        reb,continuation=rebounds.fit(rt[rt.gameId!=gid])
        plays={};targets=[]
        for p in game['recordedPasses']:
            p.pop('catchShot',None)
            if not p.get('receiver'):continue
            pid=p['possession']
            if not (root/f'viewer/data/plays/{pid}.json').exists():continue
            if pid not in plays:plays[pid]=json.loads((root/f'viewer/data/plays/{pid}.json').read_text())
            prior=[f for f in plays[pid]['frames'] if f['frame']<p['start'] and p['start']-f['frame']<=10 and not f.get('reason') and f.get('geometry',{}).get('handler')==p['passer']]
            if not prior:continue
            frame=prior[-1];option=next((o for o in frame.get('passOptions',[]) if o['player']==p['receiver']),None)
            if not option:continue
            state=project_release(frame,option)
            if state is None:continue
            x=features(state,p['receiver']);r=rebounds.geometry(state,p['receiver'])
            if not x or r is None or x[0]>32:continue
            three=bool(location_is_three(x[0],x[2]))
            if three and evidence.get(p['receiver'],{}).get('attempts',0)<20:continue
            targets.append((p,x,r,three))
        # Forecast every supported perimeter passing option, not only recorded passes.
        for entry in game['plays']:
            pid=entry['id']
            path=root/f'viewer/data/plays/{pid}.json'
            if pid not in plays:plays[pid]=json.loads(path.read_text())
            for frame in plays[pid]['frames']:
                for option in frame.get('passOptions',[]):
                    option.pop('catchShot',None)
                    if frame.get('reason'):continue
                    state=project_release(frame,option)
                    if state is None:continue
                    player=option['player']
                    x=features(state,player)
                    if not x or x[0]>32 or not location_is_three(x[0],x[2]):continue
                    if evidence.get(player,{}).get('attempts',0)<20:continue
                    r=rebounds.geometry(state,player)
                    if r is None:continue
                    targets.append((option,x,r,True))
        if targets:
            q=np.clip(sq.predict([x for _,x,_,_ in targets],[p.get('receiver',p.get('player')) for p,_,_,_ in targets],[t for *_,t in targets]),0,1)
            orb=reb.predict_proba(pd.DataFrame([r for _,_,r,_ in targets])[rebounds.COLUMNS])[:,1]
            for (p,x,_,three),prob,o in zip(targets,q,orb):
                p['catchShot']=dict(**catch_shoot_value(prob,3 if three else 2,o,continuation),releaseDefenderFeet=round(x[1],2),
                                   releaseShotClock=round(x[3],2),releaseSeconds=.5,source='projected-catch-no-foul-v2')
                total+=1
        for pid,play in plays.items():
            (root/f'viewer/data/plays/{pid}.json').write_text(json.dumps(play,separators=(',',':'),allow_nan=False))
        print('Catch and shoot',gid,len(targets),flush=True)
    m['metrics']['catchShoot']=dict(forecasts=total,scope='Conditional on catch: SQ field-goal points plus field-goal rebound continuation only, no foul/FT value. Projected catch plus 0.5s release; nearest defender reacts after 0.2s, closes at 12 ft/s to 2 ft. Others stationary during release. Not validated C&S policy value.')
    manifest_path.write_text(json.dumps(m,separators=(',',':'),allow_nan=False))


if __name__=='__main__':
    with threadpool_limits(limits=2):main()
