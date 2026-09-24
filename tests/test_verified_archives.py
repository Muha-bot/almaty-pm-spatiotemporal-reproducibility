"""Pytest wrappers around the existing src/*/verify_*.py scripts.

These tests do not compute new scientific results. They only assert that the
independent verification scripts (already used by `make verify`) exit
successfully against the data shipped in this repository, so that
`pytest -q` can be used as a single CI entry point (mirrors this project's
own convention of a `tests/` folder collecting all integrity checks).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(args):
    result = subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_baseline_archive_reproduces():
    out = _run([
        "src/forecasting/verify_archived_results.py",
        "--data-dir", "data/derived/baseline",
        "--out-dir", "results/verified",
    ])
    assert "PASS" in out


def test_hourly_long_matches_locked_hash():
    out = _run([
        "src/data/verify_almaty_hourly_long.py",
        "--data", "data/derived/baseline/almaty_hourly_long.csv.gz",
        "--qc-out", "results/verified/almaty_hourly_long_qc_recomputed.json",
    ])
    assert "PASS" in out


def test_spatial_archive_matches_locked_hashes():
    out = _run([
        "src/spatial/verify_spatial_archive.py",
        "--data-dir", "data/derived/spatial",
    ])
    assert "PASS" in out


def test_new_figures_6_7_self_consistent():
    out = _run(["src/spatial/verify_new_figures_6_7.py", "--repo-root", "."])
    assert out.count("PASS") == 7
