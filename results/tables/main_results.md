# Main results (selected models, primary test set)

Recomputed from `data/derived/baseline/` by `src/forecasting/verify_archived_results.py` and independently checked against the archived manuscript exports (`make verify`). Formatting only; no values are recalculated or altered here.

| target   |   horizon | ablation   | selected_model   |   validation_MAE |   test_MAE |   test_RMSE |   test_R2 |   persistence_RMSE |   RMSE_reduction_pct_vs_persistence |
|:---------|----------:|:-----------|:-----------------|-----------------:|-----------:|------------:|----------:|-------------------:|------------------------------------:|
| pm10     |         1 | A0_history | RandomForest     |            6.402 |      8.863 |      19.51  |     0.847 |             21.36  |                               8.663 |
| pm10     |         1 | A1_crossPM | XGBoost          |            6.521 |      9.017 |      19.648 |     0.844 |             21.36  |                               8.015 |
| pm10     |        24 | A0_history | RandomForest     |           14.635 |     17.567 |      34.56  |     0.529 |             39.638 |                              12.81  |
| pm10     |        24 | A1_crossPM | RandomForest     |           14.622 |     17.617 |      34.488 |     0.531 |             39.638 |                              12.991 |
| pm25     |         1 | A0_history | RandomForest     |            4     |      6.174 |      15.672 |     0.757 |             17.445 |                              10.162 |
| pm25     |         1 | A1_crossPM | RandomForest     |            4.053 |      6.273 |      15.778 |     0.754 |             17.445 |                               9.555 |
| pm25     |        24 | A0_history | RandomForest     |            7.307 |     10.465 |      22.417 |     0.501 |             27.012 |                              17.01  |
| pm25     |        24 | A1_crossPM | RandomForest     |            7.451 |     10.532 |      22.474 |     0.499 |             27.012 |                              16.801 |
