#!/usr/bin/env python3
"""Leakage-safe exact UTC join of station-level ERA5 to forecast-origin rows."""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd

PRIMARY = [
    "era5_t2m_c", "era5_rh2m_pct", "era5_sp_hpa",
    "era5_u10_ms", "era5_v10_ms", "era5_tp_mm_1h",
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--forecast-rows", type=Path, required=True)
    ap.add_argument("--era5", type=Path, required=True)
    ap.add_argument("--origin-col", default="timestamp_utc")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    f = pd.read_csv(args.forecast_rows)
    e = pd.read_csv(args.era5)
    need_f = {"station_id", args.origin_col}
    need_e = {"station_id", "timestamp_utc", *PRIMARY}
    if need_f - set(f): raise ValueError(f"Forecast rows missing {sorted(need_f-set(f))}")
    if need_e - set(e): raise ValueError(f"ERA5 table missing {sorted(need_e-set(e))}")

    f[args.origin_col] = pd.to_datetime(f[args.origin_col], utc=True, errors="raise")
    e["timestamp_utc"] = pd.to_datetime(e["timestamp_utc"], utc=True, errors="raise")
    if e.duplicated(["station_id","timestamp_utc"]).any():
        raise ValueError("Duplicate ERA5 station-hour keys")

    e = e[["station_id","timestamp_utc",*PRIMARY]].rename(columns={"timestamp_utc":"era5_valid_time_utc"})
    out = f.merge(
        e,
        left_on=["station_id", args.origin_col],
        right_on=["station_id", "era5_valid_time_utc"],
        how="left",
        validate="many_to_one",
    )
    if len(out) != len(f):
        raise AssertionError("ERA5 join changed row count")
    matched = out["era5_valid_time_utc"].notna()
    if (out.loc[matched, "era5_valid_time_utc"] > out.loc[matched, args.origin_col]).any():
        raise AssertionError("Future ERA5 timestamp detected")
    if not (out.loc[matched, "era5_valid_time_utc"] == out.loc[matched, args.origin_col]).all():
        raise AssertionError("Primary ERA5 join must be exact at forecast origin t")

    out.to_csv(args.out, index=False)
    print(f"rows={len(out)} matched={int(matched.sum())} missing={int((~matched).sum())} coverage={matched.mean():.6f}")
    print(args.out)

if __name__ == "__main__":
    main()
