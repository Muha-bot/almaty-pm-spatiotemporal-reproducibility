#!/usr/bin/env python3
"""Build station-level GIS predictors for the Almaty PM2.5/PM10 study.

Privacy design: station coordinates are never sent to an external API. Public regional
files are downloaded as whole tiles/extracts (optional) and all spatial joins are local.

Canonical inputs
----------------
- airgradient_station_geometry_features.csv (141 stations)
- kgmt_station_geometry_features.csv (11 stations)

Public spatial inputs (fixed versions)
--------------------------------------
- Copernicus DEM GLO-30, 2021 release: N43E076 and N43E077 tiles
- ESA WorldCover 2021 v200: N42E075 tile
- Geofabrik Kazakhstan OSM PBF dated 2026-09-03

Outputs
-------
- almaty_station_gis_predictors.csv
- gis_predictor_missingness.csv
- gis_extraction_metadata.json
"""
from __future__ import annotations

import argparse
import json
import math
import urllib.request
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import pyogrio
import rasterio
from rasterio.merge import merge
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.vrt import WarpedVRT
from shapely.geometry import Point, box, mapping

UTM = "EPSG:32643"   # Almaty, metric buffers
WGS84 = "EPSG:4326"

DEM_URLS = {
    "N43E076": "https://copernicus-dem-30m.s3.amazonaws.com/"
                "Copernicus_DSM_COG_10_N43_00_E076_00_DEM/"
                "Copernicus_DSM_COG_10_N43_00_E076_00_DEM.tif",
    "N43E077": "https://copernicus-dem-30m.s3.amazonaws.com/"
                "Copernicus_DSM_COG_10_N43_00_E077_00_DEM/"
                "Copernicus_DSM_COG_10_N43_00_E077_00_DEM.tif",
}
WORLDCOVER_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
    "ESA_WorldCover_10m_2021_v200_N42E075_Map.tif"
)
OSM_URL = "https://download.geofabrik.de/asia/kazakhstan-260903.osm.pbf"

MAJOR_HIGHWAYS = {
    "motorway", "motorway_link", "trunk", "trunk_link",
    "primary", "primary_link", "secondary", "secondary_link",
    "tertiary", "tertiary_link",
}
# Motor-vehicle network used for road-density exposure. Pedestrian/cycle/path/steps
# and rural tracks are deliberately excluded from the traffic proxy.
VEHICLE_HIGHWAYS = MAJOR_HIGHWAYS | {
    "unclassified", "residential", "living_street", "service",
}
WC_CLASSES = {"tree": 10, "grass": 30, "built": 50, "bare": 60, "water": 80}


def download(url: str, out: Path) -> None:
    if out.exists() and out.stat().st_size > 0:
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(out)


def load_stations(ag_csv: Path, kg_csv: Path) -> gpd.GeoDataFrame:
    ag = pd.read_csv(ag_csv)
    kg = pd.read_csv(kg_csv)
    if len(ag) != 141:
        raise ValueError(f"AirGradient canonical table must contain 141 rows, found {len(ag)}")
    if len(kg) != 11:
        raise ValueError(f"KGMT canonical table must contain 11 rows, found {len(kg)}")
    for name, df in [("AirGradient", ag), ("KGMT", kg)]:
        if df["station_id"].duplicated().any():
            raise ValueError(f"Duplicate station_id in canonical {name} table")
        if df[["lat", "lon"]].isna().any().any():
            raise ValueError(f"Missing coordinates in canonical {name} table")
    keep = ["station_id", "station_name", "source", "lat", "lon", "cluster_id",
            "cluster_name", "n_obs", "first_utc", "last_utc", "parameters"]
    all_df = pd.concat([ag[keep], kg[keep]], ignore_index=True)
    g = gpd.GeoDataFrame(
        all_df,
        geometry=gpd.points_from_xy(all_df.lon, all_df.lat),
        crs=WGS84,
    ).to_crs(UTM)
    g["x_utm_m"] = g.geometry.x
    g["y_utm_m"] = g.geometry.y
    return g


