#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

EXPECTED_HASHES = {
    "airgradient_hourly_openaq.csv.gz": "d71bd86f6500ed41f4e2ad8630adb046a29e94761dbcade8b684c1dc28d69111",
    "gwr_FINAL_8080_results.csv": "8b329df41ec7ed7a3f91503159b073efe2f69fde3f757b420e6d211ca3c71111",
    "gwr_target_8080.csv": "291aeabca506641fbf86d586a31a573cae83bd160e6a61010c93184f0666ed66",
    "gwr_dataset_8080_133.csv": "f69d33bcccfffc46573a746f71c6fe48c4b3b8f99a681c5a8b8faed709bf09c8",
}


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, required=True)
    args=ap.parse_args()
    ddir=args.data_dir

    for name, expected in EXPECTED_HASHES.items():
        p=ddir/name
        if not p.exists():
            raise FileNotFoundError(p)
        got=sha256(p)
        if got!=expected:
            raise AssertionError(f"SHA-256 mismatch for {name}: {got}")

    hourly=pd.read_csv(ddir/"airgradient_hourly_openaq.csv.gz", compression="gzip")
    required={"parameter","ts_utc","station_id","source","value_ugm3"}
    if required-set(hourly):
        raise AssertionError(f"Hourly AirGradient file missing {sorted(required-set(hourly))}")
    if len(hourly)!=130_816:
        raise AssertionError(f"Expected 130,816 hourly rows, found {len(hourly)}")
    if hourly.station_id.nunique()!=141:
        raise AssertionError("Expected 141 AirGradient stations")
    if set(hourly.parameter.astype(str).str.lower().unique())!={"pm25"}:
        raise AssertionError("Spatial hourly archive must be PM2.5-only")
    if set(hourly.source.astype(str).str.lower().unique())!={"airgradient"}:
        raise AssertionError("Spatial hourly archive must be AirGradient-only")
    if hourly.isna().any().any():
        raise AssertionError("Missing values found in spatial hourly archive")
    if (pd.to_numeric(hourly.value_ugm3,errors="coerce")<0).any():
        raise AssertionError("Negative PM2.5 value found")
    ts=pd.to_datetime(hourly.ts_utc,utc=True,errors="raise")
    if hourly.assign(_ts=ts).duplicated(["station_id","_ts"]).any():
        raise AssertionError("Duplicate AirGradient station-hour keys")
    counts=hourly.assign(_ts=ts).groupby("_ts").station_id.nunique()
    if counts.size!=956:
        raise AssertionError(f"Expected 956 distinct observed hours, found {counts.size}")
    if counts.min()<132:
        raise AssertionError(f"Unexpected low network coverage; minimum reporting stations={counts.min()}")

    target=pd.read_csv(ddir/"gwr_target_8080.csv")
    model=pd.read_csv(ddir/"gwr_dataset_8080_133.csv")
    summary=pd.read_csv(ddir/"gwr_FINAL_8080_results.csv")

    if len(target)!=133 or target.station_id.nunique()!=133:
        raise AssertionError("GWR target must contain 133 unique stations")
    if len(model)!=133 or model.station_id.nunique()!=133:
        raise AssertionError("GWR model table must contain 133 unique stations")
    if set(target.station_id.astype(str)) != set(model.station_id.astype(str)):
        raise AssertionError("GWR target/model station sets differ")
    if target.isna().any().any() or model.isna().any().any():
        raise AssertionError("Missing values in final GWR target/model table")
    if not target.eligible_8080.astype(bool).all():
        raise AssertionError("All final GWR targets must pass eligible_8080")
    if float(target.coverage.min()) < 0.80:
        raise AssertionError("Final GWR target contains station coverage below 80%")

    sm=summary.set_index("metric")
    checks={
        ("n_stations","OLS"):133.0,
        ("n_stations","GWR"):133.0,
        ("common_hours","OLS"):956.0,
        ("R2","OLS"):0.514,
        ("R2","GWR"):0.773,
        ("RMSE_ugm3","OLS"):5.920,
        ("RMSE_ugm3","GWR"):4.050,
        ("AICc","OLS"):867.700,
        ("AICc","GWR"):821.300,
        ("residual_Moran_I","OLS"):0.282,
        ("residual_Moran_I","GWR"):0.101,
        ("median_local_condition","GWR"):29.900,
    }
    for (metric,col), expected in checks.items():
        got=float(sm.loc[metric,col])
        if not np.isclose(got, expected, rtol=0, atol=1e-12):
            raise AssertionError(f"Unexpected {metric}/{col}: {got} != {expected}")

    print("PASS: spatial archive hashes match")
    print("PASS: AirGradient hourly archive has 130,816 rows, 141 stations, 956 observed hours and no duplicate station-hour keys")
    print("PASS: final 80/80 GWR target/model tables contain 133 unique stations with no missing values")
    print("PASS: preserved OLS/GWR summary matches the locked archive")


if __name__=="__main__":
    main()
