#!/usr/bin/env python3
"""Render the reconstructed spatial-block transfer-sensitivity figure
(manuscript Figure 7) from results/verified/spatial_block_cv_107/, produced
by src/spatial/reproduce_spatial_block_cv.py and
src/spatial/add_coordinate_xgboost_baseline.py. See docs/FIGURE_MAPPING.md
for the important caveat that this reconstruction does NOT confirm the
manuscript's claim that XGBoost has the lowest pooled/block-macro RMSE.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    args = ap.parse_args()
    root = args.repo_root
    src = root / "results/verified/spatial_block_cv_107"

    d = pd.read_csv(src / "spatial_block_cv_summary_with_xgboost.csv")
    order = ["TrainingMean", "IDW", "Quadratic", "Linear",
              "XGBoost_coord_only", "XGBoost_coord_only_tuned"]
    d = d.set_index("model").reindex(order).reset_index()

    x = np.arange(len(order))
    width = 0.36
    fig, ax = plt.subplots(figsize=(9, 5.8))
    ax.bar(x - width / 2, d.RMSE_pooled, width, label="Pooled RMSE")
    ax.bar(x + width / 2, d.RMSE_block_macro, width, label="Block-macro RMSE")
    ax.set_xticks(x, order, rotation=20, ha="right")
    ax.set_ylabel("RMSE (\u00b5g/m\u00b3)")
    ax.set_title(
        "Reconstructed spatial-block transfer sensitivity, 107 AirGradient stations\n"
        "(NEW reconstruction \u2014 does not confirm XGBoost superiority, see docs/FIGURE_MAPPING.md)"
    )
    ax.legend(frameon=False)
    fig.tight_layout()
    out = root / "figures/fig_verified_spatial_block_transfer_sensitivity.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