def mosaic_and_reproject(src_paths: list[Path], dst: Path, resolution: float = 30.0) -> Path:
    if dst.exists() and dst.stat().st_size > 0:
        return dst
    srcs = [rasterio.open(p) for p in src_paths]
    arr, trans = merge(srcs)
    profile = srcs[0].profile.copy()
    profile.update(height=arr.shape[1], width=arr.shape[2], transform=trans, count=1)
    tmp = dst.with_name(dst.stem + "_wgs84.tif")
    with rasterio.open(tmp, "w", **profile) as d:
        d.write(arr[0], 1)
    for s in srcs:
        s.close()
    with rasterio.open(tmp) as src:
        transform, width, height = calculate_default_transform(
            src.crs, UTM, src.width, src.height, *src.bounds, resolution=resolution
        )
        prof = src.profile.copy()
        prof.update(crs=UTM, transform=transform, width=width, height=height)
        with rasterio.open(dst, "w", **prof) as d:
            reproject(
                source=rasterio.band(src, 1), destination=rasterio.band(d, 1),
                src_transform=src.transform, src_crs=src.crs,
                dst_transform=transform, dst_crs=UTM,
                resampling=Resampling.bilinear,
            )
    tmp.unlink(missing_ok=True)
    return dst


def reproject_worldcover(src_path: Path, dst: Path, stations: gpd.GeoDataFrame,
                         resolution: float = 10.0, margin_m: float = 1500.0) -> Path:
    """Create only a study-window UTM subset from the categorical WorldCover tile.

    Nearest-neighbour resampling preserves the categorical class codes.
    """
    if dst.exists() and dst.stat().st_size > 0:
        return dst
    xmin, ymin, xmax, ymax = stations.total_bounds
    bounds = (xmin-margin_m, ymin-margin_m, xmax+margin_m, ymax+margin_m)
    with rasterio.open(src_path) as src, WarpedVRT(
        src, crs=UTM, resolution=resolution, resampling=Resampling.nearest, nodata=0
    ) as vrt:
        win = rasterio.windows.from_bounds(*bounds, transform=vrt.transform)
        win = win.round_offsets().round_lengths()
        arr = vrt.read(1, window=win, boundless=True, fill_value=0)
        if arr.size == 0:
            raise ValueError("WorldCover study-window subset is empty")
        trans = vrt.window_transform(win)
        prof = {
            "driver": "GTiff", "height": arr.shape[0], "width": arr.shape[1],
            "count": 1, "dtype": arr.dtype, "crs": UTM, "transform": trans,
            "nodata": 0, "compress": "deflate", "tiled": True,
        }
        with rasterio.open(dst, "w", **prof) as d:
            d.write(arr, 1)
    return dst


def sample_dem_and_slope(stations: gpd.GeoDataFrame, dem_utm: Path) -> pd.DataFrame:
    out = pd.DataFrame(index=stations.index)
    with rasterio.open(dem_utm) as src:
        coords = [(p.x, p.y) for p in stations.geometry]
        elev = np.array([v[0] for v in src.sample(coords)], dtype=float)
        nodata = src.nodata
        if nodata is not None:
            elev[elev == nodata] = np.nan
        out["elevation_m"] = elev

        slopes = []
        px = abs(src.transform.a)
        py = abs(src.transform.e)
        for p in stations.geometry:
            # local 5x5 window; Horn-like gradient approximation via np.gradient
            row, col = src.index(p.x, p.y)
            win = rasterio.windows.Window(col - 2, row - 2, 5, 5)
            a = src.read(1, window=win, boundless=True, fill_value=np.nan).astype(float)
            if nodata is not None:
                a[a == nodata] = np.nan
            if np.isfinite(a).sum() < 9:
                slopes.append(np.nan)
                continue
            gy, gx = np.gradient(a, py, px)
            slope = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2)))
            slopes.append(float(np.nanmedian(slope)))
        out["slope_deg"] = slopes
    return out


