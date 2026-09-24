#!/usr/bin/env python3
"""
Strict pre-GWR gate and primary GWR runner for the Almaty PM2.5 spatial branch.

The primary model is deliberately parsimonious and fixed before GIS values are inspected:
    elevation_m, road_density_500m, built_frac_500m

Prespecified sensitivity predictors are assessed one at a time or in predefined
alternative-scale specifications, never selected by target association or map appearance:
    slope_deg, dist_major_road_m, tree_frac_500m,
    road_density_250m/1000m, built_frac_250m/1000m.

Scientific rails
----------------
- final GWR cohort comes from the locked 80/80 common-hour target table;
- no GIS imputation for the primary GWR;
- pairwise |r| > 0.80 or VIF > 5 stops the specification;
- global OLS and residual Moran's I are mandatory before GWR;
- adaptive bi-square bandwidth, AICc selection;
- GWR is PM2.5-only; PM10 remains a full forecasting/A0-A3 target.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.spatial.distance import cdist
from statsmodels.stats.outliers_influence import variance_inflation_factor

PRIMARY_PREDICTORS = [
    "elevation_m",
    "road_density_500m",
    "built_frac_500m",
]

SENSITIVITY_SPECS = {
    "slope": ["elevation_m", "slope_deg", "road_density_500m", "built_frac_500m"],
    "road_distance": ["elevation_m", "dist_major_road_m", "road_density_500m", "built_frac_500m"],
    "vegetation": ["elevation_m", "road_density_500m", "built_frac_500m", "tree_frac_500m"],
    "buffer_250m": ["elevation_m", "road_density_250m", "built_frac_250m"],
    "buffer_1000m": ["elevation_m", "road_density_1000m", "built_frac_1000m"],
}


def symmetric_knn_weights(xy: np.ndarray, k: int = 4) -> np.ndarray:
    """Symmetric binary kNN graph, row-standardized after symmetrization."""
    n = len(xy)
    if n <= k:
        raise ValueError(f"Need > k stations for Moran weights; n={n}, k={k}")
    D = cdist(xy, xy)
    np.fill_diagonal(D, np.inf)
    nbr = np.argpartition(D, kth=k-1, axis=1)[:, :k]
    A = np.zeros((n, n), dtype=float)
    for i in range(n):
        A[i, nbr[i]] = 1.0
    A = np.maximum(A, A.T)
    rs = A.sum(axis=1, keepdims=True)
    return np.divide(A, rs, out=np.zeros_like(A), where=rs != 0)


def morans_i(x: np.ndarray, W: np.ndarray) -> float:
    z = np.asarray(x, float) - np.nanmean(x)
    denom = np.sum(z * z)
    s0 = W.sum()
    if denom <= 0 or s0 <= 0:
        return float("nan")
    return float((len(z) / s0) * ((W * np.outer(z, z)).sum() / denom))


def moran_permutation(x, W, n_perm=9999, seed=20260906):
    rng = np.random.default_rng(seed)
    obs = morans_i(x, W)
    perms = np.empty(n_perm, dtype=float)
    for j in range(n_perm):
        perms[j] = morans_i(rng.permutation(x), W)
    p_two = (1 + np.sum(np.abs(perms) >= abs(obs))) / (n_perm + 1)
    return obs, float(p_two)


def prepare_model_table(gis: pd.DataFrame, target: pd.DataFrame, target_col: str, predictors: list[str]) -> pd.DataFrame:
    required_gis = {"station_id", "source", "x_utm_m", "y_utm_m", *predictors}
    missing = required_gis - set(gis.columns)
    if missing:
        raise SystemExit(f"FAIL: GIS table missing columns: {sorted(missing)}")
    if target_col not in target.columns:
        raise SystemExit(f"FAIL: target column {target_col!r} not found")
    if "gwr_eligible" not in target.columns:
        raise SystemExit("FAIL: target table has no gwr_eligible flag from the locked 80/80 rule")

    if gis["station_id"].duplicated().any():
        raise SystemExit("FAIL: duplicate station_id in GIS table")

    ag = gis[gis["source"].astype(str).str.lower().eq("airgradient")].copy()
    d = ag.merge(
        target[["station_id", target_col, "gwr_eligible", "common_hour_coverage"]],
        on="station_id",
        how="inner",
        validate="one_to_one",
    )

    elig = d["gwr_eligible"].astype(str).str.lower().isin(["true", "1", "yes"])
    if d["gwr_eligible"].dtype == bool:
        elig = d["gwr_eligible"]
    d = d.loc[elig].copy()

    if d[["x_utm_m", "y_utm_m"]].duplicated().any():
        raise SystemExit("FAIL: duplicate geometry among GWR-eligible stations")
    return d


def diagnostics(d: pd.DataFrame, predictors: list[str], target_col: str, outdir: Path,
                vif_threshold: float, corr_threshold: float, moran_k: int, n_perm: int):
    miss = d[predictors + [target_col]].isna().sum().rename("n_missing").to_frame()
    miss["missing_fraction"] = miss["n_missing"] / max(len(d), 1)
    miss.to_csv(outdir / "gwr_missingness.csv")
    if int(miss["n_missing"].sum()) > 0:
        raise SystemExit("FAIL: missing primary GWR predictor/target values remain; no imputation is allowed")

    X = d[predictors].apply(pd.to_numeric, errors="coerce")
    y = pd.to_numeric(d[target_col], errors="coerce")
    if X.isna().any().any() or y.isna().any():
        raise SystemExit("FAIL: non-numeric values in GWR inputs")

    ranges = X.agg(["min", "median", "max", "std"]).T.reset_index().rename(columns={"index": "feature"})
    ranges.to_csv(outdir / "gwr_predictor_ranges.csv", index=False)
    if (ranges["std"] <= 0).any():
        raise SystemExit("FAIL: at least one primary predictor has zero variance")

    corr = X.corr()
    corr.to_csv(outdir / "gwr_predictor_correlation.csv")
    upper = corr.abs().where(np.triu(np.ones(corr.shape), 1).astype(bool))
    high_pairs = []
    for c in upper.columns:
        for r in upper.index:
            val = upper.loc[r, c]
            if pd.notna(val) and val > corr_threshold:
                high_pairs.append({"feature_1": r, "feature_2": c, "abs_r": float(val)})
    pd.DataFrame(high_pairs, columns=["feature_1", "feature_2", "abs_r"]).to_csv(
        outdir / "gwr_high_correlation_pairs.csv", index=False
    )
    if high_pairs:
        raise SystemExit(
            f"STOP BEFORE GWR: pairwise |r| > {corr_threshold:.2f}. "
            "Use the prespecified concept-preserving sensitivity logic; do not target-select variables."
        )

    Xz = (X - X.mean()) / X.std(ddof=0)
    Xv = sm.add_constant(Xz)
    vif = pd.DataFrame({
        "term": Xv.columns,
        "VIF": [variance_inflation_factor(Xv.values, i) for i in range(Xv.shape[1])],
    })
    vif.to_csv(outdir / "gwr_vif.csv", index=False)
    bad = vif[(vif["term"] != "const") & (vif["VIF"] > vif_threshold)]
    if not bad.empty:
        raise SystemExit(
            f"STOP BEFORE GWR: VIF > {vif_threshold:.2f}. "
            "Do not use outcome-driven stepwise removal; revise only through the prespecified conceptual hierarchy."
        )

    # Global OLS reference with HC3 uncertainty.
    ols = sm.OLS(y.to_numpy(float), sm.add_constant(Xz.to_numpy(float))).fit(cov_type="HC3")
    (outdir / "global_ols_summary.txt").write_text(ols.summary().as_text(), encoding="utf-8")
    pd.DataFrame({
        "term": ["const"] + predictors,
        "coef_standardized_x": ols.params,
        "se_HC3": ols.bse,
        "p_value": ols.pvalues,
    }).to_csv(outdir / "global_ols_coefficients.csv", index=False)

    xy = d[["x_utm_m", "y_utm_m"]].to_numpy(float)
    W = symmetric_knn_weights(xy, moran_k)
    I, p = moran_permutation(np.asarray(ols.resid), W, n_perm=n_perm)

    diag = {
        "n_stations": int(len(d)),
        "target": target_col,
        "predictors": predictors,
        "corr_threshold": corr_threshold,
        "vif_threshold": vif_threshold,
        "max_abs_pairwise_r": float(upper.max().max()),
        "max_predictor_vif": float(vif.loc[vif.term != "const", "VIF"].max()),
        "global_ols_r2": float(ols.rsquared),
        "global_ols_adj_r2": float(ols.rsquared_adj),
        "global_ols_aic": float(ols.aic),
        "moran_k": int(moran_k),
        "moran_permutations": int(n_perm),
        "ols_residual_morans_I": float(I),
        "ols_residual_moran_two_sided_p": float(p),
        "pre_gwr_gate_passed": True,
    }
    (outdir / "pre_gwr_diagnostics.json").write_text(json.dumps(diag, indent=2), encoding="utf-8")
    return Xz, y, xy, ols, diag


def fit_gwr(d, Xz, y, xy, predictors, outdir: Path):
    try:
        from mgwr.sel_bw import Sel_BW
        from mgwr.gwr import GWR
    except ImportError:
        raise SystemExit(
            "PRE-GWR GATE PASSED. Package 'mgwr' is not installed in this execution environment. "
            "Install the validated mgwr package, then rerun the identical frozen inputs. "
            "No hand-written substitute GWR is used for the paper."
        )

    coords = list(map(tuple, xy))
    Xg = Xz.to_numpy(float)
    yg = y.to_numpy(float).reshape((-1, 1))

    selector = Sel_BW(coords, yg, Xg, fixed=False, kernel="bisquare", spherical=False)
    bw = selector.search(criterion="AICc")
    model = GWR(coords, yg, Xg, bw=bw, fixed=False, kernel="bisquare", spherical=False)
    res = model.fit()

    coef = pd.DataFrame(res.params, columns=["Intercept"] + predictors)
    coef.insert(0, "station_id", d["station_id"].to_numpy())
    coef["local_R2"] = np.asarray(res.localR2).reshape(-1)
    coef.to_csv(outdir / "gwr_local_coefficients.csv", index=False)

    # Residual Moran under the same primary graph as the OLS diagnostic.
    W = symmetric_knn_weights(xy, 4)
    gwr_I, gwr_p = moran_permutation(np.asarray(res.resid_response).reshape(-1), W, n_perm=9999)

    meta = {
        "bandwidth": float(bw),
        "kernel": "adaptive bisquare",
        "criterion": "AICc",
        "AICc": float(res.aicc),
        "R2": float(res.R2),
        "adjusted_R2": float(res.adj_R2),
        "residual_morans_I_k4": float(gwr_I),
        "residual_moran_two_sided_p": float(gwr_p),
        "predictors": predictors,
    }
    (outdir / "gwr_model_diagnostics.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("GWR complete")
    print(json.dumps(meta, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gis", required=True, type=Path)
    ap.add_argument("--target", required=True, type=Path)
    ap.add_argument("--outdir", required=True, type=Path)
    ap.add_argument("--target-col", default="gwr_pm25_mean_ugm3")
    ap.add_argument("--spec", choices=["primary", *SENSITIVITY_SPECS.keys()], default="primary")
    ap.add_argument("--min-stations", type=int, default=80)
    ap.add_argument("--vif-threshold", type=float, default=5.0)
    ap.add_argument("--corr-threshold", type=float, default=0.80)
    ap.add_argument("--moran-k", type=int, default=4)
    ap.add_argument("--moran-permutations", type=int, default=9999)
    ap.add_argument("--pre-gwr-only", action="store_true", help="Stop after OLS/VIF/Moran diagnostics")
    args = ap.parse_args()

    predictors = PRIMARY_PREDICTORS if args.spec == "primary" else SENSITIVITY_SPECS[args.spec]
    args.outdir.mkdir(parents=True, exist_ok=True)

    gis = pd.read_csv(args.gis)
    target = pd.read_csv(args.target)
    d = prepare_model_table(gis, target, args.target_col, predictors)

    if len(d) < args.min_stations:
        raise SystemExit(f"FAIL: only {len(d)} GWR-eligible stations; prespecified minimum is {args.min_stations}")

    Xz, y, xy, ols, diag = diagnostics(
        d, predictors, args.target_col, args.outdir,
        args.vif_threshold, args.corr_threshold, args.moran_k, args.moran_permutations,
    )
    print("PRE-GWR GATE PASSED")
    print(json.dumps(diag, indent=2))

    if args.pre_gwr_only:
        return

    fit_gwr(d, Xz, y, xy, predictors, args.outdir)


if __name__ == "__main__":
    main()
