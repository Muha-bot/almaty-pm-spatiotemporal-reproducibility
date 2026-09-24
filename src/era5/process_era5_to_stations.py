#!/usr/bin/env python3
"""
Interpolate locked ERA5 monthly NetCDF files to canonical Almaty stations.

Primary A2 model representation (non-redundant):
  era5_t2m_c         2 m temperature, deg C
  era5_rh2m_pct      relative humidity derived from T2m and Td2m, %
  era5_sp_hpa        surface pressure, hPa
  era5_u10_ms        10 m U wind component, m/s
  era5_v10_ms        10 m V wind component, m/s
  era5_tp_mm_1h      total precipitation during the one hour ending at validity time, mm

Audit/sensitivity columns may also be exported:
  era5_d2m_c, era5_wind_speed_ms, era5_blh_m

Dew point is not entered together with RH in the primary feature set. Wind speed
and direction are not entered together with u/v in the primary feature set.
This avoids deterministic feature redundancy before any outcome is inspected.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

SHORT_TO_STD = {
    "t2m": "t2m_k",
    "d2m": "d2m_k",
    "sp": "sp_pa",
    "u10": "u10_ms",
    "v10": "v10_ms",
    "tp": "tp_m_1h",
    "blh": "blh_m",
}
LONG_TO_STD = {
    "2m_temperature": "t2m_k",
    "2m_dewpoint_temperature": "d2m_k",
    "surface_pressure": "sp_pa",
    "10m_u_component_of_wind": "u10_ms",
    "10m_v_component_of_wind": "v10_ms",
    "total_precipitation": "tp_m_1h",
    "boundary_layer_height": "blh_m",
}
PRIMARY = [
    "era5_t2m_c", "era5_rh2m_pct", "era5_sp_hpa",
    "era5_u10_ms", "era5_v10_ms", "era5_tp_mm_1h",
]


def open_dataset_any(path: Path):
    try:
        import xarray as xr
    except ImportError as exc:
        raise SystemExit("xarray is required") from exc

    errors = []
    for engine in [None, "netcdf4", "h5netcdf", "scipy"]:
        try:
            kw = {} if engine is None else {"engine": engine}
            return xr.open_dataset(path, **kw)
        except Exception as e:
            errors.append(f"{engine or 'auto'}: {type(e).__name__}: {e}")
    raise RuntimeError(
        f"Cannot open {path}. Install netCDF4 or h5netcdf in the execution environment.\n"
        + "\n".join(errors)
    )


def coord_name(ds, candidates: list[str]) -> str:
    for c in candidates:
        if c in ds.coords or c in ds.dims:
            return c
    raise KeyError(f"None of coordinate names {candidates} found; got {list(ds.coords)}")


def standardize_dataset(ds):
    lat = coord_name(ds, ["latitude", "lat"])
    lon = coord_name(ds, ["longitude", "lon"])
    tim = coord_name(ds, ["valid_time", "time"])
    ren = {}
    if lat != "latitude": ren[lat] = "latitude"
    if lon != "longitude": ren[lon] = "longitude"
    if tim != "time": ren[tim] = "time"
    if ren:
        ds = ds.rename(ren)

    # Collapse scalar/singleton dimensions (e.g. number, expver) conservatively.
    for dim in list(ds.dims):
        if dim not in {"time", "latitude", "longitude"} and ds.sizes.get(dim, 0) == 1:
            ds = ds.isel({dim: 0}, drop=True)

    if not np.all(np.diff(ds["latitude"].values.astype(float)) > 0):
        ds = ds.sortby("latitude")
    if not np.all(np.diff(ds["longitude"].values.astype(float)) > 0):
        ds = ds.sortby("longitude")
    return ds


def rh_from_t_td(t_c: np.ndarray, td_c: np.ndarray) -> np.ndarray:
    """Magnus approximation over water; adequate for near-surface meteorological RH."""
    a, b = 17.625, 243.04
    es_td = np.exp((a * td_c) / (b + td_c))
    es_t = np.exp((a * t_c) / (b + t_c))
    rh = 100.0 * es_td / es_t
    return np.clip(rh, 0.0, 100.0)


def interpolate_one(path: Path, stations: pd.DataFrame) -> pd.DataFrame:
    import xarray as xr

    with open_dataset_any(path) as raw:
        ds = standardize_dataset(raw)
        rename_vars = {}
        for v in ds.data_vars:
            if v in SHORT_TO_STD:
                rename_vars[v] = SHORT_TO_STD[v]
            elif v in LONG_TO_STD:
                rename_vars[v] = LONG_TO_STD[v]
        if not rename_vars:
            raise ValueError(f"No recognized ERA5 variables in {path.name}: {list(ds.data_vars)}")
        ds = ds.rename(rename_vars)
        wanted = list(rename_vars.values())
        ds = ds[wanted]

        station_coord = xr.DataArray(stations["station_id"].astype(str).values, dims="station", name="station")
        lat = xr.DataArray(stations["lat"].astype(float).values, dims="station", coords={"station": station_coord})
        lon = xr.DataArray(stations["lon"].astype(float).values, dims="station", coords={"station": station_coord})
        ip = ds.interp(latitude=lat, longitude=lon, method="linear")
        df = ip.to_dataframe().reset_index()
        keep = ["station", "time"] + wanted
        df = df[[c for c in keep if c in df.columns]].rename(columns={"station": "station_id"})
        df["timestamp_utc"] = pd.to_datetime(df.pop("time"), utc=True, errors="coerce")
        return df


def load_stations(path: Path, source: str | None) -> pd.DataFrame:
    s = pd.read_csv(path)
    need = {"station_id", "lat", "lon"}
    miss = need - set(s.columns)
    if miss:
        raise ValueError(f"Station file missing {sorted(miss)}")
    if source and "source" in s.columns:
        s = s[s["source"].astype(str).str.lower().eq(source.lower())].copy()
    s = s[[c for c in ["station_id", "station_name", "source", "lat", "lon"] if c in s.columns]].copy()
    if s.empty or s["station_id"].duplicated().any():
        raise ValueError("Station table must contain unique non-empty station_id rows")
    return s.reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--era5-dir", type=Path, required=True)
    ap.add_argument("--stations", type=Path, required=True)
    ap.add_argument("--source", default=None, help="Optional station source filter, e.g. kgmt")
    ap.add_argument("--outdir", type=Path, required=True)
    args = ap.parse_args()

    stations = load_stations(args.stations, args.source)
    args.outdir.mkdir(parents=True, exist_ok=True)

    files = sorted(args.era5_dir.glob("era5_*.nc"))
    if not files:
        raise FileNotFoundError(f"No era5_*.nc files found in {args.era5_dir}")

    pieces = [interpolate_one(p, stations) for p in files]
    long = pd.concat(pieces, ignore_index=True)

    # Merge variable groups from separate monthly files.
    value_cols = [c for c in ["t2m_k","d2m_k","sp_pa","u10_ms","v10_ms","tp_m_1h","blh_m"] if c in long.columns]
    agg = {c: "first" for c in value_cols}
    out = long.groupby(["station_id", "timestamp_utc"], as_index=False).agg(agg)

    required_raw = ["t2m_k","d2m_k","sp_pa","u10_ms","v10_ms","tp_m_1h"]
    missing_raw = [c for c in required_raw if c not in out.columns]
    if missing_raw:
        raise ValueError(f"Missing required ERA5 source variables after merge: {missing_raw}")

    out["era5_t2m_c"] = out["t2m_k"] - 273.15
    out["era5_d2m_c"] = out["d2m_k"] - 273.15
    out["era5_rh2m_pct"] = rh_from_t_td(out["era5_t2m_c"].to_numpy(), out["era5_d2m_c"].to_numpy())
    out["era5_sp_hpa"] = out["sp_pa"] / 100.0
    out["era5_u10_ms"] = out["u10_ms"]
    out["era5_v10_ms"] = out["v10_ms"]
    out["era5_wind_speed_ms"] = np.sqrt(out["u10_ms"]**2 + out["v10_ms"]**2)
    # ERA5 hourly reanalysis total precipitation is the 1-h accumulation ending at validity time.
    out["era5_tp_mm_1h"] = out["tp_m_1h"] * 1000.0
    if "blh_m" in out.columns:
        out["era5_blh_m"] = out["blh_m"]

    export_cols = ["station_id", "timestamp_utc"] + PRIMARY + ["era5_d2m_c", "era5_wind_speed_ms"]
    if "era5_blh_m" in out.columns:
        export_cols.append("era5_blh_m")
    final = out[export_cols].sort_values(["station_id", "timestamp_utc"]).reset_index(drop=True)

    dup = final.duplicated(["station_id", "timestamp_utc"], keep=False)
    if dup.any():
        raise ValueError("Duplicate station_id + timestamp_utc after ERA5 interpolation")

    # Physical-range audit: generous bounds detect unit/decoder mistakes, not climatological extremes.
    checks = {
        "era5_t2m_c": (-90, 70),
        "era5_rh2m_pct": (0, 100),
        "era5_sp_hpa": (500, 1100),
        "era5_u10_ms": (-100, 100),
        "era5_v10_ms": (-100, 100),
        "era5_tp_mm_1h": (0, 500),
        "era5_d2m_c": (-100, 70),
        "era5_wind_speed_ms": (0, 150),
    }
    if "era5_blh_m" in final.columns:
        checks["era5_blh_m"] = (0, 10000)

    qc_rows = []
    fatal = []
    for c in final.columns:
        if c in {"station_id", "timestamp_utc"}:
            continue
        x = pd.to_numeric(final[c], errors="coerce")
        lo, hi = checks.get(c, (None, None))
        bad = pd.Series(False, index=x.index)
        if lo is not None: bad |= x < lo
        if hi is not None: bad |= x > hi
        qc_rows.append({
            "feature": c,
            "n": int(x.notna().sum()),
            "n_missing": int(x.isna().sum()),
            "missing_fraction": float(x.isna().mean()),
            "min": float(x.min()) if x.notna().any() else None,
            "median": float(x.median()) if x.notna().any() else None,
            "max": float(x.max()) if x.notna().any() else None,
            "n_outside_generous_physical_bounds": int(bad.sum()),
        })
        if bad.any():
            fatal.append(f"{c}: {int(bad.sum())} values outside [{lo},{hi}]")

    qc = pd.DataFrame(qc_rows)
    if fatal:
        raise ValueError("ERA5 unit/range audit failed:\n" + "\n".join(fatal))

    # Primary model representation deliberately excludes deterministic duplicates.
    if set(["era5_d2m_c", "era5_wind_speed_ms"]) & set(PRIMARY):
        raise AssertionError("Primary feature list contains audit/sensitivity duplicates")

    final_path = args.outdir / "era5_station_hourly.csv.gz"
    final.to_csv(final_path, index=False, compression="gzip")
    qc.to_csv(args.outdir / "era5_station_hourly_qc.csv", index=False)

    meta = {
        "n_stations": int(final["station_id"].nunique()),
        "n_rows": int(len(final)),
        "first_utc": str(final["timestamp_utc"].min()),
        "last_utc": str(final["timestamp_utc"].max()),
        "primary_features": PRIMARY,
        "audit_sensitivity_features": [c for c in ["era5_d2m_c","era5_wind_speed_ms","era5_blh_m"] if c in final.columns],
        "interpolation": "bilinear on ERA5 native 0.25-degree atmospheric grid",
        "precipitation_semantics": "hourly accumulation ending at ERA5 validity time; m multiplied by 1000 to mm",
        "leakage_rule": "Join only to the same forecast-origin UTC timestamp t; never use ERA5 t+h reanalysis to predict y(t+h).",
    }
    (args.outdir / "era5_station_hourly_metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(final_path)
    print(qc.to_string(index=False))


if __name__ == "__main__":
    main()
