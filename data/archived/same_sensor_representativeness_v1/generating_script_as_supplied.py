import pandas as pd, numpy as np, json, os
from pathlib import Path
from scipy.optimize import linear_sum_assignment
from scipy.stats import spearmanr, pearsonr
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, precision_score, recall_score, f1_score, balanced_accuracy_score, confusion_matrix
from sklearn.neighbors import NearestNeighbors

OUT=Path('/mnt/data/advanced_validation'); OUT.mkdir(exist_ok=True)
RAW='/mnt/data/almaty_src/almaty_export/almaty_hourly_long.csv.gz'; ST='/mnt/data/almaty_src/almaty_export/almaty_stations.csv'
rng=np.random.default_rng(20260904)
use=['parameter','ts_utc','ts_local','station_id','station_name','source','lat','lon','value_ugm3','cluster_id','cluster_name']
df=pd.read_csv(RAW,usecols=use)
df=df[df.parameter.eq('pm25')].copy(); df['ts_utc']=pd.to_datetime(df.ts_utc,utc=True); df['ts_local']=pd.to_datetime(df.ts_utc,utc=True).dt.tz_convert('Asia/Almaty')
kg=df[df.source.eq('kgmt')].copy(); ag=df[df.source.eq('airgradient')].copy()

# KGMT discontinuity audit
kg['year']=kg.ts_local.dt.year; kg['month_str']=kg.ts_local.dt.strftime('%Y-%m')
yr=kg.pivot_table(index='station_id',columns='year',values='value_ugm3',aggfunc='median'); yr.to_csv(OUT/'kgmt_annual_median.csv')
rows=[]
for sid,row in yr.iterrows():
    years=[int(c) for c in yr.columns if pd.notna(row[c])]
    for a,b in zip(years[:-1],years[1:]):
        x,y=float(row[a]),float(row[b]); ratio=(max(x,y)+0.5)/(min(x,y)+0.5)
        rows.append([sid,a,b,x,y,ratio,'up' if y>x else 'down'])
chg=pd.DataFrame(rows,columns=['station_id','year_from','year_to','median_from','median_to','fold_change_stabilized','direction']); chg.to_csv(OUT/'kgmt_adjacent_year_shifts.csv',index=False)
mon=kg.groupby(['station_id','month_str']).value_ugm3.median().reset_index().sort_values(['station_id','month_str']); mon['prev']=mon.groupby('station_id').value_ugm3.shift(1); mon['ratio_stab']=(np.maximum(mon.value_ugm3,mon.prev)+.5)/(np.minimum(mon.value_ugm3,mon.prev)+.5); mon['direction']=np.where(mon.value_ugm3>mon.prev,'up','down'); mon['large_shift']=mon.ratio_stab>=5
sync=mon[mon.large_shift].groupby(['month_str','direction']).station_id.nunique().reset_index(name='n_stations_large_shift').sort_values('n_stations_large_shift',ascending=False); sync.to_csv(OUT/'kgmt_synchronous_monthly_shifts.csv',index=False)

