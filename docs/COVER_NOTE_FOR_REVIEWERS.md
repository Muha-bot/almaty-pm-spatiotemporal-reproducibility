# Note to reviewers and editors

This repository accompanies the manuscript "Spatiotemporal Modelling of
PM2.5 and PM10 in Almaty: Leakage-Controlled Forecasting, GIS Predictors,
and Geographically Weighted Regression." A short summary of its current
state, so you don't need to read every file in `docs/` to get oriented:

- Most of the manuscript's quantitative results (the KGMT/AirGradient
  hourly data, the GWR spatial model, the cross-pollutant ablation, and the
  main validation table) can be independently recomputed from the data in
  this repository with a single command, `make verify`, and every number
  checks out against the archived record.
- Figures 4, 5, and 7 are included as preserved archival output (their
  original generating code was not part of what was recovered) rather than
  something this repository regenerates from scratch; this is disclosed
  explicitly, not left for you to discover.
- Figure 6 (same-sensor representativeness) has both its archived output
  *and* its generating script recovered (`data/archived/same_sensor_representativeness_v1/`),
  matching the manuscript's reported 6.05 / 1.82 / +5.96 µg/m³ to three
  decimal places. Two secondary parameters (random-draw count, and the
  geometry-constrained reference network) still do not fully match and are
  disclosed rather than silently reconciled — see `docs/FIGURE_MAPPING.md`.
- One open item remains: a from-scratch reconstruction of Figure 7's
  coordinate-only model comparison, using only station coordinates, did not
  reproduce the archived result. Two further attempts adding the extra
  columns available in the recovered cohort file (`median`, `cluster_id`)
  also did not reproduce it — one likely leaked target information, the
  other came closer but still missed. The most likely explanation is that
  the original model used a feature set that was not recovered alongside
  the archived output — this is flagged as an open question for the
  authors rather than resolved by guesswork.
- Full detail on all of the above is in `docs/REPRODUCIBILITY_STATUS.md`,
  `docs/KNOWN_LIMITATIONS.md`, and `docs/FIGURE_MAPPING.md`, and a
  step-by-step verification path is in `docs/REVIEWER_CHECKLIST.md`.

We would rather you see these notes here than find a gap yourselves without
context for it.
