# Reproducibility status

This repository separates preserved empirical evidence from executable extensions. Unknown provenance is kept explicitly unknown rather than reconstructed from memory.

## Fully preserved and hash-verified

- `metrics.csv` — 40 A0/A1 metric rows.
- `selected_hyperparameters.csv` — 24 fitted-model selections based on 2024 validation MAE.
- `kgmt_station_geometry_features.csv` — 11 KGMT stations.
- `airgradient_station_geometry_features.csv` — 141 AirGradient stations.
- `validation_selected_primary_test_results_verified.csv`.
- `crossPM_ablation_test_deltas_verified.csv`.
- `almaty_hourly_long.csv.gz` — 613,722 KGMT-only PM2.5/PM10 rows, SHA-256 locked.

The KGMT snapshot passes strict schema, duplicate, missingness, range and synchronized-pair checks. Its exact upstream AirData.kz commit SHA is **not verified**, because the original builder QC JSON was not supplied with the CSV.

## Preserved spatial/GWR branch

- 130,816 normalized AirGradient PM2.5 hourly rows;
- 141 AirGradient stations and 956 distinct observed hours in the preserved spatial archive;
- 133-station 80/80 target and GIS model table;
- OLS-vs-GWR summary;
- two archived GWR output figures;
- executable GIS/GWR gate scripts.

`src/spatial/verify_spatial_archive.py` hash-checks the preserved spatial tables and validates their internal station/hour accounting.

## ERA5

The repository contains the locked ERA5 request manifest and processing/join scripts. Large raw ERA5 NetCDF files are intentionally not committed.

## Important remaining limitation

The original row-level A0/A1 training/prediction script that generated the archived baseline metrics is not present in the preserved evidence package. Adding the KGMT long table materially improves the reproducibility package, but it does **not** by itself prove exact end-to-end retraining of the historical A0/A1 metrics.

Therefore this repository can currently:

1. verify the exact KGMT input snapshot and its structure;
2. verify immutable archived A0/A1 outputs and their hashes;
3. reproduce the validation-selected and A1-A0 delta tables from those outputs;
4. verify the preserved dense-network/GWR archive;
5. provide the preserved ERA5, GIS and spatial-analysis code.

The exact end-to-end A0/A1 retraining is not yet independently verifiable from this package alone — that will hold once the original forecasting feature/training code is recovered, or once a clean replacement pipeline is run and the manuscript numbers are updated to match that rerun.

## Note on manuscript synchronization

At an earlier stage of this package's assembly, the working manuscript
text and this repository were not perfectly aligned in a few places (some
GIS/A2/A3/GWR stages described as pending, an older AirGradient count in
places). This has since been checked directly against the final submitted
manuscript: the submitted text consistently uses 141 AirGradient stations,
130,816 hourly observations, the 133-station 80/80 GWR cohort, and 613,722
KGMT rows throughout, with no "pending" language for GIS/GWR. No
forecasting results beyond A0 (history-only) and A1 (cross-pollutant) are
claimed anywhere in the submitted text — in particular, it does **not**
claim ERA5-enhanced (A2), GIS-enhanced (A3), or SHAP-based forecasting
results, even though this repository's code includes ERA5/GIS scaffolding
(`src/era5/`, `src/gis/`) for work beyond what is reported.

## See also

`docs/KNOWN_LIMITATIONS.md` itemizes specific, unresolved reproducibility
gaps referenced above (no recorded training random seed for A0/A1 model
selection, unverified raw GIS/DEM/OSM binaries behind the spatial
predictors) and explains, for each, exactly what is and is not verifiable
from this package.
