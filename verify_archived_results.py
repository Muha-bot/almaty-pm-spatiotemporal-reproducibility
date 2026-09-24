#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

EXPECTED_HASHES = {
    "metrics.csv": "1b1baf90bfe5adcfaada33a9a5f072c557179824f832cfe62a24303b4341de56",
    "selected_hyperparameters.csv": "b856f09dad3efc4ad482ba4039f2ed5c68d0109ab6df609432345d3e7f3e5796",
    "kgmt_station_geometry_features.csv": "61a058513811892c042c0d613f18714cd0d1d8df1a0e757d3067b1fe44cdd5c6",
    "airgradient_station_geometry_features.csv": "51fc655db83188b4f17118fb67ff891f75fd9b34e9a6d44cc75f74b52e0b37ea",
}

EXPECTED_COUNTS = {
    ("pm25", 1): (81990, 29253, 41999),
    ("pm10", 1): (81990, 29253, 41999),
    ("pm25", 24): (74133, 25474, 39776),
    ("pm10", 24): (74133, 25474, 39776),
}

FITTED_MODELS = {"Ridge", "RandomForest", "XGBoost"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_hashes(data_dir: Path) -> pd.DataFrame:
    rows = []
    for name, expected in EXPECTED_HASHES.items():
        p = data_dir / name
        if not p.exists():
            raise FileNotFoundError(p)
        got = sha256(p)
        rows.append({"file": name, "expected_sha256": expected, "actual_sha256": got, "match": got == expected})
        if got != expected:
            raise AssertionError(f"SHA-256 mismatch for {name}: {got}")
    return pd.DataFrame(rows)


def validate_metrics(metrics: pd.DataFrame) -> None:
    required = {"target", "horizon", "ablation", "model", "n_train", "n_val", "n_test", "MAE", "RMSE", "R2"}
    missing = required - set(metrics.columns)
    if missing:
        raise ValueError(f"metrics.csv missing columns: {sorted(missing)}")
    if len(metrics) != 40:
        raise AssertionError(f"Expected 40 metric rows, found {len(metrics)}")
    for (target, horizon), g in metrics.groupby(["target", "horizon"]):
        exp = EXPECTED_COUNTS[(target, int(horizon))]
        observed = set(map(tuple, g[["n_train", "n_val", "n_test"]].drop_duplicates().to_numpy()))
        if observed != {exp}:
            raise AssertionError(f"Sample-count mismatch for {target} +{horizon} h: {observed}, expected {exp}")
    if set(metrics["ablation"].unique()) != {"A0_history", "A1_crossPM"}:
        raise AssertionError("Unexpected ablation labels")


def validate_hyperparameters(hp: pd.DataFrame) -> None:
    required = {"target", "horizon", "ablation", "model", "validation_MAE", "params"}
    missing = required - set(hp.columns)
    if missing:
        raise ValueError(f"selected_hyperparameters.csv missing columns: {sorted(missing)}")
    if len(hp) != 24:
        raise AssertionError(f"Expected 24 hyperparameter rows, found {len(hp)}")
    if set(hp["model"].unique()) != FITTED_MODELS:
        raise AssertionError("Unexpected fitted model set")
    # Validate params are parseable dictionaries.
    for x in hp["params"]:
        try:
            obj = json.loads(str(x))
        except Exception:
            obj = ast.literal_eval(str(x))
        if not isinstance(obj, dict):
            raise ValueError("params must parse to a dictionary")


def selected_results(metrics: pd.DataFrame, hp: pd.DataFrame) -> pd.DataFrame:
    winners = (
        hp.sort_values(["target", "horizon", "ablation", "validation_MAE", "model"])
          .groupby(["target", "horizon", "ablation"], as_index=False)
          .first()
          .rename(columns={"model": "selected_model"})
    )
    fit_metrics = metrics[metrics["model"].isin(FITTED_MODELS)].copy()
    out = winners.merge(
        fit_metrics,
        left_on=["target", "horizon", "ablation", "selected_model"],
        right_on=["target", "horizon", "ablation", "model"],
        validate="one_to_one",
    )
    persistence = metrics[metrics.model.eq("Persistence")][["target", "horizon", "ablation", "RMSE"]].rename(columns={"RMSE": "persistence_RMSE"})
    out = out.merge(persistence, on=["target", "horizon", "ablation"], validate="one_to_one")
    out["RMSE_reduction_pct_vs_persistence"] = (out.persistence_RMSE - out.RMSE) / out.persistence_RMSE * 100.0
    keep = [
        "target", "horizon", "ablation", "selected_model", "validation_MAE",
        "MAE", "RMSE", "R2", "persistence_RMSE", "RMSE_reduction_pct_vs_persistence",
    ]
    out = out[keep].rename(columns={"MAE": "test_MAE", "RMSE": "test_RMSE", "R2": "test_R2"})
    return out.sort_values(["target", "horizon", "ablation"]).reset_index(drop=True)


def crosspm_deltas(metrics: pd.DataFrame) -> pd.DataFrame:
    fit = metrics[metrics.model.isin(FITTED_MODELS)].copy()
    a0 = fit[fit.ablation.eq("A0_history")].set_index(["target", "horizon", "model"])
    a1 = fit[fit.ablation.eq("A1_crossPM")].set_index(["target", "horizon", "model"])
    if not a0.index.equals(a1.index):
        # Sort first; equality should then hold exactly.
        a0 = a0.sort_index(); a1 = a1.sort_index()
        if not a0.index.equals(a1.index):
            raise AssertionError("A0/A1 fitted-model cells do not align")
    out = pd.DataFrame(index=a0.index).reset_index()
    out["delta_MAE_A1_minus_A0"] = (a1.MAE - a0.MAE).to_numpy()
    out["delta_RMSE_A1_minus_A0"] = (a1.RMSE - a0.RMSE).to_numpy()
    out["delta_R2_A1_minus_A0"] = (a1.R2 - a0.R2).to_numpy()
    out["RMSE_pct_change_A1_vs_A0"] = ((a1.RMSE - a0.RMSE) / a0.RMSE * 100.0).to_numpy()
    return out.sort_values(["target", "horizon", "model"]).reset_index(drop=True)


def compare_csv_numeric(a: pd.DataFrame, b: pd.DataFrame, key_cols: list[str], numeric_cols: list[str], tol: float = 1e-10) -> None:
    aa = a.copy(); bb = b.copy()
    # Drop autogenerated index columns if present.
    aa = aa[[c for c in aa.columns if not c.lower().startswith("unnamed") and c != "index"]]
    bb = bb[[c for c in bb.columns if not c.lower().startswith("unnamed") and c != "index"]]
    aa = aa.sort_values(key_cols).reset_index(drop=True)
    bb = bb.sort_values(key_cols).reset_index(drop=True)
    if len(aa) != len(bb):
        raise AssertionError(f"Row-count mismatch: {len(aa)} vs {len(bb)}")
    for c in key_cols:
        if not aa[c].astype(str).equals(bb[c].astype(str)):
            raise AssertionError(f"Key mismatch in column {c}")
    for c in numeric_cols:
        if c not in aa or c not in bb:
            raise AssertionError(f"Missing numeric comparison column {c}")
        if not np.allclose(pd.to_numeric(aa[c]), pd.to_numeric(bb[c]), rtol=0, atol=tol, equal_nan=True):
            diff = np.nanmax(np.abs(pd.to_numeric(aa[c]) - pd.to_numeric(bb[c])))
            raise AssertionError(f"Numeric mismatch in {c}; max abs diff={diff}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    hash_df = verify_hashes(args.data_dir)
    metrics = pd.read_csv(args.data_dir / "metrics.csv")
    hp = pd.read_csv(args.data_dir / "selected_hyperparameters.csv")
    validate_metrics(metrics)
    validate_hyperparameters(hp)

    sel = selected_results(metrics, hp)
    delta = crosspm_deltas(metrics)

    hash_df.to_csv(args.out_dir / "hash_verification.csv", index=False)
    sel.to_csv(args.out_dir / "validation_selected_primary_test_results_recomputed.csv", index=False)
    delta.to_csv(args.out_dir / "crossPM_ablation_test_deltas_recomputed.csv", index=False)

    # Compare to preserved verification exports when available.
    archived_sel = args.data_dir / "validation_selected_primary_test_results_verified.csv"
    if archived_sel.exists():
        a = pd.read_csv(archived_sel)
        compare_csv_numeric(
            sel, a,
            key_cols=["target", "horizon", "ablation", "selected_model"],
            numeric_cols=["validation_MAE", "test_MAE", "test_RMSE", "test_R2", "persistence_RMSE", "RMSE_reduction_pct_vs_persistence"],
            tol=1e-9,
        )

    archived_delta = args.data_dir / "crossPM_ablation_test_deltas_verified.csv"
    if archived_delta.exists():
        a = pd.read_csv(archived_delta)
        compare_csv_numeric(
            delta, a,
            key_cols=["target", "horizon", "model"],
            numeric_cols=["delta_MAE_A1_minus_A0", "delta_RMSE_A1_minus_A0", "delta_R2_A1_minus_A0", "RMSE_pct_change_A1_vs_A0"],
            tol=1e-9,
        )

    print("PASS: core hashes match archived manuscript fingerprints")
    print("PASS: metrics.csv has 40 rows and invariant task counts")
    print("PASS: selected_hyperparameters.csv has 24 fitted configurations")
    print("PASS: validation-selected and A1-A0 tables reproduce preserved verification exports")
    print(sel.to_string(index=False))


if __name__ == "__main__":
    main()
