"""Read-only model audit; writes diagnostics, never changes displayed foul estimates."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits
from .foul_value import load_examples,season_profiles,FoulModel,MODEL_FEATURES

def main():
    root=Path(__file__).resolve().parents[1]
    table,fts,total=load_examples(root);profiles=season_profiles(root);rows=[]
    for gid in sorted(table.gameId.unique()):
        train=table[table.gameId!=gid];test=table[table.gameId==gid].copy()
        model=FoulModel(train,fts[fts.gameId!=gid],profiles)
        fm,fa,_=model.predict(test)
        q=(test.sq/100).where(test.sq.between(0,100),train.made.mean()).to_numpy()
        test['predicted']=(1-q)*fm+q*fa
        test['conditional']=np.where(test.made,fa,fm)
        test['baseline']=[train[(train.points==p)&(train.made==m)].fouled.mean() for p,m in zip(test.points,test.made)]
        conditional=[]
        for made in (0,1):
            tr=model.design(train[train.made==made]);te=model.design(test)
            tr['three']=(tr.points==3).astype(int);te['three']=(te.points==3).astype(int)
            design=ColumnTransformer([('geometry',make_pipeline(SimpleImputer(),StandardScaler()),MODEL_FEATURES+['three']),('player',OneHotEncoder(handle_unknown='ignore'),['shooter'])])
            candidate=make_pipeline(design,LogisticRegression(C=.2,max_iter=1000)).fit(tr,tr.fouled)
            conditional.append(candidate.predict_proba(te)[:,1])
        test['with_three']=np.where(test.made,conditional[1],conditional[0])
        rows.append(test)
    data=pd.concat(rows)
    def report(df):
        return dict(n=len(df),fouls=int(df.fouled.sum()),observed=float(df.fouled.mean()),
                    prospectiveMean=float(df.predicted.mean()),conditionalMean=float(df.conditional.mean()),
                    brier=float(np.mean((df.conditional-df.fouled)**2)),
                    shotTypeBaselineBrier=float(np.mean((df.baseline-df.fouled)**2)),
                    withThreeIndicatorBrier=float(np.mean((df.with_three-df.fouled)**2)))
    groups={'all':data,'twos':data[data.points==2],'threes':data[data.points==3],
            'threes_defender_under3ft':data[(data.points==3)&(data.defender_distance<3)],
            'threes_defender_3plusft':data[(data.points==3)&(data.defender_distance>=3)],
            'dubljevic_other_games_threes':data[(data.shooter=='59204')&(data.points==3)&(data.gameId!=191313)]}
    result={k:report(v) for k,v in groups.items() if len(v)}
    result['limitations']='Conditional Brier uses observed make/miss only to evaluate the correct stratum. Prospective mean mixes branches with vendor SQ, not a validated live C&S forecast. Candidate three-point indicator evaluated only, not deployed.'
    (root/'artifacts/foul-audit.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__=='__main__':
    with threadpool_limits(limits=2):main()
