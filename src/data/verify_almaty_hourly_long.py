#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

EXPECTED_SHA256 = "1188fc9d87ac3f0a3a947c81ec5083646f4703620e0e3db7ed48c3d90f57b8f8"
EXPECTED_ROWS = 613_722
EXPECTED_PARAM_ROWS = {"pm25": 355_450, "pm10": 258_272}
EXPECTED_STATIONS = 11
EXPECTED_SYNC_ROWS = 237_783
EXPECTED_COLUMNS = ["parameter", "ts_utc", "station_id", "source", "value_ugm3"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--qc-out", type=Path)
    args = ap.parse_args()

    got_sha = sha256(args.data)
    if got_sha != EXPECTED_SHA256:
        raise AssertionError(f"SHA-256 mismatch: {got_sha}")

    d = pd.read_csv(args.data, compression="gzip")
    if list(d.columns) != EXPECTED_COLUMNS:
        raise AssertionError(f"Unexpected schema: {list(d.columns)}")
    if len(d) != EXPECTED_ROWS:
        raise AssertionError(f"Unexpected row count: {len(d)}")
    if d.station_id.nunique() != EXPECTED_STATIONS:
        raise AssertionError(f"Unexpected station count: {d.station_id.nunique()}")
    if set(d.source.astype(str).str.lower().unique()) != {"kgmt"}:
        raise AssertionError("Only source=kgmt is allowed in the locked table")
    if d.isna().any().any():
        raise AssertionError("Missing values found")

    values = pd.to_numeric(d.value_ugm3, errors="coerce")
    if not np.isfinite(values).all():
        raise AssertionError("Non-finite values found")
    if (values < 0).any():
        raise AssertionError("Negative concentrations found")

    dup = d.duplicated(["parameter", "station_id", "ts_utc"], keep=False)
    if dup.any():
        raise AssertionError(f"Duplicate parameter/station/time rows: {int(dup.sum())}")

    counts = d.parameter.value_counts().to_dict()
    if counts != EXPECTED_PARAM_ROWS:
        raise AssertionError(f"Unexpected pollutant counts: {counts}")

    # Parse all UTC timestamps and verify the exact synchronized PM2.5/PM10 support.
    ts = pd.to_datetime(d.ts_utc, utc=True, errors="raise")
    x = d.assign(_ts=ts)
    wide = d.pivot(index=["station_id", "ts_utc"], columns="parameter", values="value_ugm3")
    both = wide.dropna(subset=["pm25", "pm10"])
    if len(both) != EXPECTED_SYNC_ROWS:
        raise AssertionError(f"Unexpected synchronized PM2.5/PM10 count: {len(both)}")

    report = {
        "sha256": got_sha,
        "rows": int(len(d)),
        "stations": int(d.station_id.nunique()),
        "parameter_rows": {k: int(v) for k, v in counts.items()},
        "synchronized_pm25_pm10_station_hours": int(len(both)),
        "same_hour_pearson_r": float(both[["pm25", "pm10"]].corr(method="pearson").iloc[0,1]),
        "same_hour_spearman_rho": float(both[["pm25", "pm10"]].corr(method="spearman").iloc[0,1]),
        "first_ts_utc": x._ts.min().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_ts_utc": x._ts.max().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "missing_cells": int(d.isna().sum().sum()),
        "negative_values": int((values < 0).sum()),
        "duplicate_keys": int(dup.sum()),
    }
    if args.qc_out:
        args.qc_out.parent.mkdir(parents=True, exist_ok=True)
        args.qc_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("PASS: almaty_hourly_long.csv.gz matches the locked SHA-256")
    print("PASS: 613,722 KGMT rows = 355,450 PM2.5 + 258,272 PM10")
    print("PASS: 11 stations, no missing/negative/non-finite values, no duplicate keys")
    print("PASS: 237,783 exact synchronized PM2.5/PM10 station-hours")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
