# Data layout

## `derived/baseline/`

Small preserved audit artifacts for temporal forecasting, station geometry, and the locked normalized KGMT PM2.5/PM10 long table.

The committed KGMT snapshot is only 3.0 MB compressed and is retained because it is the exact user-supplied empirical input needed for later ERA5/A2 and GIS/A3 joins. Its SHA-256 and QC are stored alongside it.

## `derived/spatial/`

Dense-network AirGradient input and final 80/80 GWR branch artifacts.

## `raw/`

Not committed. Large or mutable public environmental source files are downloaded by scripts.

## Public-source policy

Store small publication snapshots and their hashes when redistribution is permitted and scientifically useful. Do not duplicate large ERA5/DEM/WorldCover/OSM binaries in Git history. Keep data licensing separate from the software licence; see `../docs/DATA_LICENSE.md`.
