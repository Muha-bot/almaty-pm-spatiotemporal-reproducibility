#!/usr/bin/env python3
"""
Reproduce the deterministic spatial-block transfer sensitivity for the
107-site AirGradient PM2.5 station-mean cohort.

Scope:
- secondary RQ5 spatial-field transfer sensitivity;
- NOT the final hourly station-holdout A0-A3 forecasting experiment.

Inputs:
  airgradient_spatial_blocks.csv
Columns required:
  station_id, lat, lon, pm25, spatial_block

Prespecified deterministic models:
  TrainingMean : mean PM2.5 of training blocks
  IDW          : inverse-distance-squared using training stations
  Linear       : PM2.5 ~ lon + lat
  Quadratic    : degree-2 polynomial in lon/lat

Block reconstruction audit:
  KMeans(n_clusters=5, random_state=20260904, n_init=20)
  on z-standardized EPSG:32643 x/y coordinates.

Uncertainty:
  paired bootstrap of the five held-out spatial blocks, 20,000 replicates,
  seed 20260906. With only five blocks, intervals are sensitivity evidence,
  not high-powered inferential claims.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial.distance import cdist
from sklearn.cluster import KMeans
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (
    adjusted_rand_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler


def idw2_predict(x_train, y_train, x_test):
    d = cdist(x_test, x_train)
    if np.any(d == 0):
        raise ValueError("A held-out location coincides with a training location.")
    w = 1.0 / np.square(d)
    return (w * y_train[None, :]).sum(axis=1) / w.sum(axis=1)


def main():
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

    # Reconstruct block partition independently in metric coordinates.
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
    x, y_utm = transformer.transform(df.lon.to_numpy(), df.lat.to_numpy())
    xy_utm = np.c_[x, y_utm]
    xy_z = StandardScaler().fit_transform(xy_utm)
    km = KMeans(n_clusters=5, random_state=20260904, n_init=20).fit(xy_z)
    ari = adjusted_rand_score(df.spatial_block, km.labels_)

    # Distance coordinates for IDW in approximately kilometres.
    lat0 = np.deg2rad(df.lat.mean())
    xy_km = np.c_[
        df.lon.to_numpy() * np.cos(lat0) * 111.32,
        df.lat.to_numpy() * 110.57,
    ]
    xy_ll = df[["lon", "lat"]].to_numpy(float)
    y = df.pm25.to_numpy(float)
    block = df.spatial_block.to_numpy(int)

    rows, preds = [], []
    for b in sorted(np.unique(block)):
        tr, te = block != b, block == b

        pred_map = {}
        pred_map["TrainingMean"] = np.repeat(y[tr].mean(), te.sum())
        pred_map["IDW"] = idw2_predict(xy_km[tr], y[tr], xy_km[te])
        pred_map["Linear"] = LinearRegression().fit(xy_ll[tr], y[tr]).predict(xy_ll[te])
        pred_map["Quadratic"] = make_pipeline(
            PolynomialFeatures(degree=2, include_bias=False),
            LinearRegression(),
        ).fit(xy_ll[tr], y[tr]).predict(xy_ll[te])

        idx = np.where(te)[0]
        for model, pr in pred_map.items():
            rows.append({
                "block": int(b),
                "model": model,
                "n": int(te.sum()),
                "MAE": mean_absolute_error(y[te], pr),
                "RMSE": mean_squared_error(y[te], pr) ** 0.5,
                "R2": r2_score(y[te], pr),
            })
            for j, p in zip(idx, pr):
                preds.append({
                    "station_id": df.iloc[j].station_id,
                    "block": int(b),
                    "model": model,
                    "y_true": float(y[j]),
                    "y_pred": float(p),
                    "error": float(p - y[j]),
                    "abs_error": float(abs(p - y[j])),
                })

    by_block = pd.DataFrame(rows)
    pred = pd.DataFrame(preds)

    summary = []
    for model, g in pred.groupby("model"):
        yt, yp = g.y_true.to_numpy(), g.y_pred.to_numpy()
        bb = by_block[by_block.model.eq(model)]
        summary.append({
            "model": model,
            "n": len(g),
            "MAE_pooled": mean_absolute_error(yt, yp),
            "RMSE_pooled": mean_squared_error(yt, yp) ** 0.5,
            "R2_pooled": r2_score(yt, yp),
            "MAE_block_macro": bb.MAE.mean(),
            "RMSE_block_macro": bb.RMSE.mean(),
        })
    summary = pd.DataFrame(summary)

    base = summary.loc[summary.model.eq("TrainingMean")].iloc[0]
    summary["MAE_reduction_vs_training_mean_pct"] = (
        (base.MAE_pooled - summary.MAE_pooled) / base.MAE_pooled * 100
    )
    summary["RMSE_reduction_vs_training_mean_pct"] = (
        (base.RMSE_pooled - summary.RMSE_pooled) / base.RMSE_pooled * 100
    )

    # Paired spatial-block bootstrap using block sufficient statistics.
    wide = pred.pivot_table(
        index=["station_id", "block", "y_true"],
        columns="model",
        values="y_pred",
        aggfunc="first",
    ).reset_index()
    blocks = np.array(sorted(wide.block.unique()))
    model_names = ["TrainingMean", "Linear", "IDW", "Quadratic"]

    stats = {}
    for model in model_names:
        a = []
        for b in blocks:
            g = wide[wide.block.eq(b)]
            e = g[model].to_numpy() - g.y_true.to_numpy()
            a.append([len(g), np.abs(e).sum(), np.square(e).sum()])
        stats[model] = np.array(a, dtype=float)

    def pooled(counts, model):
        s = stats[model]
        n = counts @ s[:, 0]
        return (counts @ s[:, 1]) / n, np.sqrt((counts @ s[:, 2]) / n)

    rng = np.random.default_rng(20260906)
    B = 20000
    draws = rng.integers(0, len(blocks), size=(B, len(blocks)))
    counts = np.column_stack([(draws == j).sum(axis=1) for j in range(len(blocks))])

    comparisons = [
        ("Linear", "TrainingMean"),
        ("IDW", "TrainingMean"),
        ("Quadratic", "TrainingMean"),
        ("Linear", "IDW"),
    ]
    boot_rows = []
    ones = np.ones(len(blocks))
    for a, b in comparisons:
        a_mae, a_rmse = pooled(ones, a)
        b_mae, b_rmse = pooled(ones, b)
        amae, armse = pooled(counts, a)
        bmae, brmse = pooled(counts, b)
        dmae, drmse = amae - bmae, armse - brmse
        boot_rows.append({
            "comparison": f"{a} - {b}",
            "delta_MAE": a_mae - b_mae,
            "delta_MAE_ci_low": np.quantile(dmae, .025),
            "delta_MAE_ci_high": np.quantile(dmae, .975),
            "delta_RMSE": a_rmse - b_rmse,
            "delta_RMSE_ci_low": np.quantile(drmse, .025),
            "delta_RMSE_ci_high": np.quantile(drmse, .975),
            "bootstrap_unit": "held-out spatial block",
            "n_blocks": len(blocks),
            "bootstrap_replicates": B,
            "seed": 20260906,
        })
    boot = pd.DataFrame(boot_rows)

    summary.to_csv(args.outdir / "spatial_block_cv_summary.csv", index=False)
    by_block.to_csv(args.outdir / "spatial_block_cv_by_block.csv", index=False)
    pred.to_csv(args.outdir / "spatial_block_cv_predictions.csv", index=False)
    boot.to_csv(args.outdir / "spatial_block_cv_block_bootstrap.csv", index=False)

    audit = {
        "n_stations": 107,
        "n_blocks": 5,
        "block_sizes": {
            str(int(k)): int(v) for k, v in df.groupby("spatial_block").size().items()
        },
        "regenerated_vs_archived_block_ARI": float(ari),
        "block_construction":
            "KMeans(n_clusters=5, random_state=20260904, n_init=20) "
            "on z-standardized EPSG:32643 x/y coordinates",
        "scope":
            "Station-mean PM2.5 spatial-field transfer sensitivity only; "
            "not final hourly station-holdout A0-A3 forecasting.",
    }
    (args.outdir / "audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")

    print(summary.sort_values("MAE_pooled").to_string(index=False))
    print()
    print(boot.to_string(index=False))
    print()
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
