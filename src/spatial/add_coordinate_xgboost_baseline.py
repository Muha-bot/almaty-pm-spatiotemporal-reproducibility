#!/usr/bin/env python3
"""
Add a coordinate-only XGBoost baseline to the 107-station spatial-block
transfer-sensitivity analysis (manuscript Figure 7).

`reproduce_spatial_block_cv.py` in this same directory implements four
deterministic baselines (TrainingMean, IDW, Linear, Quadratic) but not the
XGBoost coordinate-only model the manuscript's Figure 7 caption refers to
("XGBoost has the lowest pooled and block-macro RMSE in this secondary
coordinate-only experiment"). That model was never supplied with this
repository as either code or archived predictions, so it is added here,
run against the same 5-fold spatial-block partition, with an explicit,
fixed random seed recorded in the output (unlike the missing-seed A0/A1
model selections documented in docs/KNOWN_LIMITATIONS.md §1 — that gap is
not repeated here).

Input: the same schema as reproduce_spatial_block_cv.py
(station_id, lat, lon, pm25, spatial_block), so both scripts can be run
against the same cohort file and their outputs compared directly.

This is a NEW model run, not a recovery of an archived XGBoost result:
hyperparameters were not supplied, so reasonable, explicitly-recorded
defaults are used instead of an unstated original configuration.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

XGB_PARAMS = dict(
    n_estimators=300,
    max_depth=3,
    learning_rate=0.05,
    subsample=0.9,
    colsample_bytree=0.9,
    reg_lambda=1.0,
    random_state=20260922,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--outdir", required=True, type=Path)
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.input)
    req = {"station_id", "lat", "lon", "pm25", "spatial_block"}
    miss = req - set(df.columns)
    if miss:
        raise ValueError(f"Missing columns: {sorted(miss)}")
    if len(df) != 107 or df.station_id.nunique() != 107:
        raise ValueError("Expected 107 unique AirGradient station means.")

    xy_ll = df[["lon", "lat"]].to_numpy(float)
    y = df.pm25.to_numpy(float)
    block = df.spatial_block.to_numpy(int)

    rows, preds = [], []
    for b in sorted(np.unique(block)):
        tr, te = block != b, block == b
        model = XGBRegressor(**XGB_PARAMS)
        model.fit(xy_ll[tr], y[tr])
        pr = model.predict(xy_ll[te])

        rows.append({
            "block": int(b), "model": "XGBoost_coord_only", "n": int(te.sum()),
            "MAE": mean_absolute_error(y[te], pr),
            "RMSE": mean_squared_error(y[te], pr) ** 0.5,
            "R2": r2_score(y[te], pr),
        })
        idx = np.where(te)[0]
        for j, p in zip(idx, pr):
            preds.append({
                "station_id": df.iloc[j].station_id, "block": int(b),
                "model": "XGBoost_coord_only",
                "y_true": float(y[j]), "y_pred": float(p),
                "error": float(p - y[j]), "abs_error": float(abs(p - y[j])),
            })

    by_block = pd.DataFrame(rows)
    pred = pd.DataFrame(preds)
    summary = pd.DataFrame([{
        "model": "XGBoost_coord_only",
        "n": len(pred),
        "MAE_pooled": mean_absolute_error(pred.y_true, pred.y_pred),
        "RMSE_pooled": mean_squared_error(pred.y_true, pred.y_pred) ** 0.5,
        "R2_pooled": r2_score(pred.y_true, pred.y_pred),
        "MAE_block_macro": by_block.MAE.mean(),
        "RMSE_block_macro": by_block.RMSE.mean(),
        "hyperparameters": json.dumps(XGB_PARAMS),
    }])

    by_block.to_csv(args.outdir / "xgboost_coord_only_by_block.csv", index=False)
    pred.to_csv(args.outdir / "xgboost_coord_only_predictions.csv", index=False)
    summary.to_csv(args.outdir / "xgboost_coord_only_summary.csv", index=False)
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
