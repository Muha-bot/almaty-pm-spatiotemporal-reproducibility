# Attempt run 2026-09-22, single pass, no hyperparameter tuning against the target.
# Result did NOT reproduce the archived XGB_coordinates numbers -- see docs/FIGURE_MAPPING.md ("Figure 7 feature-set question").

"""
ONE-SHOT, non-tuned attempt: does adding the extra columns present in the
recovered cohort file (median, cluster_id) -- instead of lon/lat only --
let XGB_coordinates/RF_coordinates reproduce the archived Table 10 numbers?

Methodology is fixed BEFORE looking at the target values:
- Same 5 spatial blocks as the archived file (already ARI=1.0 confirmed).
- Same held-block CV loop as reproduce_spatial_block_cv.py.
- Two models only: RandomForestRegressor and XGBRegressor, generic
  literature-typical hyperparameters (NOT tuned to match the target).
- Feature set: lon, lat, median, one-hot cluster_id -- i.e. every numeric/
  categorical column present in the recovered cohort file besides the
  identifiers and the target itself.
- Reported once, no iteration, no hyperparameter search.
"""
import numpy as np, pandas as pd
from pyproj import Transformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

df = pd.read_csv("data/archived/spatial_block_cv_107/airgradient_spatial_blocks_107.csv")
assert len(df) == 107

feat_cols = ["lon", "lat", "median"]
X_base = df[feat_cols].to_numpy(float)
dum = pd.get_dummies(df.cluster_id, prefix="cl", dtype=float)
X = np.c_[X_base, dum.to_numpy()]
y = df.pm25.to_numpy(float)
block = df.spatial_block.to_numpy(int)

models = {
    "RF_coordinates_plus": RandomForestRegressor(n_estimators=300, max_depth=None, random_state=20260904, n_jobs=4),
    "XGB_coordinates_plus": XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                                          colsample_bytree=0.9, reg_lambda=1.0, random_state=20260904,
                                          objective="reg:squarederror", tree_method="hist", n_jobs=4),
}

rows_by_block = []
preds = {m: [] for m in models}
truth = {m: [] for m in models}
for b in sorted(np.unique(block)):
    tr, te = block != b, block == b
    for name, mdl in models.items():
        mdl.fit(X[tr], y[tr])
        p = mdl.predict(X[te])
        preds[name].append(p); truth[name].append(y[te])
        rows_by_block.append({"block": int(b), "model": name, "n": int(te.sum()),
                               "MAE": mean_absolute_error(y[te], p),
                               "RMSE": mean_squared_error(y[te], p) ** 0.5})

by_block = pd.DataFrame(rows_by_block)
summary = []
for name in models:
    yp = np.concatenate(preds[name]); yt = np.concatenate(truth[name])
    bb = by_block[by_block.model.eq(name)]
    summary.append({"model": name, "n": len(yt),
                     "MAE_pooled": mean_absolute_error(yt, yp),
                     "RMSE_pooled": mean_squared_error(yt, yp) ** 0.5,
                     "R2_pooled": r2_score(yt, yp),
                     "MAE_block_macro": bb.MAE.mean(),
                     "RMSE_block_macro": bb.RMSE.mean()})
out = pd.DataFrame(summary)
print(out.to_string(index=False))
print()
print("TARGET from manuscript Table 10 / archived file:")
print("XGB_coordinates  MAE_pooled=4.135 RMSE_pooled=5.600 R2_pooled=0.552 RMSE_block_macro=5.045")
print("RF_coordinates   MAE_pooled=4.998 RMSE_pooled=6.409 R2_pooled=0.413 RMSE_block_macro=5.762")
