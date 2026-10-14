"""
Report on the MEI SHAPE CORRECTION workbook: which column the dashboard currently uses for
"Tech" on every sheet, what values it holds, and which other columns look like names or IDs.

Usage (from the project folder):
    python3 inspect_correction_workbook.py "/path/to/MEI SHAPE CORRECTION .xlsx"
Writes workbook_report.txt next to the script and prints it. Send that file back.
Read-only: it never changes the workbook.
"""
import sys, re
import pandas as pd

path = sys.argv[1] if len(sys.argv) > 1 else "/Users/khushi.bodhwani_240893/Downloads/MEI SHAPE CORRECTION .xlsx"
SKIP = ['IMPORTANT', 'JUNE ANALYSIS SUMMARY', 'Sheet22']          # same sheets the dashboard skips
HINTS = ('tech', 'mc', 'machine', 'm/c', 'name', 'operator', 'emp', 'id', 'by', 'done', 'person', 'staff', 'user')

def kind(vals):
    v = [str(x).strip() for x in vals if pd.notna(x) and str(x).strip() != '']
    if not v:
        return "empty"
    num = sum(bool(re.fullmatch(r'\d+(\.0)?', x)) for x in v) / len(v)
    alpha = sum(bool(re.search(r'[A-Za-z]{3,}', x)) for x in v) / len(v)
    if num >= 0.9: return "NUMBERS"
    if alpha >= 0.9: return "TEXT/NAMES"
    return "MIXED"

out = []
def say(s=""):
    out.append(s); print(s)

xl = pd.ExcelFile(path)
say(f"Workbook: {path}")
say(f"Sheets: {xl.sheet_names}")
summary = []
for s in xl.sheet_names:
    if s in SKIP:
        say(f"\n=== {s}: skipped by dashboard ==="); continue
    df = pd.read_excel(path, sheet_name=s)
    cols = list(df.columns)
    pid = [c for c in cols if 'pid' in str(c).lower()]
    date = [c for c in cols if c in ['%f', 'Date', 'DATE', 'timestamp', 'created_at']]
    issue = [c for c in cols if 'issue' in str(c).lower() or 'remark' in str(c).lower()]
    by = [c for c in cols if 'done' in str(c).lower() or 'by' in str(c).lower()]   # EXACT current rule
    say(f"\n=== {s}  ({len(df)} rows) ===")
    say(f"dashboard uses -> PID: {pid[:1]}  DATE: {date[:1]}  ISSUE: {issue[:1]}  TECH(DONE BY): {by[:1] or 'NONE -> shows \"Operator\"'}")
    if len(by) > 1:
        say(f"   (other columns also matching 'done'/'by', ignored: {by[1:]})")
    if not pid:
        say("   no PID column -> sheet is ignored by the dashboard")
    say(f"   {'column':32} {'filled':>6}  {'looks like':11} samples")
    for c in cols:
        col = df[c]
        samples = [str(x) for x in col.dropna().unique()[:4]]
        tag = " <== TECH" if by and c == by[0] else ""
        cand = " (candidate)" if any(h in str(c).lower() for h in HINTS) and not tag else ""
        say(f"   {str(c)[:32]:32} {col.notna().sum():>6}  {kind(col):11} {samples}{tag}{cand}")
    if by:
        summary.append((s, by[0], kind(df[by[0]]), df[by[0]].dropna().astype(str).nunique()))
    else:
        summary.append((s, None, "no column", 0))

say("\n\n##### SUMMARY: what the dashboard shows in 'Tech', per sheet #####")
for s, c, k, n in summary:
    say(f"{s[:28]:28} column={str(c)[:24]:24} contains={k:11} distinct values={n}")
open("workbook_report.txt", "w").write("\n".join(out))
print("\nSaved workbook_report.txt")
