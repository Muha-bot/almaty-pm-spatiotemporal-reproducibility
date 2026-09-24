#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build almaty_hourly_long.csv.gz from AirData.kz public Almaty PM2.5/PM10 files.

Output columns:
    parameter, ts_utc, station_id, source, value_ugm3

Only rows with source == "kgmt" are retained.

The script resolves the current GitHub `main` commit SHA first, then downloads
the two files from that immutable commit for reproducibility.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import sys
import urllib.request
from pathlib import Path

import pandas as pd

OWNER = "qazybekb"
REPO = "AirDatakz-OpenData"
API_COMMIT = f"https://api.github.com/repos/{OWNER}/{REPO}/commits/main"

FILES = {
    "pm25": "almaty/pm25.csv.gz",
    "pm10": "almaty/pm10.csv.gz",
}

REQUIRED_SOURCE_COLUMNS = {
    "datetime_utc",
    "station_id",
    "source",
    "value_ugm3",
}

OUT_COLUMNS = [
    "parameter",
    "ts_utc",
    "station_id",
    "source",
    "value_ugm3",
]


def http_get(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Almaty-PM-Scopus-reproducibility-builder/1.0",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolve_main_sha() -> str:
    payload = json.loads(http_get(API_COMMIT).decode("utf-8"))
    sha = payload.get("sha")
    if not sha or len(sha) < 12:
        raise RuntimeError("Could not resolve GitHub main commit SHA.")
    return sha


def load_parameter(parameter: str, relpath: str, ref: str):
    url = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{ref}/{relpath}"
    raw = http_get(url)

    # Keep a fingerprint of the exact downloaded binary.
    binary_sha256 = sha256_bytes(raw)

    # pandas can read gzip-compressed bytes from BytesIO.
    df = pd.read_csv(io.BytesIO(raw), compression="gzip")

    missing = REQUIRED_SOURCE_COLUMNS - set(df.columns)
    if missing:
        raise RuntimeError(
            f"{parameter}: source file missing required columns: {sorted(missing)}"
        )

    d = df.loc[
        df["source"].astype(str).str.lower().eq("kgmt"),
        ["datetime_utc", "station_id", "source", "value_ugm3"],
    ].copy()

    d["parameter"] = parameter
    d["ts_utc"] = pd.to_datetime(d["datetime_utc"], utc=True, errors="coerce")
    d["station_id"] = d["station_id"].astype(str)
    d["source"] = d["source"].astype(str).str.lower()
    d["value_ugm3"] = pd.to_numeric(d["value_ugm3"], errors="coerce")

    invalid_ts = int(d["ts_utc"].isna().sum())
    invalid_value = int(d["value_ugm3"].isna().sum())
    negative = int((d["value_ugm3"] < 0).sum())

    if invalid_ts or invalid_value:
        raise RuntimeError(
            f"{parameter}: invalid rows after normalization: "
            f"bad_ts={invalid_ts}, bad_value={invalid_value}"
        )
    if negative:
        raise RuntimeError(f"{parameter}: found {negative} negative KGMT values.")

    d["ts_utc"] = d["ts_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    d = d[OUT_COLUMNS]

    dup = d.duplicated(["parameter", "station_id", "ts_utc"], keep=False)
    n_dup = int(dup.sum())
    if n_dup:
        ex = d.loc[dup].head(10).to_dict(orient="records")
        raise RuntimeError(
            f"{parameter}: duplicate parameter+station_id+ts_utc rows found "
            f"(n={n_dup}); examples={ex}"
        )

    qc = {
        "parameter": parameter,
        "source_url": url,
        "source_binary_sha256": binary_sha256,
        "n_kgmt_rows": int(len(d)),
        "n_stations": int(d["station_id"].nunique()),
        "first_ts_utc": d["ts_utc"].min() if len(d) else None,
        "last_ts_utc": d["ts_utc"].max() if len(d) else None,
        "min_value_ugm3": float(d["value_ugm3"].min()) if len(d) else None,
        "max_value_ugm3": float(d["value_ugm3"].max()) if len(d) else None,
        "duplicate_keys": n_dup,
        "missing_values": int(d.isna().sum().sum()),
    }
    return d, qc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        default="almaty_hourly_long.csv.gz",
        help="Output gzip CSV filename",
    )
    ap.add_argument(
        "--qc",
        default="almaty_hourly_long_qc.json",
        help="QC/provenance JSON filename",
    )
    args = ap.parse_args()

    ref = resolve_main_sha()
    frames = []
    qcs = []

    for parameter, relpath in FILES.items():
        d, qc = load_parameter(parameter, relpath, ref)
        frames.append(d)
        qcs.append(qc)

    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values(
        ["ts_utc", "station_id", "parameter"],
        kind="mergesort",
    ).reset_index(drop=True)

    # Final invariant: only KGMT and exact requested columns.
    if list(out.columns) != OUT_COLUMNS:
        raise RuntimeError(f"Unexpected output schema: {list(out.columns)}")
    if set(out["source"].unique()) != {"kgmt"}:
        raise RuntimeError(f"Unexpected source values: {sorted(out['source'].unique())}")

    final_dup = out.duplicated(
        ["parameter", "station_id", "ts_utc"], keep=False
    ).sum()
    if final_dup:
        raise RuntimeError(f"Final output contains {int(final_dup)} duplicate keys.")

    out_path = Path(args.out)
    out.to_csv(
        out_path,
        index=False,
        compression={"method": "gzip", "compresslevel": 9, "mtime": 0},
    )

    qc_doc = {
        "repository": f"https://github.com/{OWNER}/{REPO}",
        "resolved_main_commit_sha": ref,
        "output_file": str(out_path),
        "output_columns": OUT_COLUMNS,
        "n_rows_total": int(len(out)),
        "n_stations_total": int(out["station_id"].nunique()),
        "parameters": sorted(out["parameter"].unique().tolist()),
        "sources": sorted(out["source"].unique().tolist()),
        "first_ts_utc": out["ts_utc"].min() if len(out) else None,
        "last_ts_utc": out["ts_utc"].max() if len(out) else None,
        "output_sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
        "source_files": qcs,
    }
    Path(args.qc).write_text(
        json.dumps(qc_doc, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps(qc_doc, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
