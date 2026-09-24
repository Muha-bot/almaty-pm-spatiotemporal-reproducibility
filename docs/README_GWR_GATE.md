# Almaty PM2.5/PM10: GIS → OLS/VIF/Moran → GWR empirical gate

This package implements the locked spatial branch of the manuscript. It does **not** create or infer missing empirical values.

## Fixed scientific design

- Canonical station geometry: **141 AirGradient + 11 KGMT = 152 unique stations**.
- Projected CRS: **EPSG:32643 (WGS 84 / UTM zone 43N)**.
- GIS sources:
  - Copernicus DEM GLO-30, 2021 release, required coverage N43E076 and N43E077.
  - ESA WorldCover 2021 v200, tile N42E075.
  - OpenStreetMap / Geofabrik Kazakhstan snapshot dated 2026-09-03.
- GIS predictors: elevation, slope, nearest major road, motor-vehicle road density at 250/500/1000 m, built fraction at 250/500/1000 m, tree/grass at 500/1000 m, bare/water at 1000 m.
- Primary GWR target: locked **80/80 common-hour rule**.
  - An hour is retained when ≥113/141 AirGradient stations report valid PM2.5.
  - A station is eligible when it is observed in ≥80% of retained common hours.
  - Primary response is station mean PM2.5 over that common support.
- The earlier 107-site ≥90% cohort remains a completed Moran/diagnostic reference and is **not** automatically reused as the final GWR cohort.

## Primary GWR specification

The primary local model contains only three predeclared concepts:

1. `elevation_m`
2. `road_density_500m`
3. `built_frac_500m`

Sensitivity specifications separately evaluate slope, distance to major road, tree fraction and 250/1000 m buffer alternatives. Predictor selection is not allowed to use PM2.5 association strength or visual appeal of coefficient maps.

Before GWR, the runner requires:

- zero missing values in the primary GWR predictors/target;
- no duplicate station IDs or geometries;
- pairwise |r| ≤ 0.80;
- VIF ≤ 5;
- global OLS;
- 9,999-permutation residual Moran's I using a symmetric 4-nearest-neighbour graph.

A violation stops the pipeline before local estimation.

## One-command run

```bash
bash run_almaty_gis_gwr_empirical_gate.sh \
  AIRGRADIENT_HOURLY_PM25.csv \
  airgradient_station_geometry_features.csv \
  kgmt_station_geometry_features.csv \
  ./empirical_gate_run \
  --download
```

If the fixed public DEM/WorldCover/OSM files were already downloaded into the expected work directory, omit `--download`.

## Expected outputs

The GIS step writes:

- `almaty_station_gis_predictors.csv`
- `gis_predictor_missingness.csv`
- `gis_predictor_ranges.csv`
- `gis_extraction_metadata.json` with source SHA-256 fingerprints

The target step writes:

- `airgradient_gwr_target_80_80.csv`

The pre-GWR step writes:

- `gwr_missingness.csv`
- `gwr_predictor_ranges.csv`
- `gwr_predictor_correlation.csv`
- `gwr_high_correlation_pairs.csv`
- `gwr_vif.csv`
- `global_ols_coefficients.csv`
- `global_ols_summary.txt`
- `pre_gwr_diagnostics.json`

The final GWR step, only after the gate passes, writes:

- `gwr_local_coefficients.csv`
- `gwr_model_diagnostics.json`

## Software QA already performed

The extraction functions were checked using a synthetic spatial fixture with a known DEM gradient, categorical WorldCover classes, and road classes including a footway. The test confirmed finite DEM/slope extraction, categorical fractions in [0,1], correct major-road distance, and exclusion of footways from the motor-vehicle road-density proxy.

The pre-GWR gate was separately tested with outcome-independent synthetic predictors. A non-collinear specification passed OLS/VIF/Moran diagnostics. An intentionally redundant specification halted before local fitting at the prespecified correlation threshold. These are software tests only and are **not empirical Almaty results**.
