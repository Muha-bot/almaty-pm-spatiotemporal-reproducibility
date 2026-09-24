#!/usr/bin/env python3
"""Prepare the leakage-safe ERA5 A2 meteorological block for the Almaty PM2.5/PM10 study.

Scientific contract
-------------------
* Forecasting targets: KGMT PM2.5 and PM10, horizons +1 h and +24 h.
* ERA5 source: C3S/ECMWF ERA5 hourly data on single levels (0.25 degree grid),
  DOI 10.24381/cds.adbb2d47.
* Core A2 model inputs at forecast origin t:
    t2m_c, rh_pct, sp_hpa, u10_ms, v10_ms, tp_mm_1h
* Boundary-layer height (blh_m) is prespecified sensitivity only.
* No ERA5 value later than forecast origin t may enter an A2 row.
* Spatial extraction is bilinear from the parent ERA5 grid; nearest-grid extraction
  is a sensitivity check and is not silently substituted.

The script can (1) write a reproducible request manifest without credentials,
(2) download monthly ERA5 NetCDF files when the user's CDS credentials are already
configured locally, and (3) interpolate downloaded fields to the 11 KGMT stations.
No API secret is read from command-line arguments or written to output files.
"""
from __future__ import annotations

import argparse
import calendar
import json
import math
import os
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

DATASET = "reanalysis-era5-single-levels"
DATASET_DOI = "10.24381/cds.adbb2d47"
VARIABLES_CORE = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "surface_pressure",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "total_precipitation",
]
VARIABLES_SENSITIVITY = ["boundary_layer_height"]
ALL_VARIABLES = VARIABLES_CORE + VARIABLES_SENSITIVITY
ALL_TIMES = [f"{h:02d}:00" for h in range(24)]
START = pd.Timestamp("2021-01-01 00:00:00", tz="UTC")  # first year of the locked forecasting training period
END = pd.Timestamp("2025-12-31 23:00:00", tz="UTC")

# KGMT bounds are 43.180754..43.374376 N and 76.817060..77.006407 E.
# These exact 0.25-degree boundaries provide the four surrounding ERA5 nodes
# required for bilinear interpolation at every KGMT location.
AREA = [43.50, 76.75, 43.00, 77.25]  # [north, west, south, east]

SHORT_TO_OUTPUT = {
    "t2m": "t2m_k",
    "d2m": "d2m_k",
    "sp": "sp_pa",
    "u10": "u10_ms",
    "v10": "v10_ms",
    "tp": "tp_m_1h",
    "blh": "blh_m",
}
LONG_TO_SHORT = {
    "2m_temperature": "t2m",
    "2m_dewpoint_temperature": "d2m",
    "surface_pressure": "sp",
    "10m_u_component_of_wind": "u10",
    "10m_v_component_of_wind": "v10",
    "total_precipitation": "tp",
    "boundary_layer_height": "blh",
}


def month_iter(start: pd.Timestamp, end: pd.Timestamp) -> Iterable[tuple[int, int]]:
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1


def days_for_month(y: int, m: int) -> list[str]:
    first = 1
    last = calendar.monthrange(y, m)[1]
    if y == START.year and m == START.month:
        first = START.day
    if y == END.year and m == END.month:
        last = END.day
    return [f"{d:02d}" for d in range(first, last + 1)]


def request_for_month(y: int, m: int) -> dict:
    return {
        "product_type": ["reanalysis"],
        "variable": ALL_VARIABLES,
        "year": [str(y)],
        "month": [f"{m:02d}"],
        "day": days_for_month(y, m),
        "time": ALL_TIMES,
        "data_format": "netcdf",
        "download_format": "unarchived",
        "area": AREA,
    }


