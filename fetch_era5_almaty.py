#!/usr/bin/env python3
"""
Retrieve the locked ERA5 A2 meteorological block for the Almaty PM2.5/PM10 study.

Scientific lock
---------------
Dataset: reanalysis-era5-single-levels
DOI: 10.24381/cds.adbb2d47
Native atmospheric grid: 0.25 degree lat/lon
Area (N,W,S,E): 43.50, 76.50, 43.00, 77.25
Primary source variables:
  - 2m_temperature
  - 2m_dewpoint_temperature
  - surface_pressure
  - 10m_u_component_of_wind
  - 10m_v_component_of_wind
  - total_precipitation
Sensitivity only:
  - boundary_layer_height

The script retrieves monthly NetCDF files so interrupted downloads can resume and
request sizes remain modest. 2020 is retained as context/warm-up; the locked
forecast split remains train 2021-2023, validation 2024, test 2025.

No modelling is performed here. Successful files are fingerprinted with SHA-256.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
from pathlib import Path

DATASET = "reanalysis-era5-single-levels"
AREA_NWSE = [43.50, 76.50, 43.00, 77.25]
INSTANT_VARS = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "surface_pressure",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
]
PRECIP_VARS = ["total_precipitation"]
BLH_VARS = ["boundary_layer_height"]
TIMES = [f"{h:02d}:00" for h in range(24)]


def sha256_file(path: Path, chunk_mb: int = 8) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_mb * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def month_request(year: int, month: int, variables: list[str]) -> dict:
    ndays = calendar.monthrange(year, month)[1]
    return {
        "product_type": ["reanalysis"],
        "variable": variables,
        "year": [str(year)],
        "month": [f"{month:02d}"],
        "day": [f"{d:02d}" for d in range(1, ndays + 1)],
        "time": TIMES,
        "area": AREA_NWSE,
        "data_format": "netcdf",
        "download_format": "unarchived",
    }


def retrieve(client, outdir: Path, year: int, month: int, tag: str, variables: list[str]) -> Path:
    target = outdir / f"era5_{tag}_{year}_{month:02d}.nc"
    if target.exists() and target.stat().st_size > 0:
        return target
    req = month_request(year, month, variables)
    tmp = target.with_suffix(".nc.part")
    if tmp.exists():
        tmp.unlink()
    result = client.retrieve(DATASET, req)
    result.download(str(tmp))
    if not tmp.exists() or tmp.stat().st_size == 0:
        raise IOError(f"ERA5 retrieval produced no bytes: {target.name}")
    tmp.replace(target)
    return target


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", type=Path, default=Path("era5_raw"))
    ap.add_argument("--start-year", type=int, default=2020)
    ap.add_argument("--end-year", type=int, default=2025)
    ap.add_argument("--include-blh", action="store_true",
                    help="Retrieve boundary-layer height as a sensitivity block")
    args = ap.parse_args()

    if args.start_year > args.end_year:
        raise ValueError("start-year must be <= end-year")

    try:
        import cdsapi
    except ImportError as exc:
        raise SystemExit(
            "cdsapi is required. In a network-enabled environment install it with: pip install cdsapi\n"
            "Configure the CDS API token according to https://cds.climate.copernicus.eu/en/how-to-api"
        ) from exc

    args.outdir.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client()
    records = []

    groups = [("inst", INSTANT_VARS), ("tp", PRECIP_VARS)]
    if args.include_blh:
        groups.append(("blh", BLH_VARS))

    for year in range(args.start_year, args.end_year + 1):
        for month in range(1, 13):
            for tag, variables in groups:
                p = retrieve(client, args.outdir, year, month, tag, variables)
                records.append({
                    "dataset": DATASET,
                    "year": year,
                    "month": month,
                    "group": tag,
                    "variables": variables,
                    "area_nwse": AREA_NWSE,
                    "path": str(p),
                    "bytes": p.stat().st_size,
                    "sha256": sha256_file(p),
                })
                print(f"OK {p.name} {p.stat().st_size} bytes")

    meta = {
        "dataset": DATASET,
        "doi": "10.24381/cds.adbb2d47",
        "area_nwse": AREA_NWSE,
        "native_atmospheric_grid_deg": 0.25,
        "start_year": args.start_year,
        "end_year": args.end_year,
        "primary_source_variables": INSTANT_VARS + PRECIP_VARS,
        "sensitivity_variables": BLH_VARS if args.include_blh else [],
        "forecast_split": {"train": "2021-2023", "validation": "2024", "test": "2025"},
        "leakage_rule": "Only ERA5 validity time t or earlier may be used at forecast origin t; never target-hour t+h reanalysis.",
        "files": records,
    }
    (args.outdir / "era5_source_fingerprints.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(args.outdir / "era5_source_fingerprints.json")


if __name__ == "__main__":
    main()
