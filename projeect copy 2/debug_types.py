import pandas as pd
from backend.analyzer import MEIAnalyzer
a = MEIAnalyzer("QC Raw Data-2.xlsx", "QC Raw Data-3.xlsx", "/Users/khushi.bodhwani_240893/Downloads/MEI SHAPE CORRECTION .xlsx")
df_p_mei = a.df_past[(a.df_past['status'] == 'QCFailed') & (a.df_past['reason_cluster'].isin(a.mei_clusters))]
w1_failed_pids = {p for p in set(df_p_mei['pid'].unique()) if pd.notna(p) and str(p).lower() != 'nan' and p != ''}

w2_cutoff = pd.Timestamp('2026-08-13')
valid_logs = a.df_log[a.df_log['timestamp'] < w2_cutoff].sort_values('timestamp')

latest_corrections = {}
for pid, group in valid_logs.groupby('pid'):
    latest_corrections[pid] = group.iloc[-1].to_dict()

print("Type of a pid in w1_failed_pids:", type(list(w1_failed_pids)[0]))
print("Type of a pid in latest_corrections:", type(list(latest_corrections.keys())[0]))

intersect = set(w1_failed_pids).intersection(set(latest_corrections.keys()))
print("Intersection in analyze():", len(intersect))
