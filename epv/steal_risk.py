"""Test a localized steal prior against the existing selected-pass model."""
import json
from pathlib import Path
import numpy as np
from sklearn.metrics import log_loss, brier_score_loss
from .defense import annotate, fit_priors
from .passing import load_passes, fit_pass_model, PASS_FEATURES, pass_features, lane_weights

FEATURE='lane_steal_prior'


def threat(ids, weights, profiles, pool):
    return sum(w*(profiles.get(int(pid),{}).get('priorPer100',pool)-pool) for pid,w in zip(ids,weights))


def add_feature(table, counts, excluded):
    result=table.copy()
    values={}
    for gid,group in table.groupby('gameId'):
        profiles,pool=fit_priors(counts,set(excluded)|{int(gid)})
        for index,row in group.iterrows():
            values[index]=threat(row.defenderIds,row.defenderLaneWeights,profiles,pool)
    result[FEATURE]=[values[i] for i in result.index]
    return result


def main():
    root=Path(__file__).resolve().parents[1]
    counts=annotate(root)
    table,_=load_passes(root)
    folds=[]; models={}
    for gid in sorted(table.gameId.unique()):
        train=add_feature(table[table.gameId!=gid],counts,{int(gid)})
        test=add_feature(table[table.gameId==gid],counts,{int(gid)})
        base=fit_pass_model(train)
        model=fit_pass_model(train,PASS_FEATURES+[FEATURE])
        old=base.predict_proba(test[PASS_FEATURES])[:,1]
        new=model.predict_proba(test[PASS_FEATURES+[FEATURE]])[:,1]
        folds.append(dict(gameId=int(gid),passes=len(test),oldLogLoss=log_loss(test.turnover,old),newLogLoss=log_loss(test.turnover,new),oldBrier=brier_score_loss(test.turnover,old),newBrier=brier_score_loss(test.turnover,new),coefficient=float(model[-1].coef_[0][-1])))
        models[int(gid)]=model
    summary={k:float(np.mean([f[k] for f in folds])) for k in ['oldLogLoss','newLogLoss','oldBrier','newBrier']}
    # Require both proper scoring rules to improve. Negative learned coefficients
    # would contradict the intended threat interpretation; do not deploy those.
    enabled=summary['newLogLoss']<summary['oldLogLoss'] and summary['newBrier']<summary['oldBrier'] and all(f['coefficient']>=0 for f in folds)
    report=dict(enabled=enabled,folds=folds,summary=summary,feature=FEATURE,scope='Outer held-out game excluded from every prior; each training row also excludes its own game. Retrospective other-game priors, not chronological forecasts. Fixed 100-possession shrinkage and 4-ft lane decay. Steal rate does not change physical reach or speed.')
    (root/'viewer/data/steal-risk.json').write_text(json.dumps(report,indent=2))
    if enabled:
        import pandas as pd
        manifest=json.loads((root/'viewer/data/manifest.json').read_text())
        for game in manifest['games']:
            gid=game['match']['id']; profiles,pool=fit_priors(counts,{gid})
            for entry in game['plays']:
                path=root/f"viewer/data/plays/{entry['id']}.json";play=json.loads(path.read_text())
                rows=[]; options=[]
                for frame in play['frames']:
                    holder=frame.get('geometry',{}).get('handler')
                    for option in frame.get('passOptions',[]):
                        f=pass_features(frame,holder,option['player'])
                        if f is None: continue
                        f[FEATURE]=threat([d[0] for d in frame['defense']],lane_weights(frame,holder,option['player']),profiles,pool)
                        rows.append(f); options.append(option)
                if rows:
                    predictions=models[gid].predict_proba(pd.DataFrame(rows)[PASS_FEATURES+[FEATURE]])[:,1]
                    for option,p in zip(options,predictions):
                        option['turnoverProbability']=round(float(p),5)
                        option['value']=round(float((1-p)*option['completedEpv']),4)
                        option['riskModel']='player-steal-prior'
                    path.write_text(json.dumps(play,separators=(',',':'),allow_nan=False))
    print(json.dumps(dict(summary,enabled=enabled)),flush=True)

if __name__=='__main__':main()