def build_manifest(stations: pd.DataFrame) -> dict:
    return {
        "dataset": DATASET,
        "dataset_title": "ERA5 hourly data on single levels from 1940 to present",
        "dataset_doi": DATASET_DOI,
        "provider": "Copernicus Climate Change Service / ECMWF",
        "grid_deg": 0.25,
        "requested_period_utc": {"start": str(START), "end": str(END)},
        "request_area_nwse": AREA,
        "kgmt_coordinate_bounds": {
            "lat_min": float(stations.lat.min()), "lat_max": float(stations.lat.max()),
            "lon_min": float(stations.lon.min()), "lon_max": float(stations.lon.max()),
        },
        "variables_core_A2": VARIABLES_CORE,
        "variables_sensitivity": VARIABLES_SENSITIVITY,
        "core_model_columns": ["t2m_c", "rh_pct", "sp_hpa", "u10_ms", "v10_ms", "tp_mm_1h"],
        "sensitivity_columns": ["blh_m"],
        "core_A2_temporal_definition": "origin-time meteorology only; no meteorological lags or rolling summaries in the primary ablation",
        "spatial_extraction_primary": "bilinear interpolation from 0.25-degree parent ERA5 grid",
        "spatial_extraction_sensitivity": "nearest ERA5 grid point",
        "temporal_join": "exact UTC forecast-origin hour",
        "leakage_rule": "ERA5 timestamp must be <= forecast origin t; never use t+h reanalysis as a predictor",
        "precipitation_definition": "hourly ERA5 accumulation ending at validity time; convert m to mm by x1000",
        "station_count": int(len(stations)),
        "expected_hour_count": int((END - START) / pd.Timedelta(hours=1)) + 1,
        "expected_station_hour_rows": (int((END - START) / pd.Timedelta(hours=1)) + 1) * int(len(stations)),
        "station_ids_unique": bool(stations.station_id.is_unique),
        "monthly_requests": [
            {"year": y, "month": m, "days": days_for_month(y, m)} for y, m in month_iter(START, END)
        ],
    }


def download_months(outdir: Path, overwrite: bool = False) -> None:
    try:
        import cdsapi  # type: ignore
    except ImportError as e:
        raise RuntimeError("cdsapi is not installed. Install it in the execution environment before --download.") from e
    # cdsapi itself resolves ~/.cdsapirc or CDSAPI_* environment variables.
    # Do not accept secrets on the command line and do not log them here.
    client = cdsapi.Client()
    outdir.mkdir(parents=True, exist_ok=True)
    for y, m in month_iter(START, END):
        target = outdir / f"era5_almaty_{y}{m:02d}.nc"
        if target.exists() and target.stat().st_size > 0 and not overwrite:
            print(f"SKIP {target.name}")
            continue
        req = request_for_month(y, m)
        print(f"REQUEST {y}-{m:02d}: {len(req['day'])} days, {len(ALL_VARIABLES)} variables, area={AREA}")
        client.retrieve(DATASET, req, str(target))


def normalize_dataset(ds):
    """Return an xarray Dataset with stable short variable names and `time` coordinate."""
    # Coordinate naming differs across NetCDF encoders.
    rename = {}
    if "valid_time" in ds.coords and "time" not in ds.coords:
        rename["valid_time"] = "time"
    if "latitude" not in ds.coords and "lat" in ds.coords:
        rename["lat"] = "latitude"
    if "longitude" not in ds.coords and "lon" in ds.coords:
        rename["lon"] = "longitude"
    if rename:
        ds = ds.rename(rename)

    # Variable naming can be short GRIB names or long CDS names.
    var_rename = {}
    for long_name, short_name in LONG_TO_SHORT.items():
        if long_name in ds.data_vars and short_name not in ds.data_vars:
            var_rename[long_name] = short_name
    if var_rename:
        ds = ds.rename(var_rename)

    required = {"t2m", "d2m", "sp", "u10", "v10", "tp"}
    missing = required - set(ds.data_vars)
    if missing:
        raise ValueError(f"ERA5 file(s) missing required variables after normalization: {sorted(missing)}")
    for c in ("time", "latitude", "longitude"):
        if c not in ds.coords:
            raise ValueError(f"ERA5 file(s) missing coordinate: {c}")
    # xarray interpolation is safest with ascending coordinates.
    ds = ds.sortby("latitude").sortby("longitude").sortby("time")
    return ds


def magnus_rh_pct(t_c: np.ndarray, td_c: np.ndarray) -> np.ndarray:
    """Relative humidity (%) from temperature and dew point using a standard Magnus approximation."""
    a, b = 17.625, 243.04
    return 100.0 * np.exp((a * td_c / (b + td_c)) - (a * t_c / (b + t_c)))


