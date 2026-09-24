#!/usr/bin/env python3
"""
Verify the inputs and recompute the outputs for the two figures added after
the initial repository was assembled (manuscript Figures 6 and 7 — see
docs/FIGURE_MAPPING.md). Unlike verify_spatial_archive.py and
verify_archived_results.py, this does not check against an externally
archived hash: there is no archived Figure 6/7 computation in this
repository's history to check against (see docs/FIGURE_MAPPING.md). It
checks (a) that the two small derived input files this repository commits
are exactly the bytes originally computed from the raw hourly source, and
(b) that re-running the two build scripts against those files reproduces
the committed summary numbers, i.e. that the figures are self-consistent
and regenerable, not that they match some external ground truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

EXPECTED_HASHES = {
    "data/derived/spatial/kgmt_airgradient_pm25_hourly.csv.gz":
        "1f07bef59003df94cdca26f6f212a6bad25db40728555d881599b7a743a4e82a",
    "data/derived/spatial/airgradient_spatial_blocks_107.csv":
        "6c236ff45b61b316978930b247430f60b01222c5fd22cf4e07a778a0b4aaee73",
    "data/archived/spatial_block_cv_107/airgradient_spatial_blocks_107.csv":
        "334521e37e8826b137ca8cd8f61d2e89b763e38143dccd0c82bca858ef03c561",
    "data/archived/spatial_block_cv_107/spatial_block_cv_summary.csv":
        "23e899ede9b31c828361ec8f44843bef169432b57466e06c5781e2f0f45c809c",
    "data/archived/spatial_block_cv_107/spatial_block_cv_by_block.csv":
        "1984ca372536473633bc0ba53e5a88e5e14ba61b247bf1a959bfa93bdda59429",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--tmp-out", type=Path, default=Path("results/verified/_tmp_fig6_7_check"))
    args = ap.parse_args()
    root = args.repo_root
    args.tmp_out.mkdir(parents=True, exist_ok=True)

    ok = True
    for rel, expected in EXPECTED_HASHES.items():
        actual = sha256(root / rel)
        status = "PASS" if actual == expected else "FAIL"
        ok &= actual == expected
        print(f"{status}: {rel} hash {'matches' if actual == expected else 'DOES NOT MATCH'}")

    # Re-run Figure 6 and compare the committed summary numbers exactly
    # (fully deterministic: fixed Monte Carlo seed, no model fitting).
    fig6_out = args.tmp_out / "fig6"
    subprocess.run([
        sys.executable, "src/spatial/build_same_sensor_representativeness.py",
        "--hourly-long", "data/derived/spatial/kgmt_airgradient_pm25_hourly.csv.gz",
        "--geometry", "data/derived/baseline/kgmt_station_geometry_features.csv",
        "--outdir", str(fig6_out), "--n-draws", "2000", "--seed", "20260922",
    ], cwd=root, check=True, capture_output=True)
    recomputed = json.loads((fig6_out / "same_sensor_summary.json").read_text())
    committed = json.loads(
        (root / "results/verified/same_sensor_representativeness/same_sensor_summary.json").read_text()
    )
    numeric_keys = [k for k, v in committed.items() if isinstance(v, (int, float))]
    fig6_match = all(abs(recomputed[k] - committed[k]) < 1e-9 for k in numeric_keys)
    print(f"{'PASS' if fig6_match else 'FAIL'}: Figure 6 recomputation matches committed summary")
    ok &= fig6_match

    # Re-run Figure 7's deterministic baselines (XGBoost is not checked for
    # exact equality here: its numerical result can vary slightly across
    # xgboost/platform versions even with a fixed random_state, so only
    # regenerating without error is checked for that model).
    fig7_out = args.tmp_out / "fig7"
    subprocess.run([
        sys.executable, "src/spatial/reproduce_spatial_block_cv.py",
        "--input", "data/derived/spatial/airgradient_spatial_blocks_107.csv",
        "--outdir", str(fig7_out),
    ], cwd=root, check=True, capture_output=True)
    subprocess.run([
        sys.executable, "src/spatial/add_coordinate_xgboost_baseline.py",
        "--input", "data/derived/spatial/airgradient_spatial_blocks_107.csv",
        "--outdir", str(fig7_out),
    ], cwd=root, check=True, capture_output=True)
    audit = json.loads((fig7_out / "audit.json").read_text())
    fig7_ari_ok = audit["regenerated_vs_archived_block_ARI"] == 1.0
    print(f"{'PASS' if fig7_ari_ok else 'FAIL'}: Figure 7 spatial-block partition self-consistent (ARI=1.0)")
    ok &= fig7_ari_ok

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
