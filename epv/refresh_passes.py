"""Refresh pass risk and discounted values without retraining unchanged catch EPV.

Run after an existing full build: python -m epv.refresh_passes
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss
from threadpoolctl import threadpool_limits

from .passing import (
    BASE_PASS_FEATURES,
    PASS_FEATURES,
    TIMING_DESCRIPTION,
    fit_pass_model,
    load_passes,
    pass_features,
    route_diagnostic,
)


def main():
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / "viewer/data/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    table, _audit = load_passes(root)
    validation = []
    for game in manifest["games"]:
        gid = game["match"]["id"]
        train, test = table[table.gameId != gid], table[table.gameId == gid]
        model = fit_pass_model(train)
        old = fit_pass_model(train, BASE_PASS_FEATURES)
        prob = model.predict_proba(test[PASS_FEATURES])[:, 1]
        old_prob = old.predict_proba(test[BASE_PASS_FEATURES])[:, 1]
        validation.append(
            {
                "gameId": gid,
                "passes": len(test),
                "turnovers": int(test.turnover.sum()),
                "brier": float(brier_score_loss(test.turnover, prob)),
                "baselineBrier": float(
                    brier_score_loss(
                        test.turnover, np.full(len(test), train.turnover.mean())
                    )
                ),
                "logLoss": float(log_loss(test.turnover, prob, labels=[0, 1])),
                "geometryBrier": float(brier_score_loss(test.turnover, old_prob)),
                "geometryLogLoss": float(
                    log_loss(test.turnover, old_prob, labels=[0, 1])
                ),
            }
        )
        for entry in game["plays"]:
            path = root / f"viewer/data/plays/{entry['id']}.json"
            play = json.loads(path.read_text())
            refs = []
            rows = []
            for frame in play["frames"]:
                for option in frame.get("passOptions", []):
                    feats = pass_features(
                        frame, frame["geometry"]["handler"], option["player"]
                    )
                    rows.append(feats)
                    refs.append(option)
            if rows:
                probs = model.predict_proba(pd.DataFrame(rows)[PASS_FEATURES])[:, 1]
                for option, feats, p in zip(refs, rows, probs):
                    option.update(
                        turnoverProbability=round(float(p), 5),
                        value=round(float((1 - p) * option["completedEpv"]), 4),
                        route=route_diagnostic(feats),
                    )
                path.write_text(
                    json.dumps(play, separators=(",", ":"), allow_nan=False)
                )
        print("Updated pass options", gid, flush=True)
    metrics = manifest["metrics"]["passing"]
    metrics.update(
        perGame=validation, features=PASS_FEATURES, timing=TIMING_DESCRIPTION
    )
    manifest_path.write_text(
        json.dumps(manifest, separators=(",", ":"), allow_nan=False)
    )
    (root / "artifacts/metrics.json").write_text(
        json.dumps(manifest["metrics"], separators=(",", ":"), allow_nan=False)
    )
    bundle = joblib.load(root / "artifacts/models.joblib")
    bundle.update(passModel=fit_pass_model(table), passFeatures=PASS_FEATURES)
    joblib.dump(bundle, root / "artifacts/models.joblib")
    print(
        {
            key: float(np.mean([r[key] for r in validation]))
            for key in ["brier", "geometryBrier", "logLoss", "geometryLogLoss"]
        },
        flush=True,
    )


if __name__ == "__main__":
    with threadpool_limits(limits=2):
        main()
