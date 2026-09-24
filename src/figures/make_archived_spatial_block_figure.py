#!/usr/bin/env python3
"""Render manuscript Figure 7 from the recovered archive
data/archived/spatial_block_cv_107/spatial_block_cv_summary.csv (found in
almaty_review_v4.zip on 2026-09-22; the code that generated it was not
found — see docs/FIGURE_MAPPING.md). This plots the archived numbers as-is;
it does not recompute anything.
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

    d = pd.read_csv(root / "data/archived/spatial_block_cv_107/spatial_block_cv_summary.csv")
    order = ["IDW", "Quadratic", "Linear", "RF_coordinates", "XGB_coordinates"]
    d = d.set_index("model").reindex(order).reset_index()

    x = np.arange(len(order))
    width = 0.36
    fig, ax = plt.subplots(figsize=(9, 5.8))
    ax.bar(x - width / 2, d.RMSE_pooled, width, label="Pooled RMSE")
    ax.bar(x + width / 2, d.RMSE_block_macro, width, label="Block-macro RMSE")
    ax.set_xticks(x, order, rotation=20, ha="right")
    ax.set_ylabel("RMSE (\u00b5g/m\u00b3)")
    ax.set_title(
        "Archived spatial-block transfer sensitivity, 107 AirGradient stations\n"
        "(recovered archive, 2026-09-22 \u2014 see docs/FIGURE_MAPPING.md)"
    )
    ax.legend(frameon=False)
    fig.tight_layout()
    out = root / "figures/fig_spatial_block_cv_107_archived.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
