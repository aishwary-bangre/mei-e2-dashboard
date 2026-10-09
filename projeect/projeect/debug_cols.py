import pandas as pd
from backend.analyzer import MEIAnalyzer
a = MEIAnalyzer("QC Raw Data-2.xlsx", "QC Raw Data-3.xlsx", "/Users/khushi.bodhwani_240893/Downloads/MEI SHAPE CORRECTION .xlsx")
print(a.df_past[['parent_uw', 'vendor_invoice_number', 'product_id']].head(10))
