#!/usr/bin/env bash
set -euo pipefail

# Reproducible empirical gate for the Almaty PM2.5/PM10 manuscript.
# Usage:
#   bash run_almaty_gis_gwr_empirical_gate.sh \
#     /path/to/airgradient_hourly_pm25.csv \
#     /path/to/airgradient_station_geometry_features.csv \
#     /path/to/kgmt_station_geometry_features.csv \
#     /path/to/workdir \
#     [--download]
#
# The optional --download retrieves only fixed public regional files.
# Station coordinates are not sent to per-point APIs.

if [[ $# -lt 4 || $# -gt 5 ]]; then
  echo "Usage: $0 AIRGRADIENT_HOURLY_PM25 AIRGRADIENT_GEOMETRY KGMT_GEOMETRY WORKDIR [--download]" >&2
  exit 64
fi

HOURLY="$1"
AG_GEOM="$2"
KG_GEOM="$3"
WORKDIR="$4"
DOWNLOAD_FLAG="${5:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIS_BUILDER="$SCRIPT_DIR/build_almaty_gis_predictors_v2.py"
TARGET_BUILDER="$SCRIPT_DIR/prepare_airgradient_gwr_target.py"
GWR_RUNNER="$SCRIPT_DIR/qc_and_run_airgradient_gwr_v2.py"

for f in "$GIS_BUILDER" "$TARGET_BUILDER" "$GWR_RUNNER" "$HOURLY" "$AG_GEOM" "$KG_GEOM"; do
  [[ -f "$f" ]] || { echo "ERROR: missing file: $f" >&2; exit 66; }
done

mkdir -p "$WORKDIR"

# Step 1. Static GIS predictors for 141 AirGradient + 11 KGMT.
GIS_ARGS=(--airgradient "$AG_GEOM" --kgmt "$KG_GEOM" --workdir "$WORKDIR/gis")
if [[ "$DOWNLOAD_FLAG" == "--download" ]]; then
  GIS_ARGS+=(--download)
elif [[ -n "$DOWNLOAD_FLAG" ]]; then
  echo "ERROR: fifth argument must be --download or omitted" >&2
  exit 64
fi

python "$GIS_BUILDER" "${GIS_ARGS[@]}"
GIS_TABLE="$WORKDIR/gis/outputs/almaty_station_gis_predictors.csv"
[[ -s "$GIS_TABLE" ]] || { echo "ERROR: GIS table was not created" >&2; exit 70; }

# Step 2. Locked 80/80 common-hour PM2.5 target.
TARGET_TABLE="$WORKDIR/airgradient_gwr_target_80_80.csv"
python "$TARGET_BUILDER" \
  --hourly "$HOURLY" \
  --canonical-stations "$AG_GEOM" \
  --out "$TARGET_TABLE" \
  --min-network-fraction 0.80 \
  --min-station-fraction 0.80
[[ -s "$TARGET_TABLE" ]] || { echo "ERROR: GWR target table was not created" >&2; exit 70; }

# Step 3. Mandatory global gate. This writes missingness, ranges, correlation,
# VIF, OLS and residual Moran's I. It stops on missingness/collinearity.
PRE="$WORKDIR/pre_gwr_primary"
python "$GWR_RUNNER" \
  --gis "$GIS_TABLE" \
  --target "$TARGET_TABLE" \
  --outdir "$PRE" \
  --spec primary \
  --corr-threshold 0.80 \
  --vif-threshold 5 \
  --moran-k 4 \
  --moran-permutations 9999 \
  --pre-gwr-only

# Step 4. Primary GWR. The runner intentionally refuses a hand-written
# substitute if the validated mgwr package is unavailable.
GWR="$WORKDIR/gwr_primary"
python "$GWR_RUNNER" \
  --gis "$GIS_TABLE" \
  --target "$TARGET_TABLE" \
  --outdir "$GWR" \
  --spec primary \
  --corr-threshold 0.80 \
  --vif-threshold 5 \
  --moran-k 4 \
  --moran-permutations 9999

echo "EMPIRICAL GATE COMPLETE"
echo "GIS table:      $GIS_TABLE"
echo "GWR target:     $TARGET_TABLE"
echo "Pre-GWR audit:  $PRE"
echo "GWR outputs:    $GWR"
