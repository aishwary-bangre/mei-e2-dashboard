import pandas as pd
import numpy as np
import os
import re
import math
import json
import uuid
import hashlib
from datetime import datetime
from rapidfuzz import fuzz

# ---- Only machine-attributable shape reasons (fitter reasons removed) ----
KNOWN_MEI_REASONS = [
    "SMALL SIZE CUT BY MACHINE",
    "Wrong shape cut by machine",
    "Lens slip by machine",
    "Lens Big Size issue",
    "WRONG SHAPE",
    "POP OUT",
    "Lens chipped off while fitting process"
]

# ---- Correction log normalization maps ----
SHAPE_CORRECTION_MAP = {
    "SMALL": "SMALL",
    "SMALL SIZE": "SMALL",
    "BIG": "BIG",
    "BIG SIZE": "BIG",
    "WRONG SHAPE": "WRONG SHAPE",
    "W/SHAPE": "WRONG SHAPE",
    "W/ SHAPE": "WRONG SHAPE",
    "SLIP": "SLIP",
}

CORRECTION_EXCLUDE = {"CHIP", "SCRATCH", "SCR", "NO ISSUE", "POWER", "COATING", "LOST", "TINT", "AR"}


def _normalize_correction_issue(raw: str) -> str | None:
    """Normalize a correction log issue_raw to a standard shape bucket.
    Returns None if the issue should be excluded from shape correction analysis."""
    if not raw or raw == 'nan':
        return None
    upper = raw.strip().upper()

    # Check exclusions first
    for ex in CORRECTION_EXCLUDE:     # whole words (short ones like 'AR' must not match inside 'VARIATION' or 'LARGE')
        if re.search(r'\b' + re.escape(ex) + (r'\b' if len(ex) <= 3 else ''), upper):
            return None

    # Check if it's numeric junk
    cleaned = re.sub(r'[^A-Za-z /]', '', upper).strip()
    if not cleaned:
        return None

    # Direct map
    if cleaned in SHAPE_CORRECTION_MAP:
        return SHAPE_CORRECTION_MAP[cleaned]

    # Substring match
    if "SMALL" in upper:
        return "SMALL"
    if "BIG" in upper:
        if "SMALL" in upper:
            return "BIG/SMALL"
        return "BIG"
    if "W/SHAPE" in upper or "WRONG SHAPE" in upper or "W/ SHAPE" in upper:
        return "WRONG SHAPE"
    if "SLIP" in upper:
        return "SLIP"

    # Fallback: "Correction Logged" or generic
    return "OTHER SHAPE"


def _person_name(raw) -> str:
    """Return the person's name, or '' when the cell holds an ID/number or a placeholder.

    Rule: a name must contain at least two consecutive letters and no digits. So "Ravi Kumar"
    and "QC Lead" are kept; "21", "170379", "T0018024" and "THRS204578TFR" are not a person
    and become blank (shown as "-" in the dashboard).
    """
    t = str(raw).strip() if raw is not None else ''
    if t.lower() in ('', 'nan', 'none', 'operator', 'user', 'n/a'):
        return ''
    if not re.search(r'[A-Za-z]{2,}', t) or re.search(r'\d', t):
        return ''
    return t


def _json_safe(o):
    """NaN/NaT/numpy -> JSON-safe python values."""
    if isinstance(o, dict): return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [_json_safe(v) for v in o]
    if o is pd.NaT: return None
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, (np.floating, float)): return None if (o != o or o in (float('inf'), float('-inf'))) else float(o)
    if isinstance(o, (pd.Timestamp, datetime)): return None if pd.isna(o) else str(o)[:10]
    if isinstance(o, (np.bool_,)): return bool(o)
    return o


