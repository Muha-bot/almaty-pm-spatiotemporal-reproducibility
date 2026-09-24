# Results provenance

## Core archived A0/A1 artifacts

Expected SHA-256:

- `metrics.csv`: `1b1baf90bfe5adcfaada33a9a5f072c557179824f832cfe62a24303b4341de56`
- `selected_hyperparameters.csv`: `b856f09dad3efc4ad482ba4039f2ed5c68d0109ab6df609432345d3e7f3e5796`
- `kgmt_station_geometry_features.csv`: `61a058513811892c042c0d613f18714cd0d1d8df1a0e757d3067b1fe44cdd5c6`
- `airgradient_station_geometry_features.csv`: `51fc655db83188b4f17118fb67ff891f75fd9b34e9a6d44cc75f74b52e0b37ea`

Chronological split represented in archived metrics:

- training: 2021–2023;
- validation/model selection: 2024;
- independent test: 2025.

Forecast horizons: +1 h and +24 h for PM2.5 and PM10.

## Locked KGMT long input

- file: `data/derived/baseline/almaty_hourly_long.csv.gz`
- SHA-256: `1188fc9d87ac3f0a3a947c81ec5083646f4703620e0e3db7ed48c3d90f57b8f8`
- rows: 613,722
- PM2.5: 355,450 rows
- PM10: 258,272 rows
- stations: 11
- exact synchronized PM2.5/PM10 station-hours: 237,783
- exact upstream Git commit: **not verified from the supplied artifact**

The byte-identical builder script is stored at `src/data/build_almaty_hourly_long.py`. It records the resolved upstream commit when run, but the builder QC JSON corresponding to this already-built snapshot was not supplied.

## Preserved spatial archive hashes

- `airgradient_hourly_openaq.csv.gz`: `d71bd86f6500ed41f4e2ad8630adb046a29e94761dbcade8b684c1dc28d69111`
- `gwr_FINAL_8080_results.csv`: `8b329df41ec7ed7a3f91503159b073efe2f69fde3f757b420e6d211ca3c71111`
- `gwr_target_8080.csv`: `291aeabca506641fbf86d586a31a573cae83bd160e6a61010c93184f0666ed66`
- `gwr_dataset_8080_133.csv`: `f69d33bcccfffc46573a746f71c6fe48c4b3b8f99a681c5a8b8faed709bf09c8`

Archived GWR figures:

- `fig_gwr_FINAL_8080_coefficients.png`: `fda14c748be48858bee0971524232f69ab91fd2afbabee1b5fd455a754f3b0f2`
- `fig_gwr_FINAL_8080_fit.png`: `75a6635adbc34377f20bdbaa7cc71f77d54a396a849938e1351fca203a9f6cb1`

The re-uploaded `files (21)(1).zip` was checked against the earlier `files (21).zip` and had the same SHA-256: `776bdfcfcb52027069578775d3a3f57ade58a613eb97141328e5f107095f67b4`. It is therefore not committed as a redundant archive.

## Verification commands

```bash
make verify
```

or individually:

```bash
python src/forecasting/verify_archived_results.py \
  --data-dir data/derived/baseline \
  --out-dir results/verified

python src/data/verify_almaty_hourly_long.py \
  --data data/derived/baseline/almaty_hourly_long.csv.gz

python src/spatial/verify_spatial_archive.py \
  --data-dir data/derived/spatial
```

## Figures 6 and 7 inputs

| File | SHA-256 |
|---|---|
| `data/derived/spatial/kgmt_airgradient_pm25_hourly.csv.gz` | `1f07bef59003df94cdca26f6f212a6bad25db40728555d881599b7a743a4e82a` |
| `data/derived/spatial/airgradient_spatial_blocks_107.csv` | `6c236ff45b61b316978930b247430f60b01222c5fd22cf4e07a778a0b4aaee73` |

Verify with `make verify-new-figures`. See `docs/FIGURE_MAPPING.md` for
what these inputs were built from and, for Figure 7, an important
discrepancy with the manuscript's XGBoost claim.

## Figure 7 archive, recovered from almaty_review_v4.zip (2026-09-22)

Recovered from `almaty_review_v4/data/advanced_validation/` in a
previously-supplied review package; not regenerable from source (see
`docs/KNOWN_LIMITATIONS.md` §7 and `docs/FIGURE_MAPPING.md`).

| File | SHA-256 |
|---|---|
| `data/archived/spatial_block_cv_107/airgradient_spatial_blocks_107.csv` | `334521e37e8826b137ca8cd8f61d2e89b763e38143dccd0c82bca858ef03c561` |
| `data/archived/spatial_block_cv_107/spatial_block_cv_summary.csv` | `23e899ede9b31c828361ec8f44843bef169432b57466e06c5781e2f0f45c809c` |
| `data/archived/spatial_block_cv_107/spatial_block_cv_by_block.csv` | `1984ca372536473633bc0ba53e5a88e5e14ba61b247bf1a959bfa93bdda59429` |
