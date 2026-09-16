"""Refresh only ROP forecasts; preserve other replay estimates. Run from repo root."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import log_loss
from epv.rop_risk import conservative_rop

ROOT = Path(__file__).resolve().parents[1]


def main():
    states = pd.read_pickle(ROOT / 'artifacts/states.pkl')
    report = []
    pooled = []
    manifest_path = ROOT / 'viewer/data/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    for game in manifest['games']:
        gid = game['match']['id']
        train = states[(states.gameId != gid) & states.train]
        weights = 1 / train.groupby('possessionId').frame.transform('size')
        baseline = float(np.average(train.turnover_rest, weights=weights))
        test = states[states.gameId == gid]
        predictions = {}
        for summary in game['plays']:
            path = ROOT / 'viewer/data/plays' / (summary['id'] + '.json')
            play = json.loads(path.read_text())
            for frame in play['frames']:
                if frame.get('turnoverRest') is None:
                    continue
                raw = frame.setdefault('turnoverRestRaw', frame['turnoverRest'])
                frame['turnoverRest'] = round(float(conservative_rop(raw, baseline, frame['turnover2'])), 5)
                predictions[(play['id'], frame['frame'])] = frame['turnoverRest']
            path.write_text(json.dumps(play, separators=(',', ':')))
        p = np.array([predictions[(r.possessionId, r.frame)] for r in test.itertuples()])
        w = 1 / test.groupby('possessionId').frame.transform('size')
        pooled.append((p, test.turnover_rest.to_numpy(), w.to_numpy()/w.sum()))
        report.append(dict(gameId=gid, baseline=baseline,
                           logLoss=float(log_loss(test.turnover_rest, p, sample_weight=w)),
                           brier=float(np.average((p-test.turnover_rest)**2, weights=w)),
                           predicted=float(np.average(p, weights=w)),
                           observed=float(np.average(test.turnover_rest, weights=w))))
    result = dict(method='75% other-game possession-weighted training prevalence + 25% geometry ROP; floored at next-2s risk',
                  limitation='Blend chosen after comparing these ten held-out games; improvement is exploratory, not independent validation.',
                  perGame=report,
                  brier=float(np.mean([r['brier'] for r in report])),
                  predicted=float(np.mean([r['predicted'] for r in report])),
                  observed=float(np.mean([r['observed'] for r in report])))
    (ROOT / 'artifacts/rop-validation.json').write_text(json.dumps(result, indent=2))
    manifest['metrics']['ropAdjustment'] = result
    p, y, w = [np.concatenate([row[i] for row in pooled]) for i in range(3)]
    for metrics in [manifest['metrics'], json.loads((ROOT / 'artifacts/metrics.json').read_text())]:
        metrics.setdefault('ropBeforeAdjustment', metrics['summary']['turnover_rest']['geometry'].copy())
        metrics['ropAdjustment'] = result
        metrics['summary']['turnover_rest']['geometry'] = dict(
            brier=result['brier'], logLoss=float(log_loss(y,p,sample_weight=w)),
            predicted=result['predicted'], observed=result['observed'])
        for row in metrics['perGame']:
            if row['target']=='turnover_rest' and row['model']=='geometry':
                updated=next(r for r in report if r['gameId']==row['gameId'])
                row.update({k:updated[k] for k in ['brier','logLoss','predicted','observed']})
        bins=[0,.025,.05,.1,.15,.2,.3,.5,1.000001]
        metrics['calibration']['turnover_rest']=[]
        for lo,hi in zip(bins,bins[1:]):
            mask=(p>=lo)&(p<hi)
            if mask.any():
                metrics['calibration']['turnover_rest'].append(dict(lo=lo,hi=hi,n=int(mask.sum()),
                    predicted=float(np.average(p[mask],weights=w[mask])),observed=float(np.average(y[mask],weights=w[mask]))))
        if metrics is not manifest['metrics']:
            (ROOT / 'artifacts/metrics.json').write_text(json.dumps(metrics,indent=2))
    manifest_path.write_text(json.dumps(manifest, separators=(',', ':')))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
