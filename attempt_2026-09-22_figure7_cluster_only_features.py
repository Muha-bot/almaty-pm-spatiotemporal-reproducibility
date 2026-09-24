# Attempt run 2026-09-22, single pass, no hyperparameter tuning against the target.
# Result did NOT reproduce the archived XGB_coordinates numbers -- see docs/FIGURE_MAPPING.md ("Figure 7 feature-set question").

import numpy as np, pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

df = pd.read_csv("data/archived/spatial_block_cv_107/airgradient_spatial_blocks_107.csv")
feat_cols = ["lon", "lat"]
dum = pd.get_dummies(df.cluster_id, prefix="cl", dtype=float)
X = np.c_[df[feat_cols].to_numpy(float), dum.to_numpy()]  # lon, lat, cluster_id one-hot -- NO median (avoids leakage)
y = df.pm25.to_numpy(float); block = df.spatial_block.to_numpy(int)

models = {
    "RF_coordinates_cluster": RandomForestRegressor(n_estimators=300, random_state=20260904, n_jobs=4),
    "XGB_coordinates_cluster": XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.9,
                                             colsample_bytree=0.9, reg_lambda=1.0, random_state=20260904,
                                             objective="reg:squarederror", tree_method="hist", n_jobs=4),
}
rows=[]; preds={m:[] for m in models}; truth={m:[] for m in models}
for b in sorted(np.unique(block)):
    tr, te = block != b, block == b
    for name, mdl in models.items():
        mdl.fit(X[tr], y[tr]); p = mdl.predict(X[te])
        preds[name].append(p); truth[name].append(y[te])
        rows.append({"block": int(b), "model": name, "n": int(te.sum()),
                      "MAE": mean_absolute_error(y[te], p), "RMSE": mean_squared_error(y[te], p) ** 0.5})
by_block = pd.DataFrame(rows)
summary=[]
for name in models:
    yp=np.concatenate(preds[name]); yt=np.concatenate(truth[name]); bb=by_block[by_block.model.eq(name)]
    summary.append({"model":name,"n":len(yt),"MAE_pooled":mean_absolute_error(yt,yp),
                     "RMSE_pooled":mean_squared_error(yt,yp)**0.5,"R2_pooled":r2_score(yt,yp),
                     "MAE_block_macro":bb.MAE.mean(),"RMSE_block_macro":bb.RMSE.mean()})
print(pd.DataFrame(summary).to_string(index=False))
