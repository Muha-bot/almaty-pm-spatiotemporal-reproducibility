# Raw data are intentionally not committed

This directory is intentionally empty in Git.

Large or continuously updated source products should be downloaded by the scripts in `src/`:

- AirData.kz Almaty PM2.5/PM10 hourly data: use `src/data/build_almaty_hourly_long.py`.
- ERA5 hourly single-level data: use `src/era5/fetch_era5_almaty.py` or `src/era5/prepare_era5_a2.py`.
- Copernicus DEM GLO-30, ESA WorldCover 2021 v200 and the dated Geofabrik Kazakhstan OSM extract: use `src/gis/build_almaty_gis_predictors_v2.py`.

Do not commit `.nc`, `.tif`, `.pbf`, model binaries, API keys or credentials.