# KGMT daily/seasonal
kg['local_date']=kg.ts_local.dt.date
sd=kg.groupby(['station_id','local_date']).agg(pm25=('value_ugm3','mean'),n_hours=('value_ugm3','size')).reset_index(); sd=sd[sd.n_hours>=18].copy(); sd['date']=pd.to_datetime(sd.local_date); sd['year']=sd.date.dt.year; sd['month']=sd.date.dt.month
season_map={12:'Winter',1:'Winter',2:'Winter',3:'Spring',4:'Spring',5:'Spring',6:'Summer',7:'Summer',8:'Summer',9:'Autumn',10:'Autumn',11:'Autumn'}; sd['season']=sd.month.map(season_map)
sys=sd.groupby(['station_id','year','season']).pm25.mean().reset_index(); season_summary=sys.groupby('season').pm25.agg(['mean','median','count']).reset_index(); season_summary.to_csv(OUT/'kgmt_season_balanced_summary.csv',index=False)
# pivot block rows station-year, seasons columns
pv=sys.pivot_table(index=['station_id','year'],columns='season',values='pm25'); arr=pv[['Winter','Summer']].dropna().to_numpy(); B=5000; idx=rng.integers(0,len(arr),(B,len(arr))); bs=arr[idx]; w=bs[:,:,0].mean(1); s=bs[:,:,1].mean(1); dif=w-s; rat=w/s
est_w=arr[:,0].mean(); est_s=arr[:,1].mean(); season_ci=pd.DataFrame([['winter_minus_summer',est_w-est_s,np.quantile(dif,.025),np.quantile(dif,.975)],['winter_div_summer',est_w/est_s,np.quantile(rat,.025),np.quantile(rat,.975)]],columns=['metric','estimate','ci_low','ci_high']); season_ci.to_csv(OUT/'kgmt_season_bootstrap_ci.csv',index=False)
# daily exceedance station-balanced; bootstrap stations with replacement
sd['exceed15']=(sd.pm25>15).astype(int); st_ex=sd.groupby('station_id').exceed15.mean().to_numpy(); ex_est=st_ex.mean(); ib=rng.integers(0,len(st_ex),(B,len(st_ex))); exboot=st_ex[ib].mean(1); pd.DataFrame([{'estimate':ex_est,'ci_low':np.quantile(exboot,.025),'ci_high':np.quantile(exboot,.975),'n_station_days':len(sd)}]).to_csv(OUT/'kgmt_daily_exceedance_ci.csv',index=False)
# diurnal station-month-hour means
kg['hour']=kg.ts_local.dt.hour; kg['station_month']=kg.station_id+'__'+kg.ts_local.dt.strftime('%Y-%m'); smh=kg.groupby(['station_id','station_month','hour']).value_ugm3.mean().reset_index(); di=smh.groupby('hour').value_ugm3.agg(['mean','median','count']).reset_index(); di.to_csv(OUT/'kgmt_diurnal_balanced.csv',index=False)

# AirGradient cohort
start=pd.Timestamp('2026-03-18 00:00:00',tz='UTC'); end=pd.Timestamp('2026-04-25 09:00:00',tz='UTC'); expected=int((end-start)/pd.Timedelta(hours=1))+1
agw=ag[(ag.ts_utc>=start)&(ag.ts_utc<=end)].copy(); cov=agw.groupby('station_id').agg(n=('value_ugm3','size'),lat=('lat','first'),lon=('lon','first'),station_name=('station_name','first')).reset_index(); cov['coverage']=cov.n/expected; cohort=cov[cov.coverage>=.90].station_id.tolist(); agc=agw[agw.station_id.isin(cohort)].copy()
stmean=agc.groupby('station_id').agg(pm25=('value_ugm3','mean'),median=('value_ugm3','median'),lat=('lat','first'),lon=('lon','first'),station_name=('station_name','first'),cluster_id=('cluster_id','first'),cluster_name=('cluster_name','first'),n=('value_ugm3','size')).reset_index(); stmean.to_csv(OUT/'airgradient_station_means.csv',index=False)
lat0=np.deg2rad(stmean.lat.mean()); X=np.c_[stmean.lon.values*np.cos(lat0)*111.32,stmean.lat.values*110.57]
def makeW(coords,k=3):
    ind=NearestNeighbors(n_neighbors=k+1).fit(coords).kneighbors(coords,return_distance=False)[:,1:]; W=np.zeros((len(coords),len(coords)))
    for i,js in enumerate(ind): W[i,js]=1
    W=((W+W.T)>0).astype(float); W/=W.sum(1)[:,None]; return W
def moran(y,W,perms=9999,seed=1):
    y=np.asarray(y,float); z=(y-y.mean())/y.std(ddof=0); obs=(z@(W@z))/(z@z) # W row-standard => n/S0=1
    rr=np.random.default_rng(seed); cnt=0
    for _ in range(perms):
        zp=rr.permutation(z); ii=(zp@(W@zp))/(zp@zp); cnt += abs(ii)>=abs(obs)
    return float(obs),(cnt+1)/(perms+1)
W=makeW(X,3); I,p=moran(stmean.pm25,W,9999,2026)
coord=np.c_[stmean.lat,stmean.lon]; y=stmean.pm25.to_numpy(); lin=LinearRegression().fit(coord,y); yl=lin.predict(coord); r2lin=r2_score(y,yl); Il,pl=moran(y-yl,W,9999,2027); quad=make_pipeline(PolynomialFeatures(2,include_bias=False),LinearRegression()).fit(coord,y); yq=quad.predict(coord); r2q=r2_score(y,yq); Iq,pq=moran(y-yq,W,9999,2028)
trend=pd.DataFrame([['raw',np.nan,I,p],['linear_coordinates',r2lin,Il,pl],['quadratic_coordinates',r2q,Iq,pq]],columns=['model','R2','Moran_I','p_perm']); trend.to_csv(OUT/'airgradient_trend_surface_residual_moran.csv',index=False)

