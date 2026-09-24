#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def save_validation_selected(base: Path, out: Path):
    d = pd.read_csv(base / "validation_selected_primary_test_results_verified.csv")
    d["task"] = d["target"].str.upper() + " +" + d["horizon"].astype(str) + " h"
    tasks = ["PM25 +1 h", "PM25 +24 h", "PM10 +1 h", "PM10 +24 h"]
    d["task"] = pd.Categorical(d["task"], tasks, ordered=True)
    d = d.sort_values(["task", "ablation"])
    x = np.arange(len(tasks))
    width = 0.36
    fig, ax = plt.subplots(figsize=(10, 5.8))
    for i, abl in enumerate(["A0_history", "A1_crossPM"]):
        g = d[d.ablation.eq(abl)].set_index("task").reindex(tasks)
        ax.bar(x + (i - 0.5) * width, g.test_RMSE, width, label=abl)
    ax.set_xticks(x, tasks)
    ax.set_ylabel("Independent-test RMSE (µg/m³)")
    ax.set_title("Validation-selected independent-test RMSE")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(out / "fig_verified_validation_selected_rmse.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def save_crosspm(base: Path, out: Path):
    d = pd.read_csv(base / "crossPM_ablation_test_deltas_verified.csv")
    d["task"] = d.target.str.upper() + " +" + d.horizon.astype(str) + " h"
    labels = [f"{r.task}\n{r.model}" for r in d.itertuples()]
    vals = d.delta_RMSE_A1_minus_A0.to_numpy()
    fig, ax = plt.subplots(figsize=(12, 6.2))
    ax.bar(np.arange(len(vals)), vals)
    ax.axhline(0, linewidth=1)
    ax.set_xticks(np.arange(len(vals)), labels, rotation=45, ha="right")
    ax.set_ylabel("ΔRMSE = A1 − A0 (µg/m³)")
    ax.set_title("Cross-pollutant history has small, mixed effects")
    fig.tight_layout()
    fig.savefig(out / "fig_verified_crosspm_delta_rmse.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def save_geometry(base: Path, out: Path):
    ag = pd.read_csv(base / "airgradient_station_geometry_features.csv")
    kg = pd.read_csv(base / "kgmt_station_geometry_features.csv")
    ag_by_id = ag.set_index("station_id")
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter(ag.x_utm_m / 1000, ag.y_utm_m / 1000, s=12, label="AirGradient (n=141)")
    ax.scatter(kg.x_utm_m / 1000, kg.y_utm_m / 1000, s=52, marker="^", label="KGMT (n=11)")
    for r in kg.itertuples():
        a = ag_by_id.loc[r.nearest_airgradient_id]
        ax.plot([r.x_utm_m / 1000, a.x_utm_m / 1000], [r.y_utm_m / 1000, a.y_utm_m / 1000], linewidth=0.7)
    ax.set_xlabel("UTM easting (km), EPSG:32643")
    ax.set_ylabel("UTM northing (km), EPSG:32643")
    ax.set_title("Monitoring-network geometry and one-to-one nearest matching")
    ax.legend(frameon=False)
    ax.set_aspect("equal", adjustable="datalim")
    fig.tight_layout()
    fig.savefig(out / "fig_verified_network_geometry.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def save_gwr(spatial: Path, out: Path):
    d = pd.read_csv(spatial / "gwr_FINAL_8080_results.csv").set_index("metric")
    specs = [
        ("R2", "R²", "fig_verified_gwr_r2.png"),
        ("RMSE_ugm3", "RMSE (µg/m³)", "fig_verified_gwr_rmse.png"),
        ("residual_Moran_I", "Residual Moran's I", "fig_verified_gwr_residual_moran.png"),
        ("AICc", "AICc", "fig_verified_gwr_aicc.png"),
    ]
    for metric, ylabel, name in specs:
        vals = [float(d.loc[metric, "OLS"]), float(d.loc[metric, "GWR"])]
        fig, ax = plt.subplots(figsize=(5.5, 4.5))
        ax.bar(["OLS", "GWR"], vals)
        ax.set_ylabel(ylabel)
        ax.set_title(f"OLS versus GWR: {ylabel}")
        for i, v in enumerate(vals):
            ax.text(i, v, f"{v:.3g}", ha="center", va="bottom")
        fig.tight_layout()
        fig.savefig(out / name, dpi=300, bbox_inches="tight")
        plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, required=True)
    args = ap.parse_args()
    root = args.repo_root.resolve()
    base = root / "data/derived/baseline"
    spatial = root / "data/derived/spatial"
    out = root / "figures"
    out.mkdir(parents=True, exist_ok=True)
    save_validation_selected(base, out)
    save_crosspm(base, out)
    save_geometry(base, out)
    save_gwr(spatial, out)
    print(f"Wrote verified figures to {out}")


if __name__ == "__main__":
    main()
