#!/usr/bin/env python3
"""
Same-sensor monitoring-network representativeness (manuscript Figure 6).

Compares the KGMT-matched 11-site AirGradient geometry (each KGMT reference
station paired with its single nearest AirGradient station, from
`data/derived/baseline/kgmt_station_geometry_features.csv`) against random
11-site AirGradient alternatives, using daily-mean PM2.5 MAE against the
co-located/paired KGMT station as the representativeness metric.

This is a NEW computation, not a recovered historical archive: no archived
per-pair MAE table for this specific figure was supplied with this
repository. The method follows the manuscript's Figure 6 caption ("KGMT-
matched 11-site AirGradient geometry ... daily-mean MAE ... median random
11-site alternatives ... error bar shows the match[ed] ...") as closely as
the caption text specifies, and is documented here rather than assumed.

Input: an hourly long table with columns
    parameter, ts_utc, station_id, source, value_ugm3
(source in {"kgmt", "airgradient"}; only pm25 rows are used), for example
the `almaty_hourly_long.csv.gz` already hash-locked in this repository, or
a fuller multi-source export limited to the same five columns after
filtering. This script does not require or read any columns/sources beyond
that; it does not use, and will ignore, any other pollutant or network
present in a wider input file.

Method:
1. Restrict to rows where both networks have data (the AirGradient
   operating window), and compute a daily UTC mean per station.
2. For each of the 11 KGMT stations, take its matched AirGradient station
   (nearest_airgradient_id) and compute the daily-mean MAE over days both
   report.
3. Monte Carlo (n_draws, default 2000, fixed seed): for each KGMT station,
   substitute a uniformly random *other* AirGradient station (excluding its
   matched station) and recompute the same MAE; average the 11 per-draw
   MAEs into one "random-network" MAE per draw.
4. Report the matched network's median/IQR MAE against the distribution of
   random-network MAEs.

Every number this script prints or writes is computed from the input file
given on the command line; nothing is hard-coded to match a target value.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def daily_mean(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["date"] = pd.to_datetime(d["ts_utc"], utc=True).dt.date
    return d.groupby(["station_id", "date"], as_index=False)["value_ugm3"].mean()


def pair_mae(kgmt_daily: pd.DataFrame, kgmt_id: str, ag_daily: pd.DataFrame, ag_id: str) -> tuple[float, int]:
    a = kgmt_daily[kgmt_daily.station_id == kgmt_id][["date", "value_ugm3"]].rename(
        columns={"value_ugm3": "kgmt"}
    )
    b = ag_daily[ag_daily.station_id == ag_id][["date", "value_ugm3"]].rename(
        columns={"value_ugm3": "ag"}
    )
    m = a.merge(b, on="date", how="inner")
    if len(m) == 0:
        return float("nan"), 0
    return float(np.mean(np.abs(m.kgmt - m.ag))), len(m)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hourly-long", required=True, type=Path,
                     help="CSV/CSV.GZ with columns parameter, ts_utc, station_id, source, value_ugm3")
    ap.add_argument("--geometry", required=True, type=Path,
                     help="kgmt_station_geometry_features.csv (needs nearest_airgradient_id)")
    ap.add_argument("--outdir", required=True, type=Path)
    ap.add_argument("--n-draws", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260922)
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    src_hash = hashlib.sha256(args.hourly_long.read_bytes()).hexdigest()

    raw = pd.read_csv(args.hourly_long)
    raw = raw[raw.parameter.astype(str).str.lower() == "pm25"]
    kg = raw[raw.source == "kgmt"][["ts_utc", "station_id", "value_ugm3"]]
    ag = raw[raw.source == "airgradient"][["ts_utc", "station_id", "value_ugm3"]]
    if kg.empty or ag.empty:
        raise ValueError("Input must contain both kgmt and airgradient pm25 rows.")

    geom = pd.read_csv(args.geometry)
    matched = dict(zip(geom.station_id, geom.nearest_airgradient_id))
    kgmt_ids = sorted(matched)
    if len(kgmt_ids) != 11:
        raise ValueError(f"Expected 11 KGMT stations in geometry file, found {len(kgmt_ids)}.")

    # Restrict to the AirGradient operating window (both networks present).
    lo = max(kg.ts_utc.min(), ag.ts_utc.min())
    hi = min(kg.ts_utc.max(), ag.ts_utc.max())
    kg = kg[(kg.ts_utc >= lo) & (kg.ts_utc <= hi)]
    ag = ag[(ag.ts_utc >= lo) & (ag.ts_utc <= hi)]

    kg_daily = daily_mean(kg)
    ag_daily = daily_mean(ag)
    ag_station_ids = sorted(ag_daily.station_id.unique())

    # Step 2: matched-pair MAE.
    matched_rows = []
    for kid in kgmt_ids:
        aid = matched[kid]
        mae, n_days = pair_mae(kg_daily, kid, ag_daily, aid)
        matched_rows.append({"kgmt_station_id": kid, "airgradient_station_id": aid,
                              "n_overlap_days": n_days, "daily_mean_MAE_ugm3": mae})
    matched_df = pd.DataFrame(matched_rows)

    # Step 3: Monte Carlo random-alternative network MAE.
    rng = np.random.default_rng(args.seed)
    candidates = {
        kid: [s for s in ag_station_ids if s != matched[kid]] for kid in kgmt_ids
    }
    # Precompute MAE for every (kgmt, candidate airgradient) pair once.
    pair_cache: dict[tuple[str, str], tuple[float, int]] = {}
    for kid in kgmt_ids:
        for aid in candidates[kid]:
            pair_cache[(kid, aid)] = pair_mae(kg_daily, kid, ag_daily, aid)

    draw_means = np.empty(args.n_draws)
    for d in range(args.n_draws):
        draw_maes = []
        for kid in kgmt_ids:
            aid = candidates[kid][rng.integers(len(candidates[kid]))]
            mae, n_days = pair_cache[(kid, aid)]
            if n_days > 0 and not np.isnan(mae):
                draw_maes.append(mae)
        draw_means[d] = float(np.mean(draw_maes)) if draw_maes else float("nan")

    matched_network_mae = float(matched_df.daily_mean_MAE_ugm3.mean())
    summary = {
        "source_file": str(args.hourly_long),
        "source_sha256": src_hash,
        "window_start_utc": str(lo),
        "window_end_utc": str(hi),
        "n_kgmt_stations": len(kgmt_ids),
        "n_airgradient_candidate_pool": len(ag_station_ids),
        "n_monte_carlo_draws": args.n_draws,
        "monte_carlo_seed": args.seed,
        "matched_network_mean_daily_MAE_ugm3": matched_network_mae,
        "random_network_median_daily_MAE_ugm3": float(np.nanmedian(draw_means)),
        "random_network_p25_daily_MAE_ugm3": float(np.nanpercentile(draw_means, 25)),
        "random_network_p75_daily_MAE_ugm3": float(np.nanpercentile(draw_means, 75)),
        "matched_minus_random_median_ugm3": matched_network_mae - float(np.nanmedian(draw_means)),
    }

    matched_df.to_csv(args.outdir / "same_sensor_matched_pairs.csv", index=False)
    pd.DataFrame({"draw": np.arange(args.n_draws), "random_network_mean_MAE_ugm3": draw_means}).to_csv(
        args.outdir / "same_sensor_random_network_draws.csv", index=False
    )
    (args.outdir / "same_sensor_summary.json").write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
