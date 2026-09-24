#!/usr/bin/env python3
"""
Prepare the station-level AirGradient PM2.5 target used by GWR.

Primary design
--------------
1) Use the fixed AirGradient campaign window:
   2026-03-17 23:00:00Z to 2026-04-25 09:00:00Z.
2) Keep only "common network hours": hours in which at least 80% of the
   canonical AirGradient stations have a valid PM2.5 observation.
3) For each station, require observations in at least 80% of those common hours.
4) Compute station mean PM2.5 over those common hours. This is the PRIMARY GWR target.
5) Also export median, SD and coverage as diagnostics; they are not alternative
   outcomes unless explicitly declared in the analysis plan.

This prevents stations with different missing-time patterns from being compared as if
they had been observed over the same temporal sample.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

CAMPAIGN_START = pd.Timestamp("2026-03-17 23:00:00", tz="UTC")
CAMPAIGN_END   = pd.Timestamp("2026-04-25 09:00:00", tz="UTC")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hourly", required=True, type=Path,
                    help="Normalized hourly table containing station_id, timestamp_utc and value_ugm3")
    ap.add_argument("--canonical-stations", required=True, type=Path,
                    help="airgradient_station_geometry_features.csv (141 canonical stations)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--min-network-fraction", type=float, default=0.80)
    ap.add_argument("--min-station-fraction", type=float, default=0.80)
    ap.add_argument("--source-col", default="source")
    ap.add_argument("--parameter-col", default="parameter")
    args = ap.parse_args()

    stations = pd.read_csv(args.canonical_stations)
    if len(stations) != 141 or stations.station_id.duplicated().any():
        raise ValueError("Canonical AirGradient station table must contain exactly 141 unique station_id values.")
    canonical = set(stations.station_id.astype(str))

    df = pd.read_csv(args.hourly)
    required = {"station_id","timestamp_utc","value_ugm3"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Hourly table is missing required columns: {sorted(missing)}")

    if args.source_col in df.columns:
        df = df[df[args.source_col].astype(str).str.lower().eq("airgradient")].copy()
    if args.parameter_col in df.columns:
        p = df[args.parameter_col].astype(str).str.lower().str.replace(".", "", regex=False).str.replace("_","", regex=False)
        df = df[p.isin(["pm25","pm2.5".replace(".","")])].copy()

    df["station_id"] = df["station_id"].astype(str)
    df = df[df.station_id.isin(canonical)].copy()
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True, errors="coerce")
    df["value_ugm3"] = pd.to_numeric(df["value_ugm3"], errors="coerce")
    df = df[
        df.timestamp_utc.between(CAMPAIGN_START, CAMPAIGN_END, inclusive="both")
        & df.value_ugm3.notna()
        & (df.value_ugm3 >= 0)
    ].copy()

    # Enforce one value per station-hour. Duplicate averaging is forbidden because duplicates
    # indicate an upstream data issue, not repeated independent measurements.
    dup = df.duplicated(["station_id","timestamp_utc"], keep=False)
    if dup.any():
        ex = df.loc[dup, ["station_id","timestamp_utc"]].head(10)
        raise ValueError("Duplicate station_id + timestamp_utc rows found. Resolve upstream before GWR.\n"
                         + ex.to_string(index=False))

    n_station = len(canonical)
    hourly_network_n = df.groupby("timestamp_utc")["station_id"].nunique()
    min_network_n = int(np.ceil(args.min_network_fraction * n_station))
    common_hours = hourly_network_n[hourly_network_n >= min_network_n].index

    if len(common_hours) < 24 * 7:
        raise ValueError(f"Only {len(common_hours)} common network hours remain; too little for a stable campaign summary.")

    d = df[df.timestamp_utc.isin(common_hours)].copy()
    g = d.groupby("station_id")["value_ugm3"]
    out = g.agg(
        gwr_pm25_mean_ugm3="mean",
        pm25_median_ugm3="median",
        pm25_sd_ugm3="std",
        n_common_hours_observed="count",
    ).reset_index()
    out["n_common_hours_total"] = len(common_hours)
    out["common_hour_coverage"] = out["n_common_hours_observed"] / len(common_hours)
    out["gwr_eligible"] = out["common_hour_coverage"] >= args.min_station_fraction

    # Add all canonical stations so exclusions are explicit.
    out = stations[["station_id","station_name","lat","lon"]].merge(out, on="station_id", how="left")
    out["gwr_eligible"] = out["gwr_eligible"].fillna(False)
    out["campaign_start_utc"] = str(CAMPAIGN_START)
    out["campaign_end_utc"] = str(CAMPAIGN_END)
    out["min_network_fraction"] = args.min_network_fraction
    out["min_station_fraction"] = args.min_station_fraction

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)

    print(f"Common network hours: {len(common_hours)}")
    print(f"Eligible stations: {int(out.gwr_eligible.sum())} / {len(out)}")
    print(args.out)

if __name__ == "__main__":
    main()
