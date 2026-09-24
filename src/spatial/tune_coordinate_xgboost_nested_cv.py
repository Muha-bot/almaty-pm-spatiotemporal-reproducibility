#!/usr/bin/env python3
"""
Coordinate-only XGBoost baseline for the 107-station spatial-block
sensitivity analysis, with hyperparameters chosen by NESTED cross-
validation instead of a single fixed guess.

Why this exists: `add_coordinate_xgboost_baseline.py` used one
hand-picked hyperparameter set and found XGBoost did not beat Linear
regression. Before concluding anything from that, hyperparameters should
be tuned properly -- but tuning them against the same outer test block
used for evaluation would leak information and make the result
untrustworthy (this is exactly the kind of test-set tuning this
repository's own "Scientific safeguards" rule out). So for each of the 5
outer spatial-block folds:

  1. Hold out that block as the outer test set (as in the other scripts).
  2. Within the remaining 4 training blocks only, run leave-one-block-out
     INNER cross-validation over a small, fixed grid of XGBoost
     configurations.
  3. Pick the configuration with the best mean inner-CV RMSE.
  4. Refit with that configuration on all 4 training blocks and predict
     the held-out outer block.

The outer test block is never used to choose hyperparameters. Whatever
this script reports is what a leakage-controlled tuning procedure actually
finds, not the result of trying configurations until one wins.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

GRID = {
    "n_estimators": [100, 300],
    "max_depth": [2, 3, 4],
    "learning_rate": [0.03, 0.05, 0.1],
}
FIXED = dict(subsample=0.9, colsample_bytree=0.9, reg_lambda=1.0, random_state=20260922)


def inner_cv_rmse(xy, y, block, params):
    """Leave-one-block-out RMSE within the training blocks only."""
    errs = []
    for b in np.unique(block):
        tr, te = block != b, block == b
        if te.sum() == 0 or tr.sum() == 0:
            continue
        m = XGBRegressor(**params, **FIXED)
        m.fit(xy[tr], y[tr])
        pr = m.predict(xy[te])
        errs.append((pr - y[te]) ** 2)
    if not errs:
        return np.inf
    return float(np.sqrt(np.concatenate(errs).mean()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--outdir", required=True, type=Path)
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.input)
    if len(df) != 107 or df.station_id.nunique() != 107:
        raise ValueError("Expected 107 unique AirGradient station means.")

    xy_ll = df[["lon", "lat"]].to_numpy(float)
    y = df.pm25.to_numpy(float)
    block = df.spatial_block.to_numpy(int)
    grid = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]

    rows, preds, chosen = [], [], []
    for b in sorted(np.unique(block)):
        tr, te = block != b, block == b
        xy_tr, y_tr, block_tr = xy_ll[tr], y[tr], block[tr]

        # Inner CV over the training blocks only -- outer block b untouched.
        scored = [(inner_cv_rmse(xy_tr, y_tr, block_tr, p), p) for p in grid]
        best_rmse, best_params = min(scored, key=lambda t: t[0])
        chosen.append({"outer_block": int(b), "inner_cv_rmse": best_rmse, **best_params})

        model = XGBRegressor(**best_params, **FIXED)
        model.fit(xy_tr, y_tr)
        pr = model.predict(xy_ll[te])

        rows.append({
            "block": int(b), "model": "XGBoost_coord_only_tuned", "n": int(te.sum()),
            "MAE": mean_absolute_error(y[te], pr),
            "RMSE": mean_squared_error(y[te], pr) ** 0.5,
            "R2": r2_score(y[te], pr),
        })
        idx = np.where(te)[0]
        for j, p in zip(idx, pr):
            preds.append({
                "station_id": df.iloc[j].station_id, "block": int(b),
                "model": "XGBoost_coord_only_tuned",
                "y_true": float(y[j]), "y_pred": float(p),
            })

    by_block = pd.DataFrame(rows)
    pred = pd.DataFrame(preds)
    summary = pd.DataFrame([{
        "model": "XGBoost_coord_only_tuned",
        "n": len(pred),
        "MAE_pooled": mean_absolute_error(pred.y_true, pred.y_pred),
        "RMSE_pooled": mean_squared_error(pred.y_true, pred.y_pred) ** 0.5,
        "R2_pooled": r2_score(pred.y_true, pred.y_pred),
        "MAE_block_macro": by_block.MAE.mean(),
        "RMSE_block_macro": by_block.RMSE.mean(),
    }])

    by_block.to_csv(args.outdir / "xgboost_tuned_by_block.csv", index=False)
    pred.to_csv(args.outdir / "xgboost_tuned_predictions.csv", index=False)
    summary.to_csv(args.outdir / "xgboost_tuned_summary.csv", index=False)
    pd.DataFrame(chosen).to_csv(args.outdir / "xgboost_tuned_chosen_params_per_fold.csv", index=False)

    print(pd.DataFrame(chosen).to_string(index=False))
    print()
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
