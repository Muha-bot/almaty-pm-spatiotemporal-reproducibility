.PHONY: verify verify-baseline verify-hourly verify-spatial figures syntax test verify-new-figures

verify: verify-baseline verify-hourly verify-spatial

test:
	pytest -q

verify-new-figures:
	python src/spatial/verify_new_figures_6_7.py --repo-root .

figures-new:
	python src/figures/make_same_sensor_figure.py --repo-root .
	python src/figures/make_archived_spatial_block_figure.py --repo-root .
	python src/figures/make_spatial_block_xgboost_figure.py --repo-root .

verify-baseline:
	python src/forecasting/verify_archived_results.py --data-dir data/derived/baseline --out-dir results/verified

verify-hourly:
	python src/data/verify_almaty_hourly_long.py \
	  --data data/derived/baseline/almaty_hourly_long.csv.gz \
	  --qc-out results/verified/almaty_hourly_long_qc_recomputed.json

verify-spatial:
	python src/spatial/verify_spatial_archive.py --data-dir data/derived/spatial

figures:
	python src/figures/make_verified_figures.py --repo-root .

syntax:
	python -m py_compile $$(find src -name '*.py' -type f)
