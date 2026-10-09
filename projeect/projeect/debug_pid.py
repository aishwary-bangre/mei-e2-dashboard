import pandas as pd
from backend.analyzer import MEIAnalyzer
a = MEIAnalyzer("QC Raw Data-2.xlsx", "QC Raw Data-3.xlsx", "/Users/khushi.bodhwani_240893/Downloads/MEI SHAPE CORRECTION .xlsx")
pids_past = set(a.df_past['pid'].dropna().astype(str).unique())
pids_log = set(a.df_log['pid'].dropna().astype(str).unique())
print("Sample pids_past:", list(pids_past)[:10])
print("Sample pids_log:", list(pids_log)[:10])
intersection = pids_past.intersection(pids_log)
print("Intersection size:", len(intersection))
if len(intersection) > 0:
    print("Sample intersection:", list(intersection)[:10])
