import pandas as pd
from backend.analyzer import MEIAnalyzer
a = MEIAnalyzer("QC Raw Data-2.xlsx", "QC Raw Data-3.xlsx", "/Users/khushi.bodhwani_240893/Downloads/MEI SHAPE CORRECTION .xlsx")
print("Past row 0:\n", a.df_past.iloc[0])
print("\nLog row 0:\n", a.df_log.iloc[0])