# AG daily spatial stats
agc['local_date']=agc.ts_local.dt.date; agd=agc.groupby(['station_id','local_date']).agg(pm25=('value_ugm3','mean'),n_hours=('value_ugm3','size')).reset_index(); agd=agd[agd.n_hours>=18].copy(); mat=agd.pivot(index='local_date',columns='station_id',values='pm25')
D=[]
for d,row in mat.iterrows():
    av=row.dropna();
    if len(av)<90: continue
    ss=stmean.set_index('station_id').loc[av.index]; coords=np.c_[ss.lon.values*np.cos(lat0)*111.32,ss.lat.values*110.57]; WW=makeW(coords,3); ii,pp=moran(av.values,WW,999,abs(hash(str(d)))%(2**32)); D.append([d,len(av),ii,pp,av.mean()])
dm=pd.DataFrame(D,columns=['date','n_stations','Moran_I','p_perm','mean_pm25']); dm.to_csv(OUT/'airgradient_daily_moran.csv',index=False)
# persistence top/bottom decile
pers=[]
for sid in mat.columns:
    den=top=bot=0
    for _,row in mat.iterrows():
        v=row[sid]; av=row.dropna();
        if pd.isna(v) or len(av)<90: continue
        den+=1; top+=v>=av.quantile(.9); bot+=v<=av.quantile(.1)
    if den: pers.append([sid,den,top/den,bot/den,stmean.set_index('station_id').loc[sid,'pm25']])
persist=pd.DataFrame(pers,columns=['station_id','n_days','top_decile_share','bottom_decile_share','station_mean']); persist.to_csv(OUT/'airgradient_hotspot_persistence.csv',index=False)

# Sparse network counterfactual: matched to KGMT locations with unique AG stations
stations=pd.read_csv(ST); kgcoords=stations[stations.source.eq('kgmt')][['station_id','lat','lon','station_name']].dropna().drop_duplicates('station_id'); agcoords=stmean[['station_id','lat','lon','station_name']]
def havmat(a,b):
    R=6371.0088; la1=np.deg2rad(a[:,0])[:,None]; lo1=np.deg2rad(a[:,1])[:,None]; la2=np.deg2rad(b[:,0])[None,:]; lo2=np.deg2rad(b[:,1])[None,:]; dl=la2-la1; do=lo2-lo1; h=np.sin(dl/2)**2+np.cos(la1)*np.cos(la2)*np.sin(do/2)**2; return 2*R*np.arcsin(np.sqrt(h))
DH=havmat(kgcoords[['lat','lon']].to_numpy(),agcoords[['lat','lon']].to_numpy()); rr,cc=linear_sum_assignment(DH); match=pd.DataFrame({'kgmt_station':kgcoords.iloc[rr].station_id.values,'kgmt_name':kgcoords.iloc[rr].station_name.values,'ag_station':agcoords.iloc[cc].station_id.values,'ag_name':agcoords.iloc[cc].station_name.values,'distance_km':DH[rr,cc]}); match.to_csv(OUT/'kgmt_location_matched_airgradient_subset.csv',index=False)
# numpy daily matrix columns same list
M=mat.reindex(columns=stmean.station_id).to_numpy(float); ids=np.array(stmean.station_id); valid_days=np.sum(~np.isnan(M),axis=1)>=90; M=M[valid_days]
# per-day dense stats
dmean=np.nanmean(M,1); dmax=np.nanmax(M,1); dsd=np.nanstd(M,1,ddof=1)
# top decile masks per day
T=np.zeros_like(M,dtype=bool)
for i,row in enumerate(M):
    q=np.nanquantile(row,.9); T[i]=row>=q