class MEIAnalyzer:
    def __init__(self, qc_file_path: str, correction_log_path: str = None, manual_corrections_path: str = "data/manual_corrections.json", archive_path: str = "data/qc_fail_archive.csv", settings_path: str = "data/impact_settings.json",
                 correction_sheets=("Tracing New Correction",)):
        self.qc_file_path = qc_file_path
        # Keep legacy attributes for backwards-compat with analyze() and other methods
        self.past_file_path = qc_file_path
        self.this_file_path = qc_file_path
        self.correction_log_path = correction_log_path or os.path.join(os.path.dirname(__file__), "data", "MEI SHAPE CORRECTION Tracker.xlsx")
        self.manual_corrections_path = manual_corrections_path
        self.archive_path = archive_path
        self.archive_manifest_path = os.path.splitext(archive_path)[0] + "_manifest.json"
        self._archive_cache = None  # (mtime, size, DataFrame)
        self.archive_error = None
        self.qc_done = {}
        self.row_cap_notes = []
        self.settings_path = settings_path
        self.correction_sheets = [self._norm_sheet(x) for x in (correction_sheets or [])]  # only these workbook sheets are read
        self._done_rows = {}
        self.fail_lists = {}
        self.correction_windows = {}
        self._load_settings()

        self.df_past = None
        self.df_this = None
        self.df_qc = None        # Single QC dataframe (replaces df_past / df_this)
        self.df_log = None

        # Labels / metadata
        self.qc_label = os.path.basename(qc_file_path)
        self.qc_total_rows = 0
        # Legacy labels kept for JS backwards-compat
        self.week_past_label = "QC Data"
        self.week_this_label = ""
        self.row_cap_warning = False

        self._load_data()
        self._cluster_reasons()

    def _read_row_cap(self, file_path):
        try:
            hdr = pd.read_excel(file_path, header=None, nrows=2, engine='calamine')
            for v in hdr.iloc[:, 0].astype(str):
                m = re.search(r'limited to (\d+) rows', v)
                if m:
                    return int(m.group(1))
        except Exception:
            pass
        return None

    def _parse_filter_date(self, file_path: str) -> str:
        try:
            df_first = pd.read_excel(file_path, nrows=1, header=None)
            if not df_first.empty:
                val = str(df_first.iloc[0, 0])
                match = re.search(r"after ([\d/]+)[\s\w:]+ and is before ([\d/]+)", val)
                if match:
                    return f"{match.group(1)} - {match.group(2)}"
        except Exception as e:
            print(f"Error parsing date filter from {file_path}: {e}")
        return None

    def _parse_sheet_date(self, sheet_name: str) -> pd.Timestamp:
        months = {'may': 5, 'june': 6, 'july': 7, 'aug': 8, 'august': 8}
        s = sheet_name.lower().strip()
        for m_name, m_num in months.items():
            if m_name in s:
                match = re.search(r'(\d+)', s)
                if match:
                    day = int(match.group(1))
                    return pd.Timestamp(year=2026, month=m_num, day=min(day, 28))
        return pd.Timestamp('2026-01-01')

    def _load_data(self):
        self._done_rows = {}
        self.fail_lists = {}
        self.correction_windows = {}

        # ------------------------------------------------------------------ #
        # SINGLE QC FILE  (replaces the old Period A / Period B pair)
        # ------------------------------------------------------------------ #
        fname = os.path.basename(self.qc_file_path)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [Shape System] Loading QC data from '{fname}'...", flush=True)

        df = pd.read_excel(self.qc_file_path, skiprows=2, engine='calamine')
        self.qc_total_rows = len(df)
        self.qc_label = fname
        # Legacy labels
        self.week_past_label = fname
        self.week_this_label = ""

        print(f"[{datetime.now().strftime('%H:%M:%S')}] [Shape System] [OK] QC data parsed: {len(df):,} rows", flush=True)

        self.row_cap_notes = []
        cap = self._read_row_cap(self.qc_file_path)
        if cap and len(df) >= cap:
            self.row_cap_notes.append(f"QC export hit its {cap:,}-row limit, so rows are missing and counts are a lower bound.")
        self.row_cap_warning = bool(self.row_cap_notes)

        # Filter lens rows only
        frame_inv = pd.Series(dtype=str)
        if 'item_type' in df.columns:
            _is_lens = df['item_type'].astype(str).str.upper().isin(['RIGHTLENS', 'LEFTLENS'])
            _fr = df[~_is_lens & df['vendor_invoice_number'].notna() & df['parent_uw'].notna()]
            frame_inv = _fr.drop_duplicates('parent_uw').set_index('parent_uw')['vendor_invoice_number'].astype(str).str.strip()
            df = df[_is_lens]

        df = df.copy()
        df['frame_invoice'] = df['parent_uw'].map(frame_inv)
        df['status'] = df['status'].astype(str).str.strip()
        df['mei_datetime'] = pd.to_datetime(df['mei_done'], errors='coerce') if 'mei_done' in df.columns else pd.to_datetime(pd.Series(pd.NaT, index=df.index))
        df['shift_bucket'] = df['mei_datetime'].dt.hour.fillna(-1).astype(int).apply(self._get_shift_bucket)
        done = df[df['status'].isin(['QCPass', 'QCPassed', 'QCFailed'])]
        self.qc_done = {
            'QC Data': {
                'total': int(len(done)),
                'failed_all_reasons': int((done['status'] == 'QCFailed').sum()),
                'by_shift': {k: int(v) for k, v in done['shift_bucket'].value_counts().items()},
                'held': int(df['status'].isin(['QCHold', 'QCUnhold']).sum()),
            }
        }
        # Legacy keys for analyze() method
        self.qc_done['Period A'] = self.qc_done['QC Data']
        self.qc_done['Period B'] = self.qc_done['QC Data']

        df['parent_uw'] = df['parent_uw'].fillna(df['vendor_invoice_number']).fillna(df['product_id'])
        df['pid'] = df['frame_product_id'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
        df['pid_invoice'] = df['pid'] + '.' + df['frame_invoice'].fillna('Unknown_Invoice').astype(str)

        # KEY: extract dot_inv from dot_invoice column (the suffix used in Pid.invoice of correction sheet)
        if 'dot_invoice' in df.columns:
            df['dot_inv'] = df['dot_invoice'].fillna('').astype(str).str.strip()
        else:
            # Fallback: use vendor_invoice_number
            df['dot_inv'] = df['vendor_invoice_number'].fillna('').astype(str).str.strip()

        df['status'] = df['status'].astype(str).str.strip()
        df['reason_qc_fail'] = df['reason_qc_fail'].fillna(df['latest_qc_fail_reason']).fillna('No Reason Provided').astype(str).str.strip()

        allowed_reasons = [
            "SMALL SIZE CUT BY MACHINE", "Wrong shape cut by machine",
            "Lens slip by machine", "Lens Big Size issue",
            "WRONG SHAPE", "POP OUT", "Lens chipped off while fitting process"
        ]
        _d = df[df['status'].isin(['QCPass', 'QCPassed', 'QCFailed'])]
        # Store done rows keyed BOTH by pid_invoice AND by dot_inv for two-key lookup
        done_df = pd.DataFrame({
            'pid': _d['pid'].values,
            'pid_invoice': _d['pid_invoice'].values,
            'dot_inv': _d['dot_inv'].values,
            'mei_datetime': _d['mei_datetime'].values,
            'qc_date': pd.to_datetime(_d['QC_created_date'], errors='coerce').values if 'QC_created_date' in _d.columns else pd.NaT,
            'is_mei_fail': ((_d['status'] == 'QCFailed') & _d['reason_qc_fail'].isin(allowed_reasons)).values,
            'period': 'QC Data'
        })
        self._done_rows['QC Data'] = done_df
        # Legacy Period A/B pointing to same data so analyze() still works
        self._done_rows['Period A'] = done_df.assign(period='Period A')
        self._done_rows['Period B'] = done_df.assign(period='Period B')

        mask_fail = (df['status'] == 'QCFailed') & (df['reason_qc_fail'].isin(allowed_reasons))
        df_fail = df[mask_fail].copy()
        df_fail['qc_person_id'] = df_fail['qc_person_id'].fillna('Unknown_Machine').astype(str).str.strip()
        df_fail['vendor_invoice_number'] = df_fail['vendor_invoice_number'].fillna('Unknown_Vendor').astype(str).str.strip()
        df_fail['tray_id'] = df_fail['tray_id'].fillna('Unknown_Tray').astype(str).str.strip()
        df_fail['period'] = 'QC Data'
        df_fail['created_datetime'] = pd.to_datetime(df_fail['QC_created_date'], errors='coerce') if 'QC_created_date' in df_fail.columns else pd.NaT

        # Store as both df_qc (new) and df_past/df_this (legacy for analyze())
        self.df_qc = df_fail
        self.df_past = df_fail.assign(period='Period A')
        self.df_this = df_fail.assign(period='Period B')

        # Archive ingest
        self._archive_ingest(df_fail, self.qc_label, 'QC Data')

        print(f"[{datetime.now().strftime('%H:%M:%S')}] [Shape System] Reading Correction Sheet from '{os.path.basename(self.correction_log_path)}'...", flush=True)
        log_rows = []
        if os.path.exists(self.correction_log_path):
            try:
                xl = pd.ExcelFile(self.correction_log_path)
                for s in xl.sheet_names:
                    if s in ['IMPORTANT', 'JUNE ANALYSIS SUMMARY', 'Sheet22']:
                        continue
                    if self.correction_sheets and self._norm_sheet(s) not in self.correction_sheets:
                        continue
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [Shape System] Parsing sheet '{s}' (targeting Column D 'Pid.invoice', ignoring Columns B & C)...", flush=True)
                    df_s = pd.read_excel(self.correction_log_path, sheet_name=s)
                    if 'Column1' in df_s.columns and 'MEI Fail (DOT)' in df_s.columns:   # failing-list sheet
                        self._capture_fail_list(s, df_s)
                        continue
                    # Ignore Column B ('FRAME PID') and Column C ('INVOICE')
                    # Read Column D ('Pid.invoice' / 'PID.INVOICE') exclusively
                    p_inv_cols = [c for c in df_s.columns if 'pid.invoice' in str(c).lower() or 'pid_invoice' in str(c).lower()]
                    pid_cols = p_inv_cols or [c for c in df_s.columns if 'pid' in str(c).lower() and 'frame' not in str(c).lower()]
                    date_cols = [c for c in df_s.columns if str(c).strip().lower() in ('date', 'timestamp', 'created_at', '%f', 'ct', 'time')]
                    issue_cols = [c for c in df_s.columns if 'issue' in str(c).lower() or 'remark' in str(c).lower()]
                    by_cols = [c for c in df_s.columns if str(c).strip().lower() in ('done by', 'done_by', 'doneby', 'technician', 'tech', 'operator')] \
                        or [c for c in df_s.columns if 'done by' in str(c).lower()]

                    pct_col = 'PERCENTAGE' if 'PERCENTAGE' in df_s.columns else None
                    a_col = 'A' if 'A' in df_s.columns else None
                    b_col = 'B' if 'B' in df_s.columns else None
                    circ_r_col = 'CIRC R' if 'CIRC R' in df_s.columns else None
                    circ_l_col = 'CIRC L' if 'CIRC L' in df_s.columns else None
                    a1_col = 'A1' if 'A1' in df_s.columns else None
                    b1_col = 'B1' if 'B1' in df_s.columns else None
                    circ_r1_col = 'CIRC R1' if 'CIRC R1' in df_s.columns else None
                    circ_l1_col = 'CIRC L1' if 'CIRC L1' in df_s.columns else None

                    if pid_cols:
                        p_col = pid_cols[0]
                        d_col = date_cols[0] if date_cols else None
                        i_col = issue_cols[0] if issue_cols else None
                        by_c = by_cols[0] if by_cols else None
                        w_start, w_end = self._sheet_window(s)
                        fallback_dt = w_end
                        self.correction_windows[self._norm_sheet(s)] = {'sheet': s.strip(), 'start': w_start, 'end': w_end,
                            'overridden': self._norm_sheet(s) in self.settings.get('sheet_windows', {})}

                        for _, row in df_s.iterrows():
                            raw_p_inv = ''
                            if p_inv_cols and pd.notna(row[p_inv_cols[0]]):
                                raw_p_inv = str(row[p_inv_cols[0]]).strip()
                            elif p_col and pd.notna(row[p_col]):
                                raw_p_inv = str(row[p_col]).strip()

                            if not raw_p_inv or raw_p_inv in ('nan', 'None'):
                                continue

                            # Column D format: 'PID.INVOICE' e.g. '234793.CIN-000001260002'
                            # The suffix (after first '.') is the dot_invoice key used to join QC data
                            parts = raw_p_inv.split('.', 1)
                            clean_pid = parts[0].strip()
                            dot_inv_key = parts[1].strip() if len(parts) > 1 else ''

                            if not clean_pid.isdigit():
                                m = re.search(r'\d+', clean_pid)
                                if m:
                                    clean_pid = m.group(0)
                                else:
                                    continue

                            if d_col and pd.notna(row[d_col]):
                                ts = pd.to_datetime(row[d_col], errors='coerce')
                                if pd.isna(ts):
                                    ts = fallback_dt
                            else:
                                ts = fallback_dt

                            iss = str(row[i_col]) if i_col and pd.notna(row[i_col]) else 'Correction Logged'
                            by = str(row[by_c]) if by_c and pd.notna(row[by_c]) else 'Operator'

                            norm_issue = _normalize_correction_issue(iss)

                            _num = lambda c: pd.to_numeric(row[c], errors='coerce') if c in df_s.columns else np.nan
                            _txt = lambda c: str(row[c]).strip() if c in df_s.columns and pd.notna(row[c]) else ''
                            inv_key = raw_p_inv
                            remark = _txt('REMARK') or ''
                            log_rows.append({
                                'pid': clean_pid, 'pid_invoice': inv_key, 'dot_inv_key': dot_inv_key,
                                'remark': remark, 'frame_type': _txt('Frame Type'),
                                'before_total': _num('Total Items'), 'before_qc_done': _num('QC Done (DOT)'),
                                'before_fails': _num('MEI Fail (DOT)'), 'before_fail_pct': _num('MEI Fail % (DOT)'),
                                'window_start': w_start, 'window_end': w_end, 'kind': 'workbook',
                                'timestamp': ts,
                                'issue_raw': iss,
                                'issue_normalized': norm_issue,
                                'DONE BY': _person_name(by),
                                'sheet': s,
                                'PERCENTAGE': pd.to_numeric(row[pct_col], errors='coerce') if pct_col else None,
                                'A': pd.to_numeric(row[a_col], errors='coerce') if a_col else None,
                                'B': pd.to_numeric(row[b_col], errors='coerce') if b_col else None,
                                'CIRC R': pd.to_numeric(row[circ_r_col], errors='coerce') if circ_r_col else None,
                                'CIRC L': pd.to_numeric(row[circ_l_col], errors='coerce') if circ_l_col else None,
                                'A1': pd.to_numeric(row[a1_col], errors='coerce') if a1_col else None,
                                'B1': pd.to_numeric(row[b1_col], errors='coerce') if b1_col else None,
                                'CIRC R1': pd.to_numeric(row[circ_r1_col], errors='coerce') if circ_r1_col else None,
                                'CIRC L1': pd.to_numeric(row[circ_l1_col], errors='coerce') if circ_l1_col else None
                            })

                self.df_log = pd.DataFrame(log_rows)
                if not self.df_log.empty:
                    self.df_log_all = self.df_log.copy()
                    self.df_log = self.df_log[self.df_log['issue_normalized'].notna()].copy()
                else:
                    self.df_log_all = self.df_log.copy()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] [Shape System] [OK] Loaded {len(self.df_log)} shape correction entries ({len(self.df_log_all)} total rows across sheet).", flush=True)
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] [Shape System Error] Error loading correction log sheets: {e}", flush=True)
                self.df_log = pd.DataFrame()
                self.df_log_all = pd.DataFrame()
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Shape System Warning] Correction log file not found at path: {self.correction_log_path}", flush=True)
            self.df_log = pd.DataFrame()
            self.df_log_all = pd.DataFrame()

        self._wb_log, self._wb_log_all = self.df_log.copy(), self.df_log_all.copy()
        self._merge_manual()

    def _observed(self):
        """First/last QC date actually present in the exports. Lenses cut before the first QC date are only partly
        in the data (the ones QC'd later), so corrections are never judged on them."""
        d = self._done_all()
        if d.empty or 'qc_date' not in d.columns or d['qc_date'].dropna().empty:
            return pd.NaT, pd.NaT
        q = d['qc_date'].dropna()
        return q.min().normalize(), q.max().normalize()

    def _autofill_before(self, dm):
        """Entries without 'before' stats get them from the QC data: lenses of that PID.Invoice cut up to the correction day."""
        for c in ('before_fails', 'before_qc_done', 'before_fail_pct', 'before_total'):
            if c not in dm.columns:
                dm[c] = np.nan
        done = self._done_all()
        if done.empty:
            return dm
        obs_from = self._observed()[0]
        for i, r in dm.iterrows():
            if pd.notna(r['before_fails']) and pd.notna(r['before_qc_done']):
                continue
            end = r['timestamp'].normalize() + pd.Timedelta(days=1)
            g = done[(done['pid_invoice'] == r['pid_invoice']) & (done['mei_datetime'] < end)]
            if pd.notna(obs_from):
                g = g[g['mei_datetime'] >= obs_from]
            if len(g):
                dm.at[i, 'before_qc_done'] = float(len(g))
                dm.at[i, 'before_fails'] = float(g['is_mei_fail'].sum())
        return dm

    def _merge_manual(self):
        """Workbook rows + dashboard-entered corrections. Cheap: never re-reads the QC exports or the workbook."""
        wb, wb_all = self._wb_log.copy(), self._wb_log_all.copy()
        rows = self._load_manual_corrections_list()
        if rows:
            dm = self._autofill_before(pd.DataFrame(rows))
            wb = dm if wb.empty else pd.concat([wb, dm], ignore_index=True)
            wb_all = dm if wb_all.empty else pd.concat([wb_all, dm], ignore_index=True)
            print(f"Loaded {len(rows)} manual user-entered physical corrections into analysis pipeline.")
        self.df_log, self.df_log_all = wb, wb_all

    def _load_manual_corrections_list(self):
        rows = []
        if os.path.exists(self.manual_corrections_path):
            try:
                with open(self.manual_corrections_path, 'r') as f:
                    data = json.load(f)
                wb_has_data = hasattr(self, '_wb_log') and self._wb_log is not None and not self._wb_log.empty
                for item in data:
                    if wb_has_data and item.get('is_imported', False):
                        continue
                    clean_pid = str(item.get('pid', '')).strip().replace(r'\.0$', '')
                    if not clean_pid:
                        continue
                    ts = pd.to_datetime(item.get('timestamp', pd.Timestamp.now()), errors='coerce')
                    if pd.isna(ts):
                        ts = pd.Timestamp.now()
                    iss_raw = str(item.get('issue_raw', 'Manual Shape Correction'))
                    corr_type = str(item.get('correction_type', '')).strip().capitalize() or 'Manual'
                    is_man = (corr_type.lower() != 'traced')
                    rows.append({
                        'id': str(item.get('id', uuid.uuid4().hex[:8])),
                        'pid': clean_pid,
                        'pid_invoice': str(item.get('pid_invoice') or clean_pid).strip(),
                        'kind': corr_type.lower(),
                        'correction_type': corr_type,
                        'shift': str(item.get('shift', '')),
                        'shift_ic': str(item.get('shift_ic', '')),
                        'timestamp': ts,
                        'issue_raw': iss_raw,
                        'issue_normalized': _normalize_correction_issue(iss_raw) or "OTHER SHAPE",
                        'DONE BY': _person_name(item.get('done_by', '')),
                        'sheet': 'Manual Entry (User)',
                        'is_manual': is_man,
                        'PERCENTAGE': float(item['percentage_dev']) if item.get('percentage_dev') is not None else None,
                        'A': float(item['a']) if item.get('a') is not None else None,
                        'B': float(item['b']) if item.get('b') is not None else None,
                        'CIRC R': float(item['circ_r']) if item.get('circ_r') is not None else None,
                        'CIRC L': float(item['circ_l']) if item.get('circ_l') is not None else None,
                        'A1': float(item['a1']) if item.get('a1') is not None else None,
                        'B1': float(item['b1']) if item.get('b1') is not None else None,
                        'CIRC R1': float(item['circ_r1']) if item.get('circ_r1') is not None else None,
                        'CIRC L1': float(item['circ_l1']) if item.get('circ_l1') is not None else None,
                        'notes': str(item.get('notes', '')),
                        'remark': str(item.get('notes', '') or ''), 'window_start': ts,
                        'before_fails': float(item['before_fails']) if item.get('before_fails') not in (None, '') else np.nan,
                        'before_qc_done': float(item['before_qc_done']) if item.get('before_qc_done') not in (None, '') else np.nan,
                    })
            except Exception as e:
                print(f"Error loading manual corrections from {self.manual_corrections_path}: {e}")
        return rows

    def save_manual_correction(self, entry: dict):
        os.makedirs(os.path.dirname(os.path.abspath(self.manual_corrections_path)), exist_ok=True)
        current = []
        if os.path.exists(self.manual_corrections_path):
            try:
                with open(self.manual_corrections_path, 'r') as f:
                    current = json.load(f)
            except Exception:
                current = []

        entry_id = entry.get('id') or uuid.uuid4().hex[:8]
        entry['id'] = entry_id
        if 'timestamp' not in entry or not entry['timestamp']:
            entry['timestamp'] = str(pd.Timestamp.now())[:19]

        # Store the exact PID.Invoice as entered
        entry['pid_invoice'] = entry.get('pid_invoice') or entry.get('pid', '')

        # Resolve PID if it's a PID.Invoice string
        try:
            df_combined = pd.concat([self.df_past, self.df_this], ignore_index=True)
            raw_input = str(entry.get('pid_invoice') or entry.get('pid', '')).strip()
            clean_pid = re.sub(r'\.0$', '', raw_input)
            search_pid = clean_pid
            search_invoice = clean_pid
            if '.' in clean_pid:
                parts = clean_pid.split('.', 1)
                search_pid = parts[0]
                search_invoice = parts[1]

            if 'vendor_invoice_number' in df_combined.columns and 'dot_invoice' in df_combined.columns:
                matched = df_combined[(df_combined['pid'] == search_pid) | (df_combined['pid'] == clean_pid) | (df_combined['vendor_invoice_number'] == search_invoice) | (df_combined['vendor_invoice_number'] == clean_pid) | (df_combined['dot_invoice'] == search_invoice) | (df_combined['dot_invoice'] == clean_pid)]
            elif 'vendor_invoice_number' in df_combined.columns:
                matched = df_combined[(df_combined['pid'] == search_pid) | (df_combined['pid'] == clean_pid) | (df_combined['vendor_invoice_number'] == search_invoice) | (df_combined['vendor_invoice_number'] == clean_pid)]
            else:
                matched = df_combined[(df_combined['pid'] == search_pid) | (df_combined['pid'] == clean_pid)]

            if search_pid.isdigit():
                entry['pid'] = search_pid          # the PID typed before the dot is the PID
            elif not matched.empty:
                entry['pid'] = str(matched.iloc[0]['pid'])
            else:
                entry['pid'] = search_pid  # fallback to numeric part
        except Exception as e:
            print(f"Error resolving invoice to PID: {e}")

        # If exists, update; else append
        idx = next((i for i, item in enumerate(current) if item.get('id') == entry_id), -1)
        if idx >= 0:
            current[idx] = entry
        else:
            current.append(entry)

        with open(self.manual_corrections_path, 'w') as f:
            json.dump(current, f, indent=2)

        self._merge_manual()          # instant: only the correction log is rebuilt
        self._cluster_reasons()
        return entry

    DIM_FIELDS = {
        'a': 'A', 'b': 'B', 'circ_r': 'CIRC R', 'circ_l': 'CIRC L',
        'a1': 'A1', 'b1': 'B1', 'circ_r1': 'CIRC R1', 'circ_l1': 'CIRC L1',
    }

    def update_manual_dims(self, entry_id: str, dims: dict):
        """Update the A/B/CIRC R/CIRC L (+ after) values of one manual entry.

        Each save appends a dated snapshot to the entry's `dim_entries` history, so
        daily re-measurements are kept instead of overwritten. Dimensions are display-only
        (classification never reads them), so the in-memory frames are patched directly
        rather than re-reading the 500k-row QC exports.
        Returns the updated entry, or None if the id is not a manual entry.
        """
        if not os.path.exists(self.manual_corrections_path):
            return None
        with open(self.manual_corrections_path, 'r') as f:
            current = json.load(f)
        idx = next((i for i, it in enumerate(current) if it.get('id') == entry_id), -1)
        if idx < 0:
            return None
        entry = current[idx]

        # Seed history with the original values the first time an entry is edited
        hist = entry.get('dim_entries') or []
        if not hist:
            hist.append({'date': str(entry.get('timestamp', ''))[:19],
                         **{k: entry.get(k) for k in self.DIM_FIELDS}})

        new_vals = {}
        for k in self.DIM_FIELDS:
            v = dims.get(k)
            new_vals[k] = None if v is None or v == '' else float(v)
            entry[k] = new_vals[k]
        hist.append({'date': str(pd.Timestamp.now())[:19], **new_vals})
        entry['dim_entries'] = hist
        current[idx] = entry
        with open(self.manual_corrections_path, 'w') as f:
            json.dump(current, f, indent=2)

        for df in (getattr(self, 'df_log', None), getattr(self, 'df_log_all', None)):
            if df is not None and not df.empty and 'id' in df.columns:
                mask = df['id'] == entry_id
                for k, col in self.DIM_FIELDS.items():
                    df.loc[mask, col] = new_vals[k]
        return entry

    def delete_manual_correction(self, entry_id: str):
        if not os.path.exists(self.manual_corrections_path):
            return False
        try:
            with open(self.manual_corrections_path, 'r') as f:
                current = json.load(f)
            filtered = [item for item in current if item.get('id') != entry_id]
            with open(self.manual_corrections_path, 'w') as f:
                json.dump(filtered, f, indent=2)
            self._merge_manual()
            self._cluster_reasons()
            return True
        except Exception as e:
            print(f"Error deleting manual correction {entry_id}: {e}")
            return False

    def get_manual_corrections(self):
        if not os.path.exists(self.manual_corrections_path):
            return []
        try:
            with open(self.manual_corrections_path, 'r') as f:
                return json.load(f)
        except Exception:
            return []


    # ==========================================================
    # RUNNING ARCHIVE + MASTER DATABASE
    # ==========================================================
    ARCHIVE_COLS = [
        'increment_id', 'product_id', 'pid', 'brand', 'shipping_package_id', 'QC_created_date',
        'mei_done', 'parent_uw', 'item_type', 'uw_item_id', 'barcode', 'status', 'reason_qc_fail',
        'QC Fail No of Times', 'qc_person_id', 'fitter_name', 'tray_id', 'vendor_invoice_number',
        'dot_invoice', 'invoice_date', 'sph', 'cyl', 'lens_index', 'shift_bucket', 'frame_invoice', 'pid_invoice',
    ]
    ARCHIVE_KEY_COLS = ['uw_item_id', 'barcode', 'QC_created_date', 'status', 'reason_qc_fail', 'qc_person_id', 'tray_id']

    def _archive_ingest(self, df, source_label, period_label):
        """Append rows of a loaded period that the archive does not have yet (idempotent).

        Only MEI-attributable QCFailed rows are archived (same filter the dashboard uses).
        A row's key is a hash of its identifying fields plus its occurrence number inside the
        batch, so re-loading the same file, or an overlapping export, never double-counts,
        while genuine identical repeat rows inside one export are all kept.
        """
        try:
            b = df[df['status'] == 'QCFailed'].copy()
            if b.empty:
                return
            for c in self.ARCHIVE_COLS:
                if c not in b.columns:
                    b[c] = None
            b = b[self.ARCHIVE_COLS].copy()
            b['QC_created_date'] = pd.to_datetime(b['QC_created_date'], errors='coerce')
            base = b[self.ARCHIVE_KEY_COLS].astype(str).agg('|'.join, axis=1).map(
                lambda t: hashlib.md5(t.encode('utf-8')).hexdigest()[:16])
            b['row_key'] = base + '#' + base.groupby(base).cumcount().astype(str)

            want = self.ARCHIVE_COLS + ['row_key', 'source_label', 'ingested_at']
            if os.path.exists(self.archive_path) and set(want) - set(pd.read_csv(self.archive_path, nrows=0).columns):
                old = pd.read_csv(self.archive_path, dtype=str)       # older archive: add the new columns in place
                for c in want:
                    if c not in old.columns:
                        old[c] = None
                old[want].to_csv(self.archive_path, index=False)
                self._archive_cache = None
            existing = set()
            if os.path.exists(self.archive_path):
                existing = set(pd.read_csv(self.archive_path, usecols=['row_key'], dtype=str)['row_key'])
            new_rows = b[~b['row_key'].isin(existing)].copy()

            now = str(pd.Timestamp.now())[:19]
            if not new_rows.empty:
                new_rows['source_label'] = source_label
                new_rows['ingested_at'] = now
                os.makedirs(os.path.dirname(os.path.abspath(self.archive_path)), exist_ok=True)
                new_rows.to_csv(self.archive_path, mode='a', header=not os.path.exists(self.archive_path), index=False)
                self._archive_cache = None

            # Ledger of what was loaded (one entry per distinct source, updated in place)
            manifest = []
            if os.path.exists(self.archive_manifest_path):
                try:
                    with open(self.archive_manifest_path, 'r') as f:
                        manifest = json.load(f)
                except Exception:
                    manifest = []
            d_min, d_max = b['QC_created_date'].min(), b['QC_created_date'].max()
            sig = (source_label, int(len(b)), str(d_min)[:10], str(d_max)[:10])
            hit = next((m for m in manifest if (m.get('source_label'), m.get('rows_in_file'), m.get('first_date'), m.get('last_date')) == sig), None)
            if hit is None:
                manifest.append({
                    'source_label': source_label, 'loaded_as': period_label, 'rows_in_file': int(len(b)),
                    'rows_added': int(len(new_rows)), 'first_date': sig[2], 'last_date': sig[3], 'ingested_at': now,
                })
            else:
                hit['loaded_as'] = period_label
                hit['last_seen_at'] = now
            with open(self.archive_manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)
            self.archive_error = None
        except Exception as e:
            self.archive_error = str(e)
            print(f"Archive ingest error: {e}")

    def _get_archive_df(self):
        if not os.path.exists(self.archive_path):
            return pd.DataFrame(columns=self.ARCHIVE_COLS)
        st = os.stat(self.archive_path)
        if self._archive_cache and self._archive_cache[0] == st.st_mtime and self._archive_cache[1] == st.st_size:
            return self._archive_cache[2]
        a = pd.read_csv(self.archive_path, dtype=str)
        a['QC_created_date'] = pd.to_datetime(a['QC_created_date'], errors='coerce')
        self._archive_cache = (st.st_mtime, st.st_size, a)
        return a

    @staticmethod
    def _clean_str(series):
        return series.fillna('').astype(str).replace({'nan': '', 'None': '', 'Unknown_Vendor': '', 'Unknown_Machine': ''})

    def _build_master(self):
        """One chronological table: every archived QC fail + every correction (workbook + manual)."""
        frames = []

        arch = self._get_archive_df()
        if arch.empty:  # archive unavailable -> fall back to the periods currently in memory
            cur = pd.concat([self.df_past, self.df_this], ignore_index=True)
            arch = cur[cur['status'] == 'QCFailed'].copy()
            arch['source_label'] = arch['period']
            arch['QC_created_date'] = pd.to_datetime(arch['QC_created_date'], errors='coerce')
        if not arch.empty:
            v = self._clean_str(arch['vendor_invoice_number'])
            d = self._clean_str(arch['dot_invoice'])
            inv = np.where((v != '') & (d != ''), v + ' (' + d + ')', np.where(v != '', v, d))
            pid = arch['pid'].fillna('').astype(str)
            pi = np.where(inv != '', pid.values + '.' + inv, pid.values)
            if 'pid_invoice' in arch.columns:
                ex = arch['pid_invoice'].fillna('').astype(str).values
                pi = np.where(ex != '', ex, pi)
            frames.append(pd.DataFrame({
                'type': 'QC Fail',
                'date': arch['QC_created_date'],
                'pid': pid.values,
                'pid_invoice': pi,
                'who': self._clean_str(arch['qc_person_id']).values,
                'reason': arch['reason_qc_fail'].fillna('').astype(str).values,
                'detail': (arch['shift_bucket'].fillna('').astype(str) + ' | tray ' + arch['tray_id'].fillna('').astype(str)
                           + ' | ' + arch['item_type'].fillna('').astype(str)).values,
                'source': arch['source_label'].fillna('').astype(str).values,
            }))

        log = self.df_log_all if getattr(self, 'df_log_all', None) is not None and not self.df_log_all.empty else self.df_log
        if log is not None and not log.empty:
            def dims(row):
                f = lambda x: '-' if pd.isna(x) else f"{float(x):g}"
                return (f"A:{f(row.get('A'))} B:{f(row.get('B'))} CR:{f(row.get('CIRC R'))} CL:{f(row.get('CIRC L'))}  ->  "
                        f"A1:{f(row.get('A1'))} B1:{f(row.get('B1'))} CR1:{f(row.get('CIRC R1'))} CL1:{f(row.get('CIRC L1'))}")
            pid_c = log['pid'].fillna('').astype(str)
            pinv = log['pid_invoice'].fillna('').astype(str) if 'pid_invoice' in log.columns else pid_c
            frames.append(pd.DataFrame({
                'type': 'Correction',
                'date': pd.to_datetime(log['timestamp'], errors='coerce'),
                'pid': pid_c.values,
                'pid_invoice': np.where(pinv.str.strip() != '', pinv, pid_c).tolist(),
                'who': log['DONE BY'].fillna('').astype(str).values,
                'reason': log['issue_raw'].fillna('').astype(str).values,
                'detail': log.apply(dims, axis=1).values,
                'source': log['sheet'].fillna('').astype(str).values,
            }))

        if not frames:
            return pd.DataFrame(columns=['type', 'date', 'pid', 'pid_invoice', 'who', 'reason', 'detail', 'source'])
        return pd.concat(frames, ignore_index=True)

    def _filter_master(self, search="", type_filter="all", date_from="", date_to="", sort_order="desc"):
        m = self._build_master()
        if type_filter == "fail":
            m = m[m['type'] == 'QC Fail']
        elif type_filter == "correction":
            m = m[m['type'] == 'Correction']
        if date_from:
            m = m[m['date'] >= pd.to_datetime(date_from, errors='coerce')]
        if date_to:
            m = m[m['date'] < pd.to_datetime(date_to, errors='coerce') + pd.Timedelta(days=1)]
        if search:
            q = str(search).lower().strip()
            mask = pd.Series(False, index=m.index)
            for c in ['pid', 'pid_invoice', 'who', 'reason', 'source', 'detail']:
                mask |= m[c].astype(str).str.lower().str.contains(q, na=False, regex=False)
            m = m[mask]
        return m.sort_values(['date', 'pid'], ascending=(sort_order == "asc"), kind='mergesort', na_position='last')

    @staticmethod
    def _fmt_master_date(ts, with_time):
        if pd.isna(ts):
            return ''
        return str(ts)[:19] if with_time else str(ts)[:10]

    def get_explorer_master(self, page=1, limit=50, search="", type_filter="all", date_from="", date_to="", sort_order="desc"):
        m = self._filter_master(search, type_filter, date_from, date_to, sort_order)
        total = len(m)
        pg = m.iloc[(page - 1) * limit: page * limit]
        rows = [{
            "type": r.type, "date": self._fmt_master_date(r.date, r.type == 'Correction'), "pid": r.pid,
            "pid_invoice": r.pid_invoice, "who": r.who, "reason": r.reason, "detail": r.detail, "source": r.source,
        } for r in pg.itertuples()]
        return {"total_rows": total, "page": page, "limit": limit,
                "total_pages": math.ceil(total / limit) if total else 1, "data": rows}

    def export_master_rows(self, search="", type_filter="all", date_from="", date_to="", sort_order="asc"):
        m = self._filter_master(search, type_filter, date_from, date_to, sort_order).copy()
        m['date'] = [self._fmt_master_date(r.date, r.type == 'Correction') for r in m.itertuples()]
        return m.rename(columns={'type': 'Type', 'date': 'Date', 'pid': 'PID', 'pid_invoice': 'PID.Invoice',
                                 'who': 'Machine / Tech', 'reason': 'Reason', 'detail': 'Details', 'source': 'Source'})

    def get_master_summary(self):
        m = self._build_master()
        fails = m[m['type'] == 'QC Fail']
        corr = m[m['type'] == 'Correction']
        dmin = lambda s: None if s.dropna().empty else str(s.min())[:10]
        dmax = lambda s: None if s.dropna().empty else str(s.max())[:10]

        warnings = []
        if self.archive_error:
            warnings.append(f"Archive could not be updated ({self.archive_error}). Showing only the periods currently loaded.")
        warnings.extend(self.row_cap_notes)
        fd = fails['date'].dropna().dt.normalize().drop_duplicates().sort_values()
        if len(fd) > 1:
            gaps = fd.diff().dt.days
            for idx in gaps[gaps > 3].index:
                end = fd.loc[idx]; start = end - pd.Timedelta(days=int(gaps.loc[idx]))
                warnings.append(f"No QC fail records between {str(start)[:10]} and {str(end)[:10]} "
                                f"({int(gaps.loc[idx]) - 1} days). A weekly export may be missing.")
        if not fails.empty and not corr.empty:
            lf, lc = fails['date'].max(), corr['date'].max()
            if pd.notna(lf) and pd.notna(lc) and lc > lf + pd.Timedelta(days=1):
                warnings.append(f"Corrections run to {str(lc)[:10]} but QC fail data ends {str(lf)[:10]}. "
                                f"Upload newer QC exports to see whether those corrections held.")
        if not fails.empty:
            age = (pd.Timestamp.now().normalize() - fails['date'].max().normalize()).days
            if age > 8:
                warnings.append(f"Latest QC fail record is {age} days old ({str(fails['date'].max())[:10]}).")

        manifest = []
        if os.path.exists(self.archive_manifest_path):
            try:
                with open(self.archive_manifest_path, 'r') as f:
                    manifest = json.load(f)
            except Exception:
                manifest = []
        refreshed = None
        for pth in (self.archive_path, self.manual_corrections_path):
            if os.path.exists(pth):
                t = datetime.fromtimestamp(os.path.getmtime(pth)).strftime('%Y-%m-%d %H:%M:%S')
                refreshed = t if refreshed is None or t > refreshed else refreshed

        return {
            "first_entry": dmin(m['date']), "last_entry": dmax(m['date']),
            "total_records": int(len(m)), "fails": int(len(fails)), "corrections": int(len(corr)),
            "first_fail": dmin(fails['date']), "last_fail": dmax(fails['date']),
            "first_correction": dmin(corr['date']), "last_correction": dmax(corr['date']),
            "last_updated": refreshed, "sources": sorted(manifest, key=lambda x: x.get('first_date') or ''),
            "warnings": warnings,
        }

    # ==========================================================
    # CORRECTION IMPACT (workbook sheets + manual entries vs the two QC exports)
    # ==========================================================
    IMPACT_MONTHS = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
    DIM_PAIRS = {'A': ('A', 'A1'), 'B': ('B', 'B1'), 'CIRC R': ('CIRC R', 'CIRC R1'), 'CIRC L': ('CIRC L', 'CIRC L1')}

    @staticmethod
    def _norm_sheet(name):
        return re.sub(r'\s+', '', str(name)).upper()

    def _parse_window(self, name):
        """'21-28 JULY' -> (Jul 21, Jul 28);  '29JULY-3AUG' -> (Jul 29, Aug 3). Year 2026."""
        s = str(name).upper().strip(); M = self.IMPACT_MONTHS
        m = re.search(r'(\d{1,2})\s*([A-Z]{3,})\s*-\s*(\d{1,2})\s*([A-Z]{3,})', s)
        if m:
            d1, m1, d2, m2 = int(m.group(1)), m.group(2), int(m.group(3)), m.group(4)
        else:
            m = re.search(r'(\d{1,2})\s*-\s*(\d{1,2})\s*([A-Z]{3,})', s)
            if not m:
                t = pd.Timestamp('2026-01-01'); return t, t
            d1, d2, m1 = int(m.group(1)), int(m.group(2)), m.group(3); m2 = m1
        a, b = M.get(m1[:3]), M.get(m2[:3])
        if not a or not b:
            t = pd.Timestamp('2026-01-01'); return t, t
        return pd.Timestamp(2026, a, d1), pd.Timestamp(2026, b, d2)

    def _sheet_window(self, sheet):
        a, b = self._parse_window(sheet)
        ov = self.settings.get('sheet_windows', {}).get(self._norm_sheet(sheet))
        if ov:
            try:
                a, b = pd.Timestamp(ov['start']), pd.Timestamp(ov['end'])
            except Exception:
                pass
        return a.normalize(), b.normalize()

    def _load_settings(self):
        d = {'sheet_windows': {}, 'min_volume': 5, 'fail_threshold': 5}
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, 'r') as f:
                    d.update(json.load(f))
            except Exception:
                pass
        self.settings = d

    def update_impact_settings(self, payload: dict):
        """Save user-given dates (per workbook sheet) and thresholds, then reload so every number follows them."""
        d = dict(self.settings)
        for norm, w in (payload.get('sheet_windows') or {}).items():
            if w and w.get('start') and w.get('end'):
                pd.Timestamp(w['start']); pd.Timestamp(w['end'])      # validate
                d.setdefault('sheet_windows', {})[self._norm_sheet(norm)] = {'start': w['start'], 'end': w['end']}
        for k in ('min_volume', 'fail_threshold'):
            if payload.get(k) is not None:
                d[k] = int(payload[k])
        os.makedirs(os.path.dirname(os.path.abspath(self.settings_path)), exist_ok=True)
        with open(self.settings_path, 'w') as f:
            json.dump(d, f, indent=2)
        self.settings = d
        self._load_data()
        self._cluster_reasons()

    def _capture_fail_list(self, sheet, df):
        """'1-7 AUG' / '2-8 AUG': manual lists of failing PID.Invoice with the person's DONE/pending status."""
        rows = {}
        for _, r in df.iterrows():
            k = str(r.get('Column1', '')).strip()
            if not k or k.lower() == 'nan':
                continue
            num = lambda c: (None if c not in df.columns or pd.isna(pd.to_numeric(r[c], errors='coerce')) else float(pd.to_numeric(r[c], errors='coerce')))
            st = str(r['status']).strip() if 'status' in df.columns and pd.notna(r['status']) else ''
            rows[k] = {'total': num('Total Items'), 'qc_done': num('QC Done (DOT)'), 'fails': num('MEI Fail (DOT)'),
                       'fail_pct': num('MEI Fail % (DOT)'), 'status': st}
        self.fail_lists[self._norm_sheet(sheet)] = {'sheet': str(sheet).strip(), 'rows': rows}

    def _done_all(self):
        fr = [d.assign(period=lbl) for lbl, d in self._done_rows.items()]
        return pd.concat(fr, ignore_index=True) if fr else pd.DataFrame(columns=['pid', 'pid_invoice', 'mei_datetime', 'is_mei_fail', 'period'])

    @staticmethod
    def _rate(n, d):
        return round(n / d * 100, 2) if d else None

    def get_correction_impact_by_date(self, date_from: str = None, date_to: str = None) -> dict:
        """Before/after fail analysis for corrections whose CT date falls within [date_from, date_to].

        Join key:  correction.Pid.invoice suffix (after first '.') == QC dot_invoice column.
        BEFORE:    from the sheet's 'MEI Fail (DOT)' and 'QC Done (DOT)' columns (manually written).
                   If those are blank, we look up QC data BEFORE the correction date.
        AFTER:     QC data rows whose dot_invoice matches AND whose QC_created_date >= correction CT date.
        """
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [Impact by Date] Computing impact for CT range: {date_from} -> {date_to}", flush=True)

        # --- Filter correction log by CT date ---
        log_all = self.df_log_all if getattr(self, 'df_log_all', None) is not None and not self.df_log_all.empty else self.df_log
        if log_all is None or log_all.empty:
            return {'total': 0, 'entries': [], 'summary': {}, 'date_from': date_from, 'date_to': date_to}

        log = log_all.copy()
        log['timestamp'] = pd.to_datetime(log['timestamp'], errors='coerce')

        if date_from:
            try:
                log = log[log['timestamp'] >= pd.Timestamp(date_from)]
            except Exception:
                pass
        if date_to:
            try:
                log = log[log['timestamp'] <= pd.Timestamp(date_to) + pd.Timedelta(days=1)]
            except Exception:
                pass

        if log.empty:
            return {'total': 0, 'entries': [], 'summary': {'fixed': 0, 'improved': 0, 'still_failing': 0, 'no_qc_data': 0, 'not_tested': 0},
                    'date_from': date_from, 'date_to': date_to, 'qc_label': self.qc_label}

        # --- Build dot_inv lookup from QC done rows ---
        done = self._done_rows.get('QC Data')
        if done is None or done.empty:
            done = self._done_all()
        # Build index keyed by dot_inv (drop empty)
        done_by_dot = {}
        if done is not None and not done.empty and 'dot_inv' in done.columns:
            for dot_key, g in done[done['dot_inv'] != ''].groupby('dot_inv'):
                done_by_dot[dot_key] = g

        entries = []
        for _, r in log.iterrows():
            dot_key = str(r.get('dot_inv_key', '') or '').strip()
            pid_inv = str(r.get('pid_invoice', '') or '').strip()
            ct_ts = r['timestamp']

            # --- BEFORE stats ---
            bf = r.get('before_fails')
            bq = r.get('before_qc_done')
            bp = r.get('before_fail_pct')
            bf = None if pd.isna(bf) else float(bf)
            bq = None if pd.isna(bq) else float(bq)
            before_rate = round(float(bp) * 100, 2) if pd.notna(bp) else (self._rate(bf, bq) if bf is not None and bq is not None else None)

            # If before is still missing, look up in QC data BEFORE correction date
            if (bf is None or bq is None) and dot_key and dot_key in done_by_dot:
                pre = done_by_dot[dot_key]
                if pd.notna(ct_ts):
                    pre = pre[pre['qc_date'] < ct_ts.normalize()]
                if not pre.empty:
                    bq = float(len(pre))
                    bf = float(pre['is_mei_fail'].sum())
                    before_rate = self._rate(bf, bq)

            # --- AFTER stats: QC rows with matching dot_inv AND date >= correction CT ---
            after_qc = 0
            after_fails = 0
            has_qc_match = False
            if dot_key and dot_key in done_by_dot:
                has_qc_match = True
                post = done_by_dot[dot_key]
                if pd.notna(ct_ts):
                    post = post[post['qc_date'] >= ct_ts.normalize()]
                after_qc = int(len(post))
                after_fails = int(post['is_mei_fail'].sum())

            # --- Status ---
            min_vol = int(self.settings.get('min_volume', 5))
            if not has_qc_match:
                status = 'No QC Data'
            elif after_qc < min_vol:
                status = 'Not Tested Yet'
            elif after_fails == 0:
                status = 'Fixed'
            else:
                after_rate = after_fails / after_qc * 100
                if before_rate is not None and after_rate <= before_rate * 0.5:
                    status = 'Improved'
                else:
                    status = 'Still Failing'

            after_rate_val = self._rate(after_fails, after_qc)

            # Dims
            dims = {}
            for name, (b_col, a_col) in self.DIM_PAIRS.items():
                bv, av = r.get(b_col), r.get(a_col)
                dims[name] = {
                    'before': None if pd.isna(bv) else float(bv),
                    'after': None if pd.isna(av) else float(av),
                    'delta': round(float(av) - float(bv), 2) if pd.notna(bv) and pd.notna(av) else None
                }

            entries.append({
                'pid': str(r.get('pid', '')),
                'pid_invoice': pid_inv,
                'dot_inv_key': dot_key,
                'ct': str(ct_ts)[:16] if pd.notna(ct_ts) else '',
                'issue': r.get('issue_normalized') or r.get('issue_raw') or '',
                'person': str(r.get('DONE BY', '') or ''),
                'remark': str(r.get('remark', '') or ''),
                'sheet': str(r.get('sheet', '') or ''),
                'before': {'fails': bf, 'qc_done': bq, 'rate': before_rate},
                'after': {'qc_done': after_qc, 'fails': after_fails, 'rate': after_rate_val},
                'status': status,
                'dims': dims,
                'deviation_pct': None if pd.isna(r.get('PERCENTAGE')) else r.get('PERCENTAGE'),
            })

        # --- Summary counts ---
        counts = {'Fixed': 0, 'Improved': 0, 'Still Failing': 0, 'Not Tested Yet': 0, 'No QC Data': 0}
        for e in entries:
            counts[e['status']] = counts.get(e['status'], 0) + 1

        # --- Pooled before/after rates ---
        with_data = [e for e in entries if e['before']['fails'] is not None and e['before']['qc_done']]
        pool_bf = sum(e['before']['fails'] or 0 for e in with_data)
        pool_bq = sum(e['before']['qc_done'] or 0 for e in with_data)
        with_after = [e for e in entries if e['after']['qc_done'] > 0]
        pool_af = sum(e['after']['fails'] for e in with_after)
        pool_aq = sum(e['after']['qc_done'] for e in with_after)

        summary = {
            'total': len(entries),
            'has_qc_data': len([e for e in entries if e['status'] != 'No QC Data']),
            'fixed': counts['Fixed'],
            'improved': counts['Improved'],
            'still_failing': counts['Still Failing'],
            'not_tested': counts['Not Tested Yet'],
            'no_qc_data': counts['No QC Data'],
            'pooled_before': {'fails': int(pool_bf), 'qc_done': int(pool_bq), 'rate': self._rate(pool_bf, pool_bq)},
            'pooled_after': {'fails': int(pool_af), 'qc_done': int(pool_aq), 'rate': self._rate(pool_af, pool_aq)},
        }

        print(f"[{datetime.now().strftime('%H:%M:%S')}] [Impact by Date] Done: {len(entries)} entries, {counts['Fixed']} Fixed, {counts['Still Failing']} Still Failing.", flush=True)
        return _json_safe({'total': len(entries), 'entries': entries, 'summary': summary,
                           'date_from': date_from, 'date_to': date_to, 'qc_label': self.qc_label})

    def get_correction_impact(self):
        """Before/after impact of every correction: what is fixed, what is not, and what still needs a correction.

        BEFORE = the failure stats written on the sheet when the PID.Invoice was flagged.
        AFTER  = QC data for the same PID.Invoice on lenses cut AFTER the correction date (sheet window end).
        """
        st = self.settings; min_vol = int(st.get('min_volume', 5)); thr = int(st.get('fail_threshold', 5))
        done = self._done_all()
        obs_from, obs_to = self._observed()
        byk = {k: g for k, g in done.groupby('pid_invoice')} if len(done) else {}
        log = self.df_log if self.df_log is not None else pd.DataFrame()
        entries = []
        if len(log):
            L = log.copy()
            if 'pid_invoice' not in L.columns:
                L['pid_invoice'] = L['pid']
            L['pid_invoice'] = L['pid_invoice'].fillna(L['pid'])
            L['has_after'] = L['A1'].notna() | L['B1'].notna()
            L = L.sort_values(['has_after', 'timestamp']).drop_duplicates('pid_invoice', keep='last')
            for r in L.to_dict('records'):
                key, ts = r['pid_invoice'], r['timestamp']
                cutoff = ts.normalize() + pd.Timedelta(days=1)
                if pd.notna(obs_from) and cutoff < obs_from:
                    cutoff = obs_from            # lenses cut before the first QC day are only partly in the exports
                per = {'A': [0, 0], 'B': [0, 0]}
                g = byk.get(key)
                if g is not None:
                    g = g[g['mei_datetime'] >= cutoff]
                    for lab, pl in (('A', 'Period A'), ('B', 'Period B')):
                        gp = g[g['period'] == pl]
                        per[lab] = [int(len(gp)), int(gp['is_mei_fail'].sum())]
                qa, fa_, qb, fb_ = per['A'][0], per['A'][1], per['B'][0], per['B'][1]
                bf, bq, bp = r.get('before_fails'), r.get('before_qc_done'), r.get('before_fail_pct')
                bf = None if pd.isna(bf) else float(bf)
                bq = None if pd.isna(bq) else float(bq)
                before_rate = round(float(bp) * 100, 2) if pd.notna(bp) else (self._rate(bf, bq) if bf is not None and bq is not None else None)
                vol, fails = qa + qb, fa_ + fb_
                if not r['has_after']:
                    status = 'No correction done'
                elif vol < min_vol:
                    status = 'Not tested yet'
                elif fails == 0:
                    status = 'Fixed'
                else:
                    after_rate = fails / vol * 100
                    status = 'Improved' if (before_rate is not None and after_rate <= before_rate * 0.5) else 'Still failing'
                dims = {}
                for name, (b, a) in self.DIM_PAIRS.items():
                    bv, av = r.get(b), r.get(a)
                    dims[name] = {'before': bv, 'after': av, 'delta': round(float(av) - float(bv), 2) if pd.notna(bv) and pd.notna(av) else None}
                entries.append({
                    'key': key, 'pid': r['pid'], 'sheet': r.get('sheet'), 'kind': r.get('kind', 'workbook'),
                    'window_start': r.get('window_start') if pd.notna(r.get('window_start')) else ts, 'window_end': ts,
                    'issue': r.get('issue_normalized') or r.get('issue_raw'), 'person': r.get('DONE BY') or '',
                    'remark': r.get('remark') or '', 'deviation_pct': r.get('PERCENTAGE'), 'dims': dims,
                    'before': {'fails': bf, 'qc_done': bq, 'rate': before_rate},
                    'after_a': {'qc_done': qa, 'fails': fa_, 'rate': self._rate(fa_, qa)},
                    'after_b': {'qc_done': qb, 'fails': fb_, 'rate': self._rate(fb_, qb)},
                    'status': status, 'judged_from': cutoff,
                })
        order = ['Fixed', 'Improved', 'Still failing', 'Not tested yet', 'No correction done']
        counts = {k: sum(1 for e in entries if e['status'] == k) for k in order}
        done_e = [e for e in entries if e['status'] != 'No correction done']

        def pool(rows, f, q):
            n, d = sum(f(e) or 0 for e in rows), sum(q(e) or 0 for e in rows)
            return {'fails': int(n), 'qc_done': int(d), 'rate': self._rate(n, d)}
        with_before = [e for e in done_e if e['before']['fails'] is not None and e['before']['qc_done']]
        pooled = {'before': pool(with_before, lambda e: e['before']['fails'], lambda e: e['before']['qc_done']),
                  'after_a': pool(done_e, lambda e: e['after_a']['fails'], lambda e: e['after_a']['qc_done']),
                  'after_b': pool(done_e, lambda e: e['after_b']['fails'], lambda e: e['after_b']['qc_done']),
                  'before_n': len(with_before)}
        dim_stats = {}
        for name in self.DIM_PAIRS:
            ds = [e['dims'][name]['delta'] for e in done_e if e['dims'][name]['delta'] is not None]
            dim_stats[name] = {'n': len(ds), 'mean_shift': round(float(np.mean(ds)), 2) if ds else None,
                               'mean_abs_shift': round(float(np.mean(np.abs(ds))), 2) if ds else None}

        def group(field):
            out = {}
            for e in done_e:
                k = str(e[field] or '-')
                o = out.setdefault(k, {'n': 0, 'fixed': 0, 'improved': 0, 'still': 0, 'dev': []})
                o['n'] += 1; o['fixed'] += e['status'] == 'Fixed'; o['improved'] += e['status'] == 'Improved'; o['still'] += e['status'] == 'Still failing'
                if e['deviation_pct'] is not None and pd.notna(e['deviation_pct']): o['dev'].append(float(e['deviation_pct']))
            return [{'name': k, 'n': v['n'], 'fixed': v['fixed'], 'improved': v['improved'], 'still_failing': v['still'],
                     'avg_deviation_pct': round(float(np.mean(v['dev'])), 2) if v['dev'] else None} for k, v in sorted(out.items(), key=lambda x: -x[1]['n'])]

        # PID.Invoices that keep failing but have no correction with dimensions (what is yet to be done)
        corrected_keys = {e['key'] for e in entries if e['status'] != 'No correction done'}
        pend = []
        if len(done):
            mei = done[done['is_mei_fail']]
            fa = mei.groupby(['pid_invoice', 'period']).size().unstack(fill_value=0)
            qc = done.groupby(['pid_invoice', 'period']).size().unstack(fill_value=0)
            for k in fa.index:
                a_, b_ = int(fa.loc[k].get('Period A', 0)), int(fa.loc[k].get('Period B', 0))
                if a_ + b_ >= thr and k not in corrected_keys:
                    qa_ = int(qc.loc[k].get('Period A', 0)) if k in qc.index else 0
                    qb_ = int(qc.loc[k].get('Period B', 0)) if k in qc.index else 0
                    pend.append({'key': k, 'pid': k.split('.')[0], 'fails_a': a_, 'fails_b': b_, 'qc_a': qa_, 'qc_b': qb_,
                                 'rate': self._rate(a_ + b_, qa_ + qb_),
                                 'in_lists': [{'list': v['sheet'], 'status': v['rows'][k]['status'] or 'pending'} for v in self.fail_lists.values() if k in v['rows']]})
            pend.sort(key=lambda x: -(x['fails_a'] + x['fails_b']))

        # The workbook's own VLOOKUP check, done for you: corrected in sheet X -> appears again in list Y?
        allw = self.df_log_all if getattr(self, 'df_log_all', None) is not None and len(self.df_log_all) else pd.DataFrame()
        by_sheet = {}
        if len(allw) and 'kind' in allw.columns:
            for sh, g in allw[allw['kind'] == 'workbook'].groupby('sheet'):
                by_sheet[sh] = set(g['pid_invoice'].dropna().astype(str))
        list_checks = []
        for ln, info in sorted(self.fail_lists.items(), key=lambda x: self._parse_window(x[1]['sheet'])[0]):
            rows = info['rows']
            sts = [v['status'].strip().upper() for v in rows.values()]
            back = {sh: sorted(keys & set(rows)) for sh, keys in by_sheet.items()}
            w0 = self._parse_window(info['sheet'])[0]
            repeat = {o['sheet']: len(set(rows) & set(o['rows'])) for o_ln, o in self.fail_lists.items()
                      if o_ln != ln and self._parse_window(o['sheet'])[0] < w0}
            list_checks.append({'list': info['sheet'], 'keys': len(rows), 'marked_done': sum(x.startswith('DONE') for x in sts),
                                'pending': sum(x == '' for x in sts), 'other_status': sum(x not in ('',) and not x.startswith('DONE') for x in sts),
                                'corrected_then_failing_again': [{'from_sheet': sh, 'count': len(k), 'keys': k[:15]} for sh, k in back.items()],
                                'repeat_from_earlier_lists': repeat, 'corrected_sheet_sizes': {sh: len(k) for sh, k in by_sheet.items()}})

        cov = {}
        for lbl, d in self._done_rows.items():
            m = d['mei_datetime'].dropna()
            cov[lbl] = {'qc_done': int(len(d)), 'cut_from': m.min(), 'cut_to': m.max(),
                        'bulk_from': m.quantile(0.05), 'bulk_to': m.quantile(0.95)}
        wins = sorted(({'norm': n, 'sheet': w['sheet'], 'start': w['start'], 'end': w['end'], 'overridden': w['overridden']}
                       for n, w in self.correction_windows.items()), key=lambda x: x['start'])
        return _json_safe({
            'settings': {'min_volume': min_vol, 'fail_threshold': thr}, 'coverage': cov, 'observed': {'from': obs_from, 'to': obs_to}, 'row_cap_notes': self.row_cap_notes,
            'windows': wins, 'summary': {'counts': counts, 'total': len(entries), 'pooled': pooled, 'dim_stats': dim_stats,
                                         'by_issue': group('issue'), 'by_person': group('person')},
            'entries': entries, 'pending': {'count': len(pend), 'rows': pend[:40]}, 'list_checks': list_checks,
        })

    def check_pid_invoice(self, query: str):
        """What the workbook VLOOKUPs answer, for one PID.Invoice (or every invoice of a PID)."""
        q = str(query).strip()
        done = self._done_all()
        if '.' in q:
            keys = [q]
        else:
            keys = []
            if len(done):
                d = done[done['pid'] == q]
                keys = [k for k in d[d['is_mei_fail']].groupby('pid_invoice').size().sort_values(ascending=False).index[:12]]
                if not keys:
                    keys = list(d['pid_invoice'].unique()[:12])
        allw = self.df_log_all if getattr(self, 'df_log_all', None) is not None and len(self.df_log_all) else pd.DataFrame()
        out = []
        for k in keys:
            g = done[done['pid_invoice'] == k] if len(done) else done
            per = {}
            for pl in ('Period A', 'Period B'):
                gp = g[g['period'] == pl] if len(g) else g
                per[pl] = {'qc_done': int(len(gp)), 'fails': int(gp['is_mei_fail'].sum()) if len(gp) else 0,
                           'rate': self._rate(int(gp['is_mei_fail'].sum()) if len(gp) else 0, len(gp))}
            corr = []
            if len(allw) and 'pid_invoice' in allw.columns:
                for r in allw[allw['pid_invoice'].astype(str) == k].to_dict('records'):
                    corr.append({'sheet': r.get('sheet'), 'date': r.get('timestamp'), 'issue': r.get('issue_raw'), 'person': r.get('DONE BY'),
                                 'dims': {n: [r.get(b), r.get(a)] for n, (b, a) in self.DIM_PAIRS.items()}, 'remark': r.get('remark')})
            lists = [{'list': v['sheet'], **v['rows'][k]} for v in self.fail_lists.values() if k in v['rows']]
            out.append({'key': k, 'in_qc_data': bool(len(g)), 'periods': per, 'corrections': corr, 'lists': lists})
        return _json_safe({'query': q, 'results': out})

    def _get_shift_bucket(self, hour):
        if hour < 0:
            return 'Unknown'
        elif 6 <= hour < 14:
            return 'Morning Shift (06:00-14:00)'
        elif 14 <= hour < 22:
            return 'Evening Shift (14:00-22:00)'
        else:
            return 'Night Shift (22:00-06:00)'

    def _cluster_reasons(self):
        raw_qc = set(self.df_past['reason_qc_fail'].unique()) if self.df_past is not None and not self.df_past.empty else set()
        raw_log_issues = set(self.df_log['issue_raw'].unique()) if not self.df_log.empty else set()

        all_unique_reasons = list(raw_qc.union(raw_log_issues))

        counts = {}
        if self.df_past is not None and not self.df_past.empty:
            for r in self.df_past['reason_qc_fail']:
                counts[r] = counts.get(r, 0) + 1
        if not self.df_log.empty:
            for r in self.df_log['issue_raw']:
                counts[r] = counts.get(r, 0) + 1

        parent = {r: r for r in all_unique_reasons}
        def find(i):
            path = []
            while parent[i] != i:
                path.append(i)
                i = parent[i]
            for node in path:
                parent[node] = i
            return i

        def union(i, j):
            root_i = find(i)
            root_j = find(j)
            if root_i != root_j:
                parent[root_i] = root_j

        n = len(all_unique_reasons)
        for i in range(n):
            for j in range(i + 1, n):
                r1 = all_unique_reasons[i]
                r2 = all_unique_reasons[j]
                if fuzz.ratio(r1.lower(), r2.lower()) >= 85.0:
                    union(r1, r2)

        clusters = {}
        for r in all_unique_reasons:
            root = find(r)
            if root not in clusters:
                clusters[root] = []
            clusters[root].append(r)

        self.reason_cluster_map = {}
        self.raw_counts = counts
        self.clusters_dict = clusters

        for root, members in clusters.items():
            rep = max(members, key=lambda x: counts.get(x, 0))
            for m in members:
                self.reason_cluster_map[m] = rep

        self.df_past['reason_cluster'] = self.df_past['reason_qc_fail'].map(self.reason_cluster_map)
        self.df_this['reason_cluster'] = self.df_this['reason_qc_fail'].map(self.reason_cluster_map)
        if not self.df_log.empty:
            self.df_log['issue_cluster'] = self.df_log['issue_raw'].map(self.reason_cluster_map)

        self.mei_clusters = set()
        for raw, rep in self.reason_cluster_map.items():
            for km in KNOWN_MEI_REASONS:
                if fuzz.ratio(raw.lower(), km.lower()) >= 80.0 or fuzz.ratio(rep.lower(), km.lower()) >= 80.0:
                    self.mei_clusters.add(rep)

        # Keep all QC data — don't filter out non-MEI fails from the dataframe
        # We need total QC Done counts for fail rate calculation

    SHIFT_ORDER = ['Morning Shift (06:00-14:00)', 'Evening Shift (14:00-22:00)', 'Night Shift (22:00-06:00)', 'Unknown']

    @staticmethod
    def _shape_bucket(reason):
        u = str(reason).upper()
        if 'SMALL' in u: return "Small size"
        if 'BIG' in u: return "Big size"
        if 'WRONG SHAPE' in u or 'W/SHAPE' in u: return "Wrong shape"
        if 'SLIP' in u: return "Lens slip"
        if 'POP' in u: return "Pop out"
        if 'CHIP' in u: return "Chipped (fitting)"
        return str(reason)

    def analyze(self):
        """Period A vs Period B view of MEI shape failures.

        Fail rate = MEI shape fail events / QC Done (lens rows QCPass + QCFailed, all reasons).
        Outcome of each Period-A failed PID is judged against Period B:
          a correction counts if logged before the end of Period B;
          it 'recurred' if a lens cut AFTER that correction still failed in Period B.
        """
        mei = lambda df: df[(df['status'] == 'QCFailed') & (df['reason_cluster'].isin(self.mei_clusters))]
        df_a, df_b = mei(self.df_past), mei(self.df_this)
        qa, qb = self.qc_done.get('Period A', {}), self.qc_done.get('Period B', {})
        rate = lambda n, d: round(n / d * 100, 2) if d else 0.0
        ev_a, ev_b = len(df_a), len(df_b)

        valid = lambda df: {p for p in df['pid'].unique() if pd.notna(p) and str(p).lower() not in ('nan', '')}
        pids_a, pids_b = valid(df_a), valid(df_b)

        first_a = df_a.groupby('pid')['created_datetime'].min()
        main_reason = df_a.groupby('pid')['reason_cluster'].agg(lambda x: x.value_counts().index[0])
        cnt_a, cnt_b = df_a['pid'].value_counts(), df_b['pid'].value_counts()
        b_times = df_b['mei_datetime'].fillna(df_b['created_datetime']).groupby(df_b['pid']).apply(list).to_dict()
        bmax = self.df_this['created_datetime'].max() if len(self.df_this) else pd.NaT
        b_end = (bmax.normalize() + pd.Timedelta(days=1)) if pd.notna(bmax) else pd.Timestamp('2262-01-01')

        latest_corrections, all_corrections_by_pid = {}, {}
        if self.df_log is not None and not self.df_log.empty:
            for pid, g in self.df_log[self.df_log['pid'].isin(pids_a)].groupby('pid'):
                g = g[g['timestamp'] < b_end].sort_values('timestamp')
                if len(g):
                    all_corrections_by_pid[pid] = g.to_dict('records')
                    latest_corrections[pid] = g.iloc[-1].to_dict()

        counts = {"Corrected": 0, "Recurred": 0, "Pending": 0, "Corrected-unlogged": 0}
        classified = []
        for pid in pids_a:
            corr = latest_corrections.get(pid)
            if corr is not None:
                fails_after = any(t > corr['timestamp'] for t in b_times.get(pid, []) if pd.notna(t))
                cat = "Recurred" if fails_after else "Corrected"
            else:
                cat = "Pending" if pid in pids_b else "Corrected-unlogged"
            counts[cat] += 1
            row = df_a[df_a['pid'] == pid].iloc[0]
            corr = corr or {}
            dev = corr.get('PERCENTAGE')
            classified.append({
                "pid": pid, "classification": cat, "reason_cluster": main_reason[pid], "raw_reason": row['reason_qc_fail'],
                "qc_person_id": row['qc_person_id'], "vendor_invoice_number": row['vendor_invoice_number'],
                "first_fail_timestamp": str(row['QC_created_date'])[:10],
                "correction_timestamp": str(corr.get('timestamp', 'N/A'))[:10],
                "done_by": str(corr.get('DONE BY', '') or ''),
                "percentage_dev": float(dev) if dev is not None and pd.notna(dev) else None,
                "history_corrections_count": len(all_corrections_by_pid.get(pid, [])),
                "fail_event_count": int(cnt_a.get(pid, 0)), "fail_events_b": int(cnt_b.get(pid, 0)),
            })

        n_a = len(pids_a)
        ba, bb = df_a['reason_cluster'].map(self._shape_bucket).value_counts(), df_b['reason_cluster'].map(self._shape_bucket).value_counts()
        pareto = [{"reason": k, "a": int(ba.get(k, 0)), "b": int(bb.get(k, 0))}
                  for k in sorted(set(ba.index) | set(bb.index), key=lambda k: -(ba.get(k, 0) + bb.get(k, 0)))]

        # Logged shape corrections per shift (Shift A, Shift B, Shift C)
        shift_logged = {
            "Shift A": {"traced": 0, "manual": 0, "total": 0},
            "Shift B": {"traced": 0, "manual": 0, "total": 0},
            "Shift C": {"traced": 0, "manual": 0, "total": 0}
        }
        if self.df_log is not None and not self.df_log.empty:
            for _, r in self.df_log.iterrows():
                s_val = str(r.get('shift', '') or '')
                sh = None
                if 'A' in s_val or 'Morning' in s_val:
                    sh = 'Shift A'
                elif 'B' in s_val or 'Evening' in s_val:
                    sh = 'Shift B'
                elif 'C' in s_val or 'Night' in s_val:
                    sh = 'Shift C'
                if not sh:
                    ts = r.get('timestamp')
                    if pd.notna(ts):
                        try:
                            h = pd.to_datetime(ts).hour
                            if 6 <= h < 14:
                                sh = 'Shift A'
                            elif 14 <= h < 22:
                                sh = 'Shift B'
                            else:
                                sh = 'Shift C'
                        except Exception:
                            sh = 'Shift A'
                    else:
                        sh = 'Shift A'
                is_manual = bool(r.get('is_manual', False)) or str(r.get('kind', '')).lower() == 'manual' or str(r.get('correction_type', '')).lower() == 'manual'
                if is_manual:
                    shift_logged[sh]["manual"] += 1
                else:
                    shift_logged[sh]["traced"] += 1
                shift_logged[sh]["total"] += 1

        shift = [
            {"shift": "Shift A", "shift_label": "Shift A (06:00-14:00)", "total": shift_logged["Shift A"]["total"], "traced": shift_logged["Shift A"]["traced"], "manual": shift_logged["Shift A"]["manual"]},
            {"shift": "Shift B", "shift_label": "Shift B (14:00-22:00)", "total": shift_logged["Shift B"]["total"], "traced": shift_logged["Shift B"]["traced"], "manual": shift_logged["Shift B"]["manual"]},
            {"shift": "Shift C", "shift_label": "Shift C (22:00-06:00)", "total": shift_logged["Shift C"]["total"], "traced": shift_logged["Shift C"]["traced"], "manual": shift_logged["Shift C"]["manual"]}
        ]

        action = sorted([c for c in classified if c['classification'] in ('Recurred', 'Pending')],
                        key=lambda c: (-c['fail_events_b'], -c['fail_event_count']))[:15]

        return {
            "summary": {
                "fail_rate_a": rate(ev_a, qa.get('total', 0)), "fail_rate_b": rate(ev_b, qb.get('total', 0)),
                "events_a": ev_a, "events_b": ev_b, "qc_done_a": qa.get('total', 0), "qc_done_b": qb.get('total', 0),
                "pids_a": n_a, "pids_b": len(pids_b),
                "mei_fail_rate": rate(ev_a, qa.get('total', 0)), "total_mei_fail_events": ev_a, "total_qc_done": qa.get('total', 0),
                "total_w1_fails": n_a, "corrected": counts["Corrected"], "recurred": counts["Recurred"],
                "pending": counts["Pending"], "corrected_unlogged": counts["Corrected-unlogged"],
                "weekly_correction_pct": rate(counts["Corrected"], n_a),
                "week_past_label": self.week_past_label, "week_this_label": self.week_this_label,
                "row_cap_warning": self.row_cap_warning, "row_cap_notes": self.row_cap_notes,
            },
            "classified_pids": classified,
            "pareto": pareto,
            "shift_drift": shift,
            "correction_effectiveness": {"corrected": counts["Corrected"], "recurred": counts["Recurred"],
                                         "pending": counts["Pending"], "corrected_unlogged": counts["Corrected-unlogged"]},
            "action_list": action,
        }

    # ==========================================
    # DATA EXPLORER HELPER METHODS
    # ==========================================

    def get_explorer_fails(self, page=1, limit=50, search="", sort_by="QC_created_date", sort_order="desc", period="all"):
        """Returns paginated, searchable, sortable raw QC Fails rows."""
        df_combined = pd.concat([self.df_past, self.df_this], ignore_index=True)
        df_fails = df_combined[df_combined['status'] == 'QCFailed'].copy()

        if period == "period_a":
            df_fails = df_fails[df_fails['period'] == "Period A"]
        elif period == "period_b":
            df_fails = df_fails[df_fails['period'] == "Period B"]

        if search:
            q = str(search).lower().strip()
            mask = (
                df_fails['pid'].str.lower().str.contains(q, na=False) |
                df_fails['reason_qc_fail'].str.lower().str.contains(q, na=False) |
                df_fails['reason_cluster'].str.lower().str.contains(q, na=False) |
                df_fails['qc_person_id'].str.lower().str.contains(q, na=False) |
                df_fails['vendor_invoice_number'].str.lower().str.contains(q, na=False) |
                df_fails['pid_invoice'].str.lower().str.contains(q, na=False, regex=False)
            )
            df_fails = df_fails[mask]

        if sort_by in df_fails.columns:
            ascending = (sort_order == "asc")
            df_fails = df_fails.sort_values(sort_by, ascending=ascending)

        total_rows = len(df_fails)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit

        df_page = df_fails.iloc[start_idx:end_idx]

        records = []
        for _, row in df_page.iterrows():
            records.append({
                "pid": str(row['pid']),
                "period": str(row['period']),
                "QC_created_date": str(row.get('QC_created_date', 'N/A'))[:10],
                "item_type": str(row.get('item_type', 'N/A')),
                "reason_raw": str(row['reason_qc_fail']),
                "reason_cluster": str(row['reason_cluster']),
                "is_mei_attributable": bool(row['reason_cluster'] in self.mei_clusters),
                "qc_person_id": str(row['qc_person_id']),
                "vendor_invoice_number": str(row['vendor_invoice_number']),
                "tray_id": str(row.get('tray_id', 'N/A'))
            })

        total_pages = math.ceil(total_rows / limit) if total_rows > 0 else 1
        return {
            "total_rows": total_rows,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "data": records
        }

    def get_explorer_corrections(self, page=1, limit=50, search="", sort_by="timestamp", sort_order="desc"):
        """Returns paginated, searchable, sortable physical correction log entries across all 20 sheets."""
        df_c = self.df_log_all.copy() if hasattr(self, 'df_log_all') and not self.df_log_all.empty else self.df_log.copy()
        if df_c.empty:
            return {"total_rows": 0, "page": 1, "limit": limit, "total_pages": 1, "data": []}

        if search:
            q = str(search).lower().strip()
            inv = df_c['pid_invoice'].astype(str) if 'pid_invoice' in df_c.columns else df_c['pid']
            mask = (
                df_c['pid'].str.lower().str.contains(q, na=False) |
                inv.str.lower().str.contains(q, na=False, regex=False) |
                df_c['issue_raw'].str.lower().str.contains(q, na=False) |
                df_c['DONE BY'].str.lower().str.contains(q, na=False) |
                df_c['sheet'].str.lower().str.contains(q, na=False)
            )
            df_c = df_c[mask]

        if sort_by in df_c.columns:
            ascending = (sort_order == "asc")
            df_c = df_c.sort_values(sort_by, ascending=ascending)

        total_rows = len(df_c)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit

        df_page = df_c.iloc[start_idx:end_idx]

        records = []
        for _, row in df_page.iterrows():
            _inv = row.get('pid_invoice')
            _man = row.get('is_manual')
            _id = row.get('id')
            records.append({
                "id": str(_id) if pd.notna(_id) else None,
                "is_manual": bool(pd.notna(_man) and bool(_man)),
                "pid": str(row['pid']),
                "pid_invoice": str(_inv) if pd.notna(_inv) and str(_inv).strip() else str(row['pid']),
                "timestamp": str(row['timestamp'])[:19],
                "sheet": str(row['sheet']),
                "issue_raw": str(row['issue_raw']),
                "issue_normalized": str(row.get('issue_normalized', '')),
                "done_by": str(row['DONE BY']),
                "percentage_dev": float(row['PERCENTAGE']) if pd.notna(row['PERCENTAGE']) else None,
                "dims_before": {
                    "A": float(row['A']) if pd.notna(row['A']) else None,
                    "B": float(row['B']) if pd.notna(row['B']) else None,
                    "CIRC_R": float(row['CIRC R']) if pd.notna(row['CIRC R']) else None,
                    "CIRC_L": float(row['CIRC L']) if pd.notna(row['CIRC L']) else None
                },
                "dims_after": {
                    "A1": float(row['A1']) if pd.notna(row['A1']) else None,
                    "B1": float(row['B1']) if pd.notna(row['B1']) else None,
                    "CIRC_R1": float(row['CIRC R1']) if pd.notna(row['CIRC R1']) else None,
                    "CIRC_L1": float(row['CIRC L1']) if pd.notna(row['CIRC L1']) else None
                }
            })

        total_pages = math.ceil(total_rows / limit) if total_rows > 0 else 1
        return {
            "total_rows": total_rows,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "data": records
        }

    def get_explorer_clusters(self):
        """Returns each discovered rapidfuzz cluster, representative label, and all raw strings merged into it."""
        result = []
        for root, members in self.clusters_dict.items():
            rep = max(members, key=lambda x: self.raw_counts.get(x, 0))
            member_details = []
            total_cluster_count = 0
            for m in members:
                c = self.raw_counts.get(m, 0)
                total_cluster_count += c
                member_details.append({"raw_string": m, "count": c})

            is_mei = rep in self.mei_clusters
            result.append({
                "cluster_representative": rep,
                "is_mei_attributable": is_mei,
                "total_count": total_cluster_count,
                "members": member_details
            })

        # Sort by total count descending
        result.sort(key=lambda x: x['total_count'], reverse=True)
        return result

    def get_explorer_pid_history(self, pid_query: str):
        """Single UW lookup: Returns every fail row + every correction row for a parent UW."""
        clean_pid = str(pid_query).strip()
        # Remove .0 suffix if present
        clean_pid = re.sub(r'\.0$', '', clean_pid)

        query_key = clean_pid
        search_pid = clean_pid
        search_invoice = clean_pid
        if '.' in clean_pid:
            parts = clean_pid.split('.', 1)
            search_pid = parts[0]
            search_invoice = parts[1]

        df_combined = pd.concat([self.df_past, self.df_this], ignore_index=True)
        
        if 'vendor_invoice_number' in df_combined.columns and 'dot_invoice' in df_combined.columns:
            matched = df_combined[(df_combined['pid'] == search_pid) | (df_combined['pid'] == clean_pid) | (df_combined['vendor_invoice_number'] == search_invoice) | (df_combined['vendor_invoice_number'] == clean_pid) | (df_combined['dot_invoice'] == search_invoice) | (df_combined['dot_invoice'] == clean_pid)]
        elif 'vendor_invoice_number' in df_combined.columns:
            matched = df_combined[(df_combined['pid'] == search_pid) | (df_combined['pid'] == clean_pid) | (df_combined['vendor_invoice_number'] == search_invoice) | (df_combined['vendor_invoice_number'] == clean_pid)]
        else:
            matched = df_combined[(df_combined['pid'] == search_pid) | (df_combined['pid'] == clean_pid)]
            
        exact_key = None
        if '.' in query_key and 'pid_invoice' in df_combined.columns:   # exact PID.Invoice, as in the workbook
            _ex = df_combined[df_combined['pid_invoice'] == query_key]
            if len(_ex):
                matched, exact_key = _ex, query_key
        if not matched.empty:
            clean_pid = str(matched.iloc[0]['pid'])

        # 1. QC Fail History for PID
        qc_rows = df_combined[(df_combined['pid'] == clean_pid) & (df_combined['status'] == 'QCFailed')]
        if exact_key:
            qc_rows = qc_rows[qc_rows['pid_invoice'] == exact_key]

        fails_history = []
        vendor_inv_set = set()
        dot_inv_set = set()
        machines_set = set()
        reasons_set = set()

        for _, row in qc_rows.iterrows():
            v_inv = str(row.get('vendor_invoice_number', 'N/A'))
            d_inv = str(row.get('dot_invoice', 'N/A')) if pd.notna(row.get('dot_invoice')) else 'N/A'
            if v_inv != 'N/A' and v_inv != 'Unknown_Vendor': vendor_inv_set.add(v_inv)
            if d_inv != 'N/A': dot_inv_set.add(d_inv)

            m_id = str(row.get('qc_person_id', 'Unknown_Machine'))
            machines_set.add(m_id)

            r_raw = str(row.get('reason_qc_fail', 'No Reason Provided'))
            reasons_set.add(r_raw)

            fails_history.append({
                "pid": clean_pid,
                "period": str(row.get('period', 'Period A')),
                "QC_created_date": str(row.get('QC_created_date', 'N/A'))[:19],
                "vendor_invoice_number": v_inv,
                "dot_invoice": d_inv,
                "invoice": f"{v_inv} ({d_inv})" if d_inv != 'N/A' else v_inv,
                "item_type": str(row.get('item_type', 'N/A')),
                "reason_raw": r_raw,
                "reason_cluster": str(row.get('reason_cluster', r_raw)),
                "is_mei_attributable": bool(row.get('reason_cluster') in self.mei_clusters),
                "qc_person_id": m_id,
                "shift_bucket": str(row.get('shift_bucket', 'N/A')),
                "tray_id": str(row.get('tray_id', 'N/A'))
            })

        # 2. Correction History for PID (all entries, including superseded and user-manual ones)
        corrections_history = []
        df_log_source = self.df_log_all if hasattr(self, 'df_log_all') and not self.df_log_all.empty else self.df_log
        if not df_log_source.empty:
            log_pids = df_log_source[df_log_source['pid'] == clean_pid].sort_values('timestamp')
            for idx, (_, row) in enumerate(log_pids.iterrows()):
                is_latest = (idx == len(log_pids) - 1)

                # Compute precision shift string
                b_a, a_a = row.get('A'), row.get('A1')
                b_b, a_b = row.get('B'), row.get('B1')
                b_cr, a_cr = row.get('CIRC R'), row.get('CIRC R1')
                b_cl, a_cl = row.get('CIRC L'), row.get('CIRC L1')

                prec_shifts = []
                if pd.notna(b_a) and pd.notna(a_a): prec_shifts.append(f"ΔA: {float(a_a)-float(b_a):+.2f}mm")
                if pd.notna(b_b) and pd.notna(a_b): prec_shifts.append(f"ΔB: {float(a_b)-float(b_b):+.2f}mm")
                if pd.notna(b_cr) and pd.notna(a_cr): prec_shifts.append(f"ΔCIRC R: {float(a_cr)-float(b_cr):+.2f}mm")
                if pd.notna(b_cl) and pd.notna(a_cl): prec_shifts.append(f"ΔCIRC L: {float(a_cl)-float(b_cl):+.2f}mm")
                prec_str = ", ".join(prec_shifts) if prec_shifts else "No dimension changes"

                corrections_history.append({
                    "id": str(row.get('id', '')),
                    "pid": clean_pid,
                    "timestamp": str(row['timestamp'])[:19],
                    "sheet": str(row.get('sheet', 'Manual Entry')),
                    "is_manual": bool(row.get('is_manual', False)),
                    "issue_raw": str(row['issue_raw']),
                    "issue_normalized": str(row.get('issue_normalized', '')),
                    "done_by": str(row.get('DONE BY', 'Operator')),
                    "percentage_dev": float(row['PERCENTAGE']) if pd.notna(row['PERCENTAGE']) else None,
                    "is_latest_superseding": is_latest,
                    "dims_before": {
                        "A": float(row['A']) if pd.notna(row['A']) else None,
                        "B": float(row['B']) if pd.notna(row['B']) else None,
                        "CIRC_R": float(row['CIRC R']) if pd.notna(row['CIRC R']) else None,
                        "CIRC_L": float(row['CIRC L']) if pd.notna(row['CIRC L']) else None
                    },
                    "dims_after": {
                        "A1": float(row['A1']) if pd.notna(row['A1']) else None,
                        "B1": float(row['B1']) if pd.notna(row['B1']) else None,
                        "CIRC_R1": float(row['CIRC R1']) if pd.notna(row['CIRC R1']) else None,
                        "CIRC_L1": float(row['CIRC L1']) if pd.notna(row['CIRC L1']) else None
                    },
                    "preciseness_shift": prec_str,
                    "notes": str(row.get('notes', ''))
                })

        # Determine overall classification
        analysis = self.analyze()
        classification_match = next((p for p in analysis['classified_pids'] if p['pid'] == clean_pid), None)

        latest_fail = fails_history[-1] if fails_history else {}
        latest_corr = corrections_history[-1] if corrections_history else {}

        return {
            "pid": clean_pid,
            "classification": classification_match['classification'] if classification_match else "No W1 Fail",
            "fails_count": len(fails_history),
            "corrections_count": len(corrections_history),
            "vendor_invoice": ", ".join(vendor_inv_set) if vendor_inv_set else "N/A",
            "dot_invoice": ", ".join(dot_inv_set) if dot_inv_set else "N/A",
            "primary_invoice": ", ".join(vendor_inv_set.union(dot_inv_set)) if (vendor_inv_set or dot_inv_set) else "N/A",
            "primary_machine": ", ".join(machines_set) if machines_set else "N/A",
            "primary_reason": latest_fail.get('reason_raw', 'N/A'),
            "primary_reason_cluster": latest_fail.get('reason_cluster', 'N/A'),
            "latest_fail_date": latest_fail.get('QC_created_date', 'N/A'),
            "latest_correction_date": latest_corr.get('timestamp', 'N/A'),
            "latest_tech": latest_corr.get('done_by', 'N/A'),
            "fails_history": fails_history,
            "corrections_history": corrections_history
        }

    def get_explorer_classifications(self, page=1, limit=50, search="", sort_by="pid", sort_order="asc", status_filter="all"):
        """Returns paginated, searchable, sortable full PID classification table."""
        analysis = self.analyze()
        all_pids = analysis['classified_pids']

        df_c = pd.DataFrame(all_pids)
        if df_c.empty:
            return {"total_rows": 0, "page": 1, "limit": limit, "total_pages": 1, "data": []}

        if status_filter != "all":
            df_c = df_c[df_c['classification'] == status_filter]

        if search:
            q = str(search).lower().strip()
            mask = (
                df_c['pid'].str.lower().str.contains(q, na=False) |
                df_c['reason_cluster'].str.lower().str.contains(q, na=False) |
                df_c['raw_reason'].str.lower().str.contains(q, na=False) |
                df_c['qc_person_id'].str.lower().str.contains(q, na=False) |
                df_c['vendor_invoice_number'].str.lower().str.contains(q, na=False) |
                df_c['done_by'].str.lower().str.contains(q, na=False)
            )
            df_c = df_c[mask]

        if sort_by in df_c.columns:
            ascending = (sort_order == "asc")
            df_c = df_c.sort_values(sort_by, ascending=ascending)

        total_rows = len(df_c)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit

        df_page = df_c.iloc[start_idx:end_idx]
        total_pages = math.ceil(total_rows / limit) if total_rows > 0 else 1

        # Sanitize any NaN floats so FastAPI JSON serialization never fails
        records = df_page.to_dict('records')
        for r in records:
            for k, v in list(r.items()):
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    r[k] = None

        return {
            "total_rows": total_rows,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "data": records
        }