def read_osm_roads(osm_pbf: Path, stations_utm: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    # Read only the Almaty study envelope (+2 km), first in WGS84 for OGR bbox filter.
    study = stations_utm.unary_union.convex_hull.buffer(2000)
    study_wgs = gpd.GeoSeries([study], crs=UTM).to_crs(WGS84).iloc[0]
    lines = pyogrio.read_dataframe(
        osm_pbf, layer="lines", bbox=study_wgs.bounds,
        columns=["highway", "name"],
    )
    if "highway" not in lines.columns:
        raise ValueError("OSM lines layer has no 'highway' field")
    roads = lines[lines["highway"].notna()].copy()
    roads = roads[~roads.geometry.is_empty & roads.geometry.notna()]
    roads = roads.to_crs(UTM)
    roads = roads[roads.intersects(study)]
    roads["highway"] = roads["highway"].astype(str)
    return roads


def road_features(stations: gpd.GeoDataFrame, roads: gpd.GeoDataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=stations.index)
    major = roads[roads["highway"].isin(MAJOR_HIGHWAYS)].copy().reset_index(drop=True)
    vehicle = roads[roads["highway"].isin(VEHICLE_HIGHWAYS)].copy().reset_index(drop=True)
    if major.empty:
        raise ValueError("No major OSM roads in study footprint")
    if vehicle.empty:
        raise ValueError("No motor-vehicle OSM roads in study footprint")
    major_sindex = major.sindex
    vehicle_sindex = vehicle.sindex

    dist = []
    for p in stations.geometry:
        nearest_idx = list(major_sindex.nearest(p, return_all=False))[1][0]
        dist.append(float(p.distance(major.geometry.iloc[nearest_idx])))
    out["dist_major_road_m"] = dist

    for r in (250, 500, 1000):
        vals = []
        area_km2 = math.pi * (r / 1000.0) ** 2
        for p in stations.geometry:
            b = p.buffer(r)
            cand_idx = list(vehicle_sindex.query(b, predicate="intersects"))
            if not cand_idx:
                vals.append(0.0)
                continue
            inter = vehicle.geometry.iloc[cand_idx].intersection(b)
            length_km = float(inter.length.sum() / 1000.0)
            vals.append(length_km / area_km2)
        out[f"road_density_{r}m"] = vals
    return out


def class_fraction(src, geom, class_code: int) -> float:
    arr, _ = mask(src, [mapping(geom)], crop=True, all_touched=False, filled=False)
    band = arr[0]
    valid = ~band.mask
    if valid.sum() == 0:
        return np.nan
    vals = band.data[valid]
    vals = vals[vals != 0]
    if len(vals) == 0:
        return np.nan
    return float(np.mean(vals == class_code))


def worldcover_features(stations: gpd.GeoDataFrame, wc_utm: Path) -> pd.DataFrame:
    out = pd.DataFrame(index=stations.index)
    with rasterio.open(wc_utm) as src:
        for r in (250, 500, 1000):
            out[f"built_frac_{r}m"] = [class_fraction(src, p.buffer(r), WC_CLASSES["built"])
                                          for p in stations.geometry]
        for cls in ("tree", "grass"):
            for r in (500, 1000):
                out[f"{cls}_frac_{r}m"] = [class_fraction(src, p.buffer(r), WC_CLASSES[cls])
                                             for p in stations.geometry]
        for cls in ("bare", "water"):
            out[f"{cls}_frac_1000m"] = [class_fraction(src, p.buffer(1000), WC_CLASSES[cls])
                                          for p in stations.geometry]
    return out


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def audit_feature_ranges(feat: pd.DataFrame) -> pd.DataFrame:
    fraction_cols = [c for c in feat.columns if "_frac_" in c]
    for c in fraction_cols:
        x = pd.to_numeric(feat[c], errors="coerce").dropna()
        if ((x < 0) | (x > 1)).any():
            raise ValueError(f"{c} contains values outside [0,1]")
    if (pd.to_numeric(feat["slope_deg"], errors="coerce").dropna() > 90).any():
        raise ValueError("slope_deg contains values above 90 degrees")
    for c in ["dist_major_road_m", "road_density_250m", "road_density_500m", "road_density_1000m"]:
        if (pd.to_numeric(feat[c], errors="coerce").dropna() < 0).any():
            raise ValueError(f"{c} contains negative values")
    return pd.DataFrame({
        "feature": feat.columns,
        "min": [pd.to_numeric(feat[c], errors="coerce").min() for c in feat.columns],
        "median": [pd.to_numeric(feat[c], errors="coerce").median() for c in feat.columns],
        "max": [pd.to_numeric(feat[c], errors="coerce").max() for c in feat.columns],
        "std": [pd.to_numeric(feat[c], errors="coerce").std(ddof=1) for c in feat.columns],
    })


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--airgradient", required=True, type=Path)
    ap.add_argument("--kgmt", required=True, type=Path)
    ap.add_argument("--workdir", type=Path, default=Path("gis_work"))
    ap.add_argument("--download", action="store_true",
                    help="Download fixed public regional inputs; no station coords are transmitted")
    args = ap.parse_args()
    w = args.workdir
    raw = w / "public_raw"
    outdir = w / "outputs"
    raw.mkdir(parents=True, exist_ok=True)
    outdir.mkdir(parents=True, exist_ok=True)

    dem_files = [raw / f"copdem_{k}.tif" for k in DEM_URLS]
    wc_file = raw / "ESA_WorldCover_10m_2021_v200_N42E075_Map.tif"
    osm_file = raw / "kazakhstan-260903.osm.pbf"
    if args.download:
        for (_, url), p in zip(DEM_URLS.items(), dem_files):
            download(url, p)
        download(WORLDCOVER_URL, wc_file)
        download(OSM_URL, osm_file)

    missing = [str(p) for p in dem_files + [wc_file, osm_file] if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing public GIS inputs. Use --download or place files locally:\n" + "\n".join(missing))

    stations = load_stations(args.airgradient, args.kgmt)
    dem_utm = mosaic_and_reproject(dem_files, w / "copdem_almaty_utm43.tif", 30.0)
    wc_utm = reproject_worldcover(wc_file, w / "worldcover_almaty_utm43.tif", stations, 10.0)
    roads = read_osm_roads(osm_file, stations)

    feat = pd.concat([
        sample_dem_and_slope(stations, dem_utm),
        road_features(stations, roads),
        worldcover_features(stations, wc_utm),
    ], axis=1)

    base = stations.drop(columns="geometry").reset_index(drop=True)
    final = pd.concat([base, feat.reset_index(drop=True)], axis=1)
    if len(final) != 152 or final["station_id"].duplicated().any():
        raise AssertionError("Station-table integrity check failed")

    final_path = outdir / "almaty_station_gis_predictors.csv"
    final.to_csv(final_path, index=False)
    miss = pd.DataFrame({
        "feature": feat.columns,
        "n_missing": [int(feat[c].isna().sum()) for c in feat.columns],
        "missing_fraction": [float(feat[c].isna().mean()) for c in feat.columns],
    })
    miss.to_csv(outdir / "gis_predictor_missingness.csv", index=False)
    ranges = audit_feature_ranges(feat)
    ranges.to_csv(outdir / "gis_predictor_ranges.csv", index=False)
    final["gis_complete"] = ~feat.isna().any(axis=1)
    final.to_csv(final_path, index=False)

    source_files = dem_files + [wc_file, osm_file]
    fingerprints = {p.name: {"bytes": int(p.stat().st_size), "sha256": sha256_file(p)} for p in source_files}

    meta = {
        "station_counts": {"airgradient": 141, "kgmt": 11, "total": 152},
        "analysis_crs": UTM,
        "sources": {
            "elevation": {"product": "Copernicus DEM GLO-30", "release": "2021", "tiles": list(DEM_URLS), "urls": DEM_URLS},
            "land_cover": {"product": "ESA WorldCover", "year": 2021, "version": "v200", "tile": "N42E075", "url": WORLDCOVER_URL},
            "roads": {"product": "OpenStreetMap Geofabrik Kazakhstan extract", "snapshot": "2026-09-03", "url": OSM_URL,
                      "major_highway_tags": sorted(MAJOR_HIGHWAYS),
                      "road_density_highway_tags": sorted(VEHICLE_HIGHWAYS)},
        },
        "features": {
            "elevation_m": "DEM point sample; metres",
            "slope_deg": "median local 5x5 DEM gradient; degrees",
            "dist_major_road_m": "Euclidean distance in EPSG:32643 to OSM major-road classes; metres",
            "road_density_250m/500m/1000m": "motor-vehicle OSM road length intersecting buffer / buffer area; km per km2",
            "built_frac_250m/500m/1000m": "WorldCover class 50 pixel fraction",
            "tree_frac_500m/1000m": "WorldCover class 10 pixel fraction",
            "grass_frac_500m/1000m": "WorldCover class 30 pixel fraction",
            "bare_frac_1000m": "WorldCover class 60 pixel fraction",
            "water_frac_1000m": "WorldCover class 80 pixel fraction",
        },
        "source_fingerprints": fingerprints,
        "privacy": "No station coordinates are sent to external APIs; only whole public regional files are downloaded.",
        "missingness_rule": "No imputation of static GIS predictors for primary GWR; missing values are reported and gate local modelling.",
        "gwr_gate": "Do not fit GWR until missingness, scale, pairwise correlation, VIF and global OLS diagnostics are checked.",
    }
    (outdir / "gis_extraction_metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(final_path)
    print(miss.to_string(index=False))
    print("\nRanges:")
    print(ranges.to_string(index=False))
    print(f"\nComplete GIS rows: {int(final['gis_complete'].sum())}/{len(final)}")


if __name__ == "__main__":
    main()