def sparse_metrics_idx(idx):
    S=M[:,idx]; sm=np.nanmean(S,1); sx=np.nanmax(S,1); ss=np.nanstd(S,1,ddof=1); ok=np.sum(~np.isnan(S),1)>=8
    if not ok.any(): return [np.nan]*6
    rec=np.nansum(T[:,idx],1)/np.sum(T,1); det=np.nansum(T[:,idx],1)>0
    return [np.nanmean((sm-dmean)[ok]),np.nanmean(np.abs(sm-dmean)[ok]),np.nanmean((sx/dmax)[ok]),np.nanmean(rec[ok]),np.nanmean(det[ok]),np.nanmean((ss/dsd)[ok])]
mid=[np.where(ids==s)[0][0] for s in match.ag_station]; obs=sparse_metrics_idx(mid)
sim=np.empty((3000,6))
for b in range(3000): sim[b]=sparse_metrics_idx(rng.choice(len(ids),11,replace=False))
pd.DataFrame(sim,columns=['mean_bias','mae_daily_mean','mean_max_capture_ratio','mean_topdecile_recall','hotspot_day_detection_share','mean_sd_ratio']).to_csv(OUT/'sparse_network_random_simulation.csv',index=False)
res=[]
for j,k in enumerate(['mean_bias','mae_daily_mean','mean_max_capture_ratio','mean_topdecile_recall','hotspot_day_detection_share','mean_sd_ratio']):
    a=sim[:,j]; res.append([k,obs[j],np.nanmedian(a),np.nanquantile(a,.025),np.nanquantile(a,.975),np.nanmean(a<=obs[j])])
pd.DataFrame(res,columns=['metric','matched_subset','random_median','random_q025','random_q975','matched_percentile']).to_csv(OUT/'sparse_network_counterfactual_summary.csv',index=False)

# Cross-network temporal coherence in overlap
kn=sd.groupby('local_date').pm25.median().rename('kgmt_median'); an=agd.groupby('local_date').pm25.median().rename('ag_median'); coh=pd.concat([kn,an],axis=1).dropna(); coh=coh[(coh.index>=pd.Timestamp('2026-03-19').date())&(coh.index<=pd.Timestamp('2026-04-24').date())]; pr=pearsonr(coh.kgmt_median,coh.ag_median); sr=spearmanr(coh.kgmt_median,coh.ag_median); coh.to_csv(OUT/'cross_network_daily_medians.csv')
pd.DataFrame([{'n_days':len(coh),'pearson_r':pr.statistic,'pearson_p':pr.pvalue,'spearman_rho':sr.statistic,'spearman_p':sr.pvalue,'kgmt_mean_daily_median':coh.kgmt_median.mean(),'ag_mean_daily_median':coh.ag_median.mean(),'mean_difference_kgmt_minus_ag':(coh.kgmt_median-coh.ag_median).mean(),'MAE_between_network_medians':np.mean(abs(coh.kgmt_median-coh.ag_median))}]).to_csv(OUT/'cross_network_coherence_summary.csv',index=False)

# Forecast audit
p1=pd.read_csv('/mnt/data/recheck_results_v2/predictions.csv.gz'); rf=pd.read_csv('/mnt/data/recheck_results_v2/rf_predictions.csv.gz')
rf['ts_utc']=pd.to_datetime(rf.ts_utc,utc=True).dt.tz_localize(None).astype(str); p1['ts_utc']=pd.to_datetime(p1.ts_utc).astype(str); rt=pd.to_datetime(rf.ts_utc,utc=True).dt.tz_convert('Asia/Almaty'); rf['local_date']=rt.dt.date.astype(str); rf['local_week']=rt.dt.strftime('%G-W%V'); pred=pd.concat([p1,rf[p1.columns]],ignore_index=True)
mr=[]
for (h,m,s),g in pred.groupby(['horizon','model','station_id']): mr.append([h,m,s,len(g),mean_absolute_error(g.y_true,g.y_pred),mean_squared_error(g.y_true,g.y_pred)**.5,r2_score(g.y_true,g.y_pred)])
ms=pd.DataFrame(mr,columns=['horizon','model','station_id','n','MAE','RMSE','R2']); ms.to_csv(OUT/'forecast_station_metrics_all_models.csv',index=False); macro=ms.groupby(['horizon','model']).agg(MAE_macro=('MAE','mean'),RMSE_macro=('RMSE','mean'),R2_macro=('R2','mean'),MAE_median_station=('MAE','median'),RMSE_median_station=('RMSE','median')).reset_index(); macro.to_csv(OUT/'forecast_macro_metrics.csv',index=False)
# +24 daily WHO threshold 15
d24=pred[pred.horizon.eq(24)].copy(); d24['local_date']=pd.to_datetime(d24.local_date); dag=d24.groupby(['model','station_id','local_date']).agg(y_true=('y_true','mean'),y_pred=('y_pred','mean'),n=('y_true','size')).reset_index(); dag=dag[dag.n>=18]
fr=[]
for m,g in dag.groupby('model'):
    a=g.y_true.values>15; b=g.y_pred.values>15; tn,fp,fn,tp=confusion_matrix(a,b,labels=[False,True]).ravel(); fr.append([m,len(g),mean_absolute_error(g.y_true,g.y_pred),mean_squared_error(g.y_true,g.y_pred)**.5,r2_score(g.y_true,g.y_pred),precision_score(a,b,zero_division=0),recall_score(a,b,zero_division=0),f1_score(a,b,zero_division=0),balanced_accuracy_score(a,b),tp,fp,tn,fn])
