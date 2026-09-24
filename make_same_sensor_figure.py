#!/usr/bin/env python3
"""Render the same-sensor representativeness figure (manuscript Figure 6)
from results/verified/same_sensor_representativeness/, which is produced by
src/spatial/build_same_sensor_representativeness.py. See
docs/FIGURE_MAPPING.md for what this figure does and does not confirm about
the manuscript's Figure 6.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    args = ap.parse_args()
    root = args.repo_root
    src = root / "results/verified/same_sensor_representativeness"

    matched = pd.read_csv(src / "same_sensor_matched_pairs.csv").dropna(
        subset=["daily_mean_MAE_ugm3"]
    )
    draws = pd.read_csv(src / "same_sensor_random_network_draws.csv")
    summary = json.loads((src / "same_sensor_summary.json").read_text())

    fig, ax = plt.subplots(figsize=(7, 5.5))
    bp = ax.boxplot(
        draws.random_network_mean_MAE_ugm3, positions=[0], widths=0.5,
        patch_artist=True, showfliers=False,
    )
    bp["boxes"][0].set_facecolor("#cfd8dc")
    ax.errorbar(
        [1], [matched.daily_mean_MAE_ugm3.mean()],
        yerr=[[matched.daily_mean_MAE_ugm3.mean() - matched.daily_mean_MAE_ugm3.min()],
              [matched.daily_mean_MAE_ugm3.max() - matched.daily_mean_MAE_ugm3.mean()]],
        fmt="o", color="#c62828", capsize=6, markersize=9,
        label="Matched (range across pairs)",
    )
    ax.scatter(
        np.full(len(matched), 1), matched.daily_mean_MAE_ugm3,
        color="#c62828", alpha=0.5, zorder=3, s=25,
    )
    ax.set_xticks([0, 1])
    ax.set_xticklabels([
        f"Random 11-site\nalternatives (n={summary['n_monte_carlo_draws']} draws)",
        f"KGMT-matched\nAirGradient site\n(n={len(matched)} valid pairs)",
    ])
    ax.set_ylabel("Daily-mean PM2.5 MAE vs. paired KGMT station (\u00b5g/m\u00b3)")
    ax.set_title("Same-sensor monitoring-network representativeness")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    out = root / "figures/fig_verified_same_sensor_representativeness.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
