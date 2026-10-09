import pandas as pd
from backend.analyzer import MEIAnalyzer
a = MEIAnalyzer("QC Raw Data-2.xlsx", "QC Raw Data-3.xlsx", "/Users/khushi.bodhwani_240893/Downloads/MEI SHAPE CORRECTION .xlsx")
df_p_mei = a.df_past[(a.df_past['status'] == 'QCFailed') & (a.df_past['reason_cluster'].isin(a.mei_clusters))]
w1_failed_pids = {p for p in set(df_p_mei['pid'].unique()) if pd.notna(p) and str(p).lower() != 'nan' and p != ''}
pids_log = set(a.df_log['pid'].dropna().astype(str).unique())
intersection = w1_failed_pids.intersection(pids_log)
print("Intersection with failed pids:", len(intersection))