def process_netcdf(stations: pd.DataFrame, nc_dir: Path, outdir: Path) -> None:
    try:
        import xarray as xr  # type: ignore
    except ImportError as e:
        raise RuntimeError("xarray is required for ERA5 processing.") from e

    files = sorted(nc_dir.glob("era5_almaty_*.nc"))
    if not files:
        raise FileNotFoundError(f"No era5_almaty_*.nc files found in {nc_dir}")

    datasets = []
    for f in files:
        d = xr.open_dataset(f)
        datasets.append(normalize_dataset(d))
    ds = xr.concat(datasets, dim="time").sortby("time")

    # Remove exact duplicate validity times only if values are identical across the whole grid.
    tindex = pd.DatetimeIndex(pd.to_datetime(ds.time.values, utc=True))
    if tindex.duplicated().any():
        dup_times = tindex[tindex.duplicated(keep=False)].unique()
        raise ValueError(f"Duplicate ERA5 validity times found across monthly files: {list(map(str, dup_times[:10]))}")

    ds = ds.sel(time=slice(START.tz_convert(None).to_datetime64(), END.tz_convert(None).to_datetime64()))
    expected_hours = int((END - START) / pd.Timedelta(hours=1)) + 1
    actual_hours = int(ds.sizes.get("time", 0))
    if actual_hours != expected_hours:
        raise ValueError(
            f"ERA5 time grid incomplete after slicing: expected {expected_hours} hourly validity times, found {actual_hours}"
        )
    rows = []
    nearest_rows = []
    vars_to_take = [v for v in ["t2m", "d2m", "sp", "u10", "v10", "tp", "blh"] if v in ds.data_vars]

    for s in stations.itertuples(index=False):
        bil = ds[vars_to_take].interp(latitude=float(s.lat), longitude=float(s.lon), method="linear")
        near = ds[vars_to_take].sel(latitude=float(s.lat), longitude=float(s.lon), method="nearest")
        for obj, sink, method in [(bil, rows, "bilinear"), (near, nearest_rows, "nearest")]:
            frame = obj.to_dataframe().reset_index()
            frame["station_id"] = str(s.station_id)
            frame["station_name"] = str(s.station_name)
            frame["station_lat"] = float(s.lat)
            frame["station_lon"] = float(s.lon)
            frame["extraction_method"] = method
            sink.append(frame)

    def post(frames: list[pd.DataFrame]) -> pd.DataFrame:
        df = pd.concat(frames, ignore_index=True)
        df["timestamp_utc"] = pd.to_datetime(df["time"], utc=True)
        df["t2m_k"] = pd.to_numeric(df["t2m"], errors="coerce")
        df["d2m_k"] = pd.to_numeric(df["d2m"], errors="coerce")
        df["t2m_c"] = df["t2m_k"] - 273.15
        df["d2m_c"] = df["d2m_k"] - 273.15
        df["rh_pct"] = magnus_rh_pct(df["t2m_c"].to_numpy(), df["d2m_c"].to_numpy())
        df["sp_pa"] = pd.to_numeric(df["sp"], errors="coerce")
        df["sp_hpa"] = df["sp_pa"] / 100.0
        df["u10_ms"] = pd.to_numeric(df["u10"], errors="coerce")
        df["v10_ms"] = pd.to_numeric(df["v10"], errors="coerce")
        df["wind_speed_ms"] = np.hypot(df["u10_ms"], df["v10_ms"])
        df["tp_m_1h"] = pd.to_numeric(df["tp"], errors="coerce")
        df["tp_mm_1h"] = df["tp_m_1h"] * 1000.0
        if "blh" in df.columns:
            df["blh_m"] = pd.to_numeric(df["blh"], errors="coerce")
        keep = [
            "station_id", "station_name", "station_lat", "station_lon", "timestamp_utc",
            "t2m_c", "rh_pct", "sp_hpa", "u10_ms", "v10_ms", "wind_speed_ms", "tp_mm_1h",
        ]
        if "blh_m" in df.columns:
            keep.append("blh_m")
        keep.append("extraction_method")
        df = df[keep].sort_values(["station_id", "timestamp_utc"]).reset_index(drop=True)
        if df.duplicated(["station_id", "timestamp_utc"]).any():
            raise ValueError("Duplicate station_id + timestamp_utc after ERA5 interpolation")
        return df

    bil = post(rows)
    near = post(nearest_rows)
    expected_rows = expected_hours * len(stations)
    if len(bil) != expected_rows or len(near) != expected_rows:
        raise ValueError(
            f"ERA5 station-hour row count mismatch: expected {expected_rows}, "
            f"bilinear={len(bil)}, nearest={len(near)}"
        )
    outdir.mkdir(parents=True, exist_ok=True)
    bil.to_csv(outdir / "era5_a2_station_hourly_bilinear.csv", index=False)
    near.to_csv(outdir / "era5_a2_station_hourly_nearest_sensitivity.csv", index=False)

    core = ["t2m_c", "rh_pct", "sp_hpa", "u10_ms", "v10_ms", "tp_mm_1h"]
    audit_rows = []
    for method, df in [("bilinear", bil), ("nearest", near)]:
        for c in core + (["blh_m"] if "blh_m" in df.columns else []):
            x = pd.to_numeric(df[c], errors="coerce")
            audit_rows.append({
                "extraction_method": method,
                "feature": c,
                "n": int(len(x)),
                "n_missing": int(x.isna().sum()),
                "missing_fraction": float(x.isna().mean()),
                "min": float(x.min()) if x.notna().any() else None,
                "median": float(x.median()) if x.notna().any() else None,
                "max": float(x.max()) if x.notna().any() else None,
            })
    audit = pd.DataFrame(audit_rows)
    audit.to_csv(outdir / "era5_a2_feature_audit.csv", index=False)

    coverage = bil.groupby("station_id").agg(
        n_hours=("timestamp_utc", "size"),
        start_utc=("timestamp_utc", "min"),
        end_utc=("timestamp_utc", "max"),
    ).reset_index()
    for c in core:
        coverage[f"{c}_coverage"] = bil.groupby("station_id")[c].apply(lambda x: float(x.notna().mean())).values
    coverage.to_csv(outdir / "era5_a2_station_coverage.csv", index=False)

    # Hard scientific QC gates. Values are warnings/errors, not outlier deletion rules.
    if (bil["tp_mm_1h"].dropna() < -1e-8).any():
        raise ValueError("Negative ERA5 hourly precipitation found after interpolation; inspect source/encoding")
    rh = bil["rh_pct"].dropna()
    if ((rh < -1.0) | (rh > 101.0)).any():
        raise ValueError("Derived RH falls outside a plausible numerical tolerance; inspect T/Td interpolation")
    if coverage[[f"{c}_coverage" for c in core]].min().min() < 0.99:
        print("WARNING: at least one core ERA5 feature has <99% station-hour coverage; inspect audit before A2 modelling")

    print(outdir / "era5_a2_station_hourly_bilinear.csv")
    print(audit.to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stations", required=True, type=Path, help="kgmt_station_geometry_features.csv")
    ap.add_argument("--workdir", type=Path, default=Path("era5_a2_work"))
    ap.add_argument("--write-manifest", action="store_true")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--process", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    stations = pd.read_csv(args.stations)
    required = {"station_id", "station_name", "lat", "lon"}
    missing = required - set(stations.columns)
    if missing:
        raise ValueError(f"KGMT station table missing required columns: {sorted(missing)}")
    if len(stations) != 11 or not stations.station_id.is_unique:
        raise ValueError("KGMT canonical table must contain exactly 11 unique stations")
    if stations[["lat", "lon"]].isna().any().any():
        raise ValueError("Missing KGMT coordinates")
    if not ((stations.lat >= AREA[2]) & (stations.lat <= AREA[0]) &
            (stations.lon >= AREA[1]) & (stations.lon <= AREA[3])).all():
        raise ValueError("At least one KGMT station falls outside the fixed ERA5 request area")

    args.workdir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(stations)
    manifest_path = args.workdir / "era5_a2_request_manifest.json"
    if args.write_manifest or (not args.download and not args.process):
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(manifest_path)

    ncdir = args.workdir / "netcdf"
    if args.download:
        download_months(ncdir, overwrite=args.overwrite)
    if args.process:
        process_netcdf(stations, ncdir, args.workdir / "outputs")


if __name__ == "__main__":
    main()