who=pd.DataFrame(fr,columns=['model','n_station_days','MAE_daily','RMSE_daily','R2_daily','precision_exceed15','recall_exceed15','F1_exceed15','balanced_accuracy','TP','FP','TN','FN']); who.to_csv(OUT/'forecast_24h_daily_who15.csv',index=False)
# high hourly pollution regime based on actual test q90
reg=[]
for h in [1,24]:
    base=pred[(pred.horizon==h)&(pred.model=='Persistence')]; thr=np.quantile(base.y_true,.9)
    for m,g in pred[pred.horizon.eq(h)].groupby('model'):
        for label,mask in [('lower90',g.y_true<=thr),('top10',g.y_true>thr)]:
            gg=g[mask]; reg.append([h,m,label,thr,len(gg),mean_absolute_error(gg.y_true,gg.y_pred),mean_squared_error(gg.y_true,gg.y_pred)**.5])
regdf=pd.DataFrame(reg,columns=['horizon','model','regime','test_q90_threshold','n','MAE','RMSE']); regdf.to_csv(OUT/'forecast_pollution_regime_metrics.csv',index=False)

summary={'kgmt_n':len(kg),'ag_n':len(ag),'ag_cohort_n':len(cohort),'ag_common_hours':len(agc),'kgmt_large_adjacent_year_shifts_ge5':int((chg.fold_change_stabilized>=5).sum()),'kgmt_stations_with_ge5_shift':int(chg[chg.fold_change_stabilized>=5].station_id.nunique()),'season_winter_mean':float(est_w),'season_summer_mean':float(est_s),'daily_exceed15_station_balanced':float(ex_est),'airgradient_global_moran_I':I,'airgradient_global_moran_p':p,'airgradient_daily_moran_median':float(dm.Moran_I.median()),'airgradient_daily_moran_sig_share':float((dm.p_perm<=.05).mean()),'linear_trend_R2':r2lin,'linear_residual_moran_I':Il,'linear_residual_moran_p':pl,'quadratic_trend_R2':r2q,'quadratic_residual_moran_I':Iq,'quadratic_residual_moran_p':pq,'persistent_hotspots_topdecile_ge25pct_days':int((persist.top_decile_share>=.25).sum()),'persistent_hotspots_topdecile_ge50pct_days':int((persist.top_decile_share>=.5).sum()),'cross_network_days':len(coh),'cross_network_spearman':float(sr.statistic),'cross_network_spearman_p':float(sr.pvalue),'matched_sparse_mean_distance_km':float(match.distance_km.mean()),'matched_sparse_max_distance_km':float(match.distance_km.max())}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
print('\nSEASON CI\n'+season_ci.to_string(index=False))
print('\nTREND\n'+trend.to_string(index=False))
print('\nSPARSE\n'+pd.read_csv(OUT/'sparse_network_counterfactual_summary.csv').to_string(index=False))
print('\nCROSS NETWORK\n'+pd.read_csv(OUT/'cross_network_coherence_summary.csv').to_string(index=False))
print('\nMACRO FORECAST\n'+macro.to_string(index=False))
print('\nWHO DAILY +24\n'+who.to_string(index=False))
print('\nREGIME\n'+regdf.to_string(index=False))
print('\nSYNC SHIFTS\n'+sync.head(15).to_string(index=False))
