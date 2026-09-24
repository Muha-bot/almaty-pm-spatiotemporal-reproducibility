# Reviewer checklist

This checklist lets a reviewer independently confirm what this repository
claims, using only the commands below (Python 3.12, `pip install -r
requirements-minimal.txt`). No step requires external credentials, and no
step downloads large third-party files.

- [ ] Read `README.md` ("What is included" / "What is intentionally NOT
      included") and `docs/REPRODUCIBILITY_STATUS.md` for the exact scope
      of what is, and is not, independently verifiable from this package.
- [ ] Confirm the committed file hashes with `sha256sum -c` (Linux/macOS)
      or an equivalent tool against `MANIFEST_SHA256.txt`, to rule out
      accidental modification after this repository was assembled.
- [ ] Run `make verify` (or the three commands below individually) and
      confirm every check prints `PASS`:

  ```bash
  python src/forecasting/verify_archived_results.py \
    --data-dir data/derived/baseline --out-dir results/verified
  python src/data/verify_almaty_hourly_long.py \
    --data data/derived/baseline/almaty_hourly_long.csv.gz \
    --qc-out results/verified/almaty_hourly_long_qc_recomputed.json
  python src/spatial/verify_spatial_archive.py \
    --data-dir data/derived/spatial
  ```

- [ ] Run `make test` (`pytest -q`) as a single automated entry point over
      the same three checks; confirm `3 passed`.
- [ ] Compare the printed selected-model table (or
      `results/verified/validation_selected_primary_test_results_recomputed.csv`
      / `results/tables/main_results.md`) against the corresponding table
      in the manuscript. Confirm model choice, MAE/RMSE/R², and the
      persistence-baseline RMSE reduction agree.
- [ ] Run `make figures` and compare the regenerated PNGs in `figures/`
      against the manuscript's corresponding figures. **Before comparing,
      read `docs/FIGURE_MAPPING.md`** — not every repository figure is
      meant to match a manuscript figure 1:1, and two manuscript figures
      (6 and 7) currently have no corresponding image in this repository
      at all.
- [ ] Read `docs/RESULTS_PROVENANCE.md` and confirm the listed SHA-256
      values for each archived artifact match `MANIFEST_SHA256.txt`.
- [ ] Note the documented limitation in `docs/REPRODUCIBILITY_STATUS.md`:
      the original row-level A0/A1 training/prediction script is not part
      of this package, so `make verify` confirms the archived metric
      exports and the KGMT/AirGradient/GWR input data, but does not by
      itself constitute an end-to-end retraining reproduction.
- [ ] Check `docs/DATA_LICENSE.md` for the terms attached to the
      redistributed AirData.kz snapshot before reusing the data.
- [ ] Read `docs/KNOWN_LIMITATIONS.md` — it lists exactly which
      reproducibility gaps (missing training seeds, unverified raw GIS
      binaries) cannot be closed by this package and why, so they are not
      mistaken for oversights.
- [ ] Run `python scripts/check_no_placeholders.py` and confirm no
      `[Author]`/`[Institution]`/`[Journal name]` placeholders remain
      before treating the repository as release-ready.
- [ ] Confirm the manuscript's scientific claims are not broader than what
      `docs/REPRODUCIBILITY_STATUS.md` documents as verified; if a gap is
      found, it is worth a quick note to the authors so it can be
      addressed in a revision or reviewer response.
