import pandas as pd
from backend.analyzer import MEIAnalyzer
a = MEIAnalyzer("QC Raw Data-2.xlsx", "QC Raw Data-3.xlsx", "/Users/khushi.bodhwani_240893/Downloads/MEI SHAPE CORRECTION .xlsx")
pids_frame = set(a.df_past['frame_product_id'].dropna().astype(str).str.split('.').str[0].unique())
pids_log = set(a.df_log['pid'].dropna().astype(str).unique())
intersection = pids_frame.intersection(pids_log)
print("Intersection size with frame_product_id:", len(intersection))
