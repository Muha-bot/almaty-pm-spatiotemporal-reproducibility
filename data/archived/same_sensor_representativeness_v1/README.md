# Recovered archive for Figure 6 / Section 5.6 (same-sensor representativeness)

**Recovered 2026-09-22** from the earliest reproducibility package supplied
for this manuscript (`Almaty_PM25_advanced_validation.zip` /
`files__21_.zip`), which had not previously been copied into this
repository — the same way `data/archived/spatial_block_cv_107/` was
recovered from `almaty_review_v4.zip` for Figure 7.

## What matches the manuscript

`sparse_network_counterfactual_summary.csv`, row `mae_daily_mean`:

| Quantity | Manuscript (Section 5.6) | This archive |
|---|---|---|
| Matched 11-site MAE | 6.05 µg/m³ | 6.050388937741711 |
| Random-network median MAE | 1.82 µg/m³ | 1.8214955688041896 |
| Matched percentile | 98.84th (p = 0.0117) | 98.87th (p ≈ 0.0113) |

`sparse_network_week_bootstrap_ci.csv`, row `daily_mean_absolute_difference`:
estimate 6.050 µg/m³, CI [4.021, 9.002] — manuscript states CI [4.08, 8.83].
Row `daily_mean_bias_sparse_minus_dense`: estimate 5.956 µg/m³, CI [3.816,
8.923] — manuscript states bias +5.96, CI [3.86, 8.82].

**Reading of the match:** the central estimates agree to three decimal
places (6.050 vs 6.05, 1.821 vs 1.82, 5.956 vs 5.96) — this is almost
certainly the same computation, not a coincidence. The bootstrap interval
edges differ by roughly 0.02–0.2 µg/m³, consistent with re-running the
same stochastic week-block bootstrap under a different random draw than
whatever produced the exact numbers printed in the manuscript, rather than
a different method.

## What does NOT (yet) match, or is missing

- **Random-draw count.** `generating_script_as_supplied.py` draws `B =
  3000` unconstrained random 11-site networks (see the `sim=np.empty((3000,
  6))` loop). The manuscript states **10,000** unconstrained draws. The
  percentile/point estimates are close despite this (see table above), but
  this specific parameter does not match as supplied — either the archived
  script was edited after this run, or a larger rerun was used for the
  final manuscript numbers. Flagged rather than silently reconciled.
- **Geometry-constrained reference (n = 8,029).** The manuscript's second
  randomization reference — networks constrained to a similar centroid and
  spatial extent, median MAE 2.20, matched geometry at the 98.24th
  percentile — is **not computed anywhere in this script or its output**.
  This part of Figure 6 / Section 5.6 remains unrecovered.
- **Generating code for the manuscript's exact final run** (10,000 draws,
  plus the geometry-constrained variant) has not been located in any of the
  four source packages supplied for this repository. What is preserved
  here is the closest archived antecedent found, not a byte-identical
  match to whatever produced the published rounded values.

## Files in this folder

- `generating_script_as_supplied.py` — unmodified copy of
  `run_advanced_validation_fast.py` as originally supplied; produces the
  three CSVs below (among other unrelated diagnostics) when pointed at the
  raw KGMT+AirGradient hourly table (see `data/raw/README.md`).
- `sparse_network_counterfactual_summary.csv`, `sparse_network_week_bootstrap_ci.csv`,
  `kgmt_location_matched_airgradient_subset.csv`, `sparse_network_random_simulation.csv`
  — its outputs, as supplied, unmodified.

## What this means for `results/verified/same_sensor_representativeness/`

That folder (built by `src/spatial/build_same_sensor_representativeness.py`)
is a **separate, independent reconstruction** built after this archive was
lost, using only 6 of 11 station pairs with overlapping data and a
different comparison baseline. It does not agree with either this recovered
archive or the manuscript (see `docs/FIGURE_MAPPING.md`, "Figure 6"). Cite
*this* folder's numbers as the ones matching the manuscript; cite
`results/verified/same_sensor_representativeness/` only as a documented,
non-matching independent check.
