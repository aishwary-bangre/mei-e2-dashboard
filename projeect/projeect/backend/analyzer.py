import pandas as pd
import numpy as np
import os
import re
import math
import json
import uuid
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
    for ex in CORRECTION_EXCLUDE:
        if ex in upper:
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


class MEIAnalyzer:
    def __init__(self, past_file_path: str, this_file_path: str, correction_log_path: str = None, manual_corrections_path: str = "data/manual_corrections.json"):
        self.past_file_path = past_file_path
        self.this_file_path = this_file_path
        self.correction_log_path = correction_log_path or "/Users/khushi.bodhwani_240893/Downloads/MEI SHAPE CORRECTION .xlsx"
        self.manual_corrections_path = manual_corrections_path

        self.df_past = None
        self.df_this = None
        self.df_log = None

        self.week_past_label = "Period A"
        self.week_this_label = "Period B"
        self.row_cap_warning = False

        self._load_data()
        self._cluster_reasons()

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
        print("Loading Period A data...")
        date_past = self._parse_filter_date(self.past_file_path)
        if date_past:
            self.week_past_label = f"Wk {date_past}"

        self.df_past = pd.read_excel(self.past_file_path, skiprows=2, engine='calamine')

        print("Loading Period B data...")
        date_this = self._parse_filter_date(self.this_file_path)
        if date_this:
            self.week_this_label = f"Wk {date_this}"

        self.df_this = pd.read_excel(self.this_file_path, skiprows=2, engine='calamine')

        if len(self.df_past) == 500000 or len(self.df_this) == 500000:
            self.row_cap_warning = True

        for i in range(2):
            df = self.df_past if i == 0 else self.df_this
            p_label = "Period A" if i == 0 else "Period B"

            # Filter out non-lens items (e.g. FRAME, SUNGLASS)
            if 'item_type' in df.columns:
                df = df[df['item_type'].astype(str).str.upper().isin(['RIGHTLENS', 'LEFTLENS'])]

            df['parent_uw'] = df['parent_uw'].fillna(df['vendor_invoice_number']).fillna(df['product_id'])
            df['pid'] = df['frame_product_id'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
            df['status'] = df['status'].astype(str).str.strip()
            df['reason_qc_fail'] = df['reason_qc_fail'].fillna(df['latest_qc_fail_reason']).fillna('No Reason Provided').astype(str).str.strip()
            
            allowed_reasons = [
                "SMALL SIZE CUT BY MACHINE", "Wrong shape cut by machine", 
                "Lens slip by machine", "Lens Big Size issue", 
                "WRONG SHAPE", "POP OUT", "Lens chipped off while fitting process"
            ]
            mask_pass = df['status'] == 'QCPassed'
            mask_fail = (df['status'] == 'QCFailed') & (df['reason_qc_fail'].isin(allowed_reasons))
            df = df[mask_pass | mask_fail]
            
            df['qc_person_id'] = df['qc_person_id'].fillna('Unknown_Machine').astype(str).str.strip()
            df['vendor_invoice_number'] = df['vendor_invoice_number'].fillna('Unknown_Vendor').astype(str).str.strip()
            df['tray_id'] = df['tray_id'].fillna('Unknown_Tray').astype(str).str.strip()
            df['period'] = p_label

            if 'QC_created_date' in df.columns:
                df['created_datetime'] = pd.to_datetime(df['QC_created_date'], errors='coerce')
                df['hour'] = df['created_datetime'].dt.hour.fillna(-1)
                df['shift_bucket'] = df['hour'].apply(self._get_shift_bucket)
            else:
                df['shift_bucket'] = 'Day Shift'

            if i == 0:
                self.df_past = df
            else:
                self.df_this = df

        print("Loading Manual Physical Correction Log across all workbook sheets...")
        log_rows = []
        if os.path.exists(self.correction_log_path):
            try:
                xl = pd.ExcelFile(self.correction_log_path)
                for s in xl.sheet_names:
                    if s in ['IMPORTANT', 'JUNE ANALYSIS SUMMARY', 'Sheet22']:
                        continue
                    df_s = pd.read_excel(self.correction_log_path, sheet_name=s)
                    pid_cols = [c for c in df_s.columns if 'pid' in str(c).lower()]
                    date_cols = [c for c in df_s.columns if c in ['%f', 'Date', 'DATE', 'timestamp', 'created_at']]
                    issue_cols = [c for c in df_s.columns if 'issue' in str(c).lower() or 'remark' in str(c).lower()]
                    by_cols = [c for c in df_s.columns if 'done' in str(c).lower() or 'by' in str(c).lower()]

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
                        fallback_dt = self._parse_sheet_date(s)

                        for _, row in df_s.iterrows():
                            raw_pid = str(row[p_col]).strip()
                            if not raw_pid or raw_pid == 'nan':
                                continue
                            clean_pid = raw_pid.split('.')[0].strip()
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

                            # Normalize the correction issue
                            norm_issue = _normalize_correction_issue(iss)

                            log_rows.append({
                                'pid': clean_pid,
                                'timestamp': ts,
                                'issue_raw': iss,
                                'issue_normalized': norm_issue,
                                'DONE BY': by,
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
                # Filter out non-shape corrections from the main log
                if not self.df_log.empty:
                    self.df_log_all = self.df_log.copy()  # Keep unfiltered for explorer
                    self.df_log = self.df_log[self.df_log['issue_normalized'].notna()].copy()
                else:
                    self.df_log_all = self.df_log.copy()
                print(f"Loaded {len(self.df_log)} shape correction entries ({len(self.df_log_all)} total across all sheets).")
            except Exception as e:
                print(f"Error loading correction log sheets: {e}")
                self.df_log = pd.DataFrame()
                self.df_log_all = pd.DataFrame()
        else:
            print("Correction log file not found at path.")
            self.df_log = pd.DataFrame()
            self.df_log_all = pd.DataFrame()

        # Load any user-submitted manual physical corrections
        manual_rows = self._load_manual_corrections_list()
        if manual_rows:
            df_manual = pd.DataFrame(manual_rows)
            if self.df_log.empty:
                self.df_log = df_manual
            else:
                self.df_log = pd.concat([self.df_log, df_manual], ignore_index=True)
            if self.df_log_all.empty:
                self.df_log_all = df_manual
            else:
                self.df_log_all = pd.concat([self.df_log_all, df_manual], ignore_index=True)
            print(f"Loaded {len(manual_rows)} manual user-entered physical corrections into analysis pipeline.")

    def _load_manual_corrections_list(self):
        rows = []
        if os.path.exists(self.manual_corrections_path):
            try:
                with open(self.manual_corrections_path, 'r') as f:
                    data = json.load(f)
                for item in data:
                    clean_pid = str(item.get('pid', '')).strip().replace(r'\.0$', '')
                    if not clean_pid:
                        continue
                    ts = pd.to_datetime(item.get('timestamp', pd.Timestamp.now()), errors='coerce')
                    if pd.isna(ts):
                        ts = pd.Timestamp.now()
                    iss_raw = str(item.get('issue_raw', 'Manual Shape Correction'))
                    rows.append({
                        'id': str(item.get('id', uuid.uuid4().hex[:8])),
                        'pid': clean_pid,
                        'pid_invoice': str(item.get('pid_invoice') or clean_pid).strip(),
                        'timestamp': ts,
                        'issue_raw': iss_raw,
                        'issue_normalized': _normalize_correction_issue(iss_raw) or "OTHER SHAPE",
                        'DONE BY': str(item.get('done_by', 'User')),
                        'sheet': 'Manual Entry (User)',
                        'is_manual': True,
                        'PERCENTAGE': float(item['percentage_dev']) if item.get('percentage_dev') is not None else None,
                        'A': float(item['a']) if item.get('a') is not None else None,
                        'B': float(item['b']) if item.get('b') is not None else None,
                        'CIRC R': float(item['circ_r']) if item.get('circ_r') is not None else None,
                        'CIRC L': float(item['circ_l']) if item.get('circ_l') is not None else None,
                        'A1': float(item['a1']) if item.get('a1') is not None else None,
                        'B1': float(item['b1']) if item.get('b1') is not None else None,
                        'CIRC R1': float(item['circ_r1']) if item.get('circ_r1') is not None else None,
                        'CIRC L1': float(item['circ_l1']) if item.get('circ_l1') is not None else None,
                        'notes': str(item.get('notes', ''))
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

            if not matched.empty:
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

        # Reload dataset & recompute clusters
        self._load_data()
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
            self._load_data()
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
        raw_qc_past = set(self.df_past['reason_qc_fail'].unique())
        raw_qc_this = set(self.df_this['reason_qc_fail'].unique())
        raw_log_issues = set(self.df_log['issue_raw'].unique()) if not self.df_log.empty else set()

        all_unique_reasons = list(raw_qc_past.union(raw_qc_this).union(raw_log_issues))

        counts = {}
        for r in self.df_past['reason_qc_fail']:
            counts[r] = counts.get(r, 0) + 1
        for r in self.df_this['reason_qc_fail']:
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

    def analyze(self):
        # --- Total QC Done (all statuses, lens only) ---
        total_qc_done_past = len(self.df_past)
        total_qc_done_this = len(self.df_this)

        # --- MEI shape failures (event-level, not unique PIDs) ---
        df_p_mei = self.df_past[(self.df_past['status'] == 'QCFailed') & (self.df_past['reason_cluster'].isin(self.mei_clusters))]
        df_t_mei = self.df_this[(self.df_this['status'] == 'QCFailed') & (self.df_this['reason_cluster'].isin(self.mei_clusters))]

        total_mei_fail_events_past = len(df_p_mei)
        total_mei_fail_events_this = len(df_t_mei)

        # MEI Shape Fail Rate = MEI failures / QC Done
        mei_fail_rate = round((total_mei_fail_events_past / total_qc_done_past * 100), 2) if total_qc_done_past > 0 else 0.0

        # --- Unique PID-based classification (for correction tracking) ---
        w1_failed_pids = {p for p in set(df_p_mei['pid'].unique()) if pd.notna(p) and str(p).lower() != 'nan' and p != ''}
        w2_failed_pids = {p for p in set(df_t_mei['pid'].unique()) if pd.notna(p) and str(p).lower() != 'nan' and p != ''}

        w2_cutoff = self.df_this['created_datetime'].max() if 'created_datetime' in self.df_this.columns and self.df_this['created_datetime'].notna().any() else pd.Timestamp('2026-08-13')

        latest_corrections = {}
        all_corrections_by_pid = {}

        if not self.df_log.empty:
            valid_logs = self.df_log[self.df_log['timestamp'] < w2_cutoff].sort_values('timestamp')
            for pid, group in valid_logs.groupby('pid'):
                all_corrections_by_pid[pid] = group.to_dict('records')
                latest_corrections[pid] = group.iloc[-1].to_dict()

        classified_pids = []
        counts = {
            "Corrected": 0,
            "Recurred": 0,
            "Pending": 0,
            "Corrected-unlogged": 0
        }

        for pid in w1_failed_pids:
            has_correction = pid in latest_corrections
            fails_in_w2 = pid in w2_failed_pids

            if has_correction and not fails_in_w2:
                cat = "Corrected"
            elif has_correction and fails_in_w2:
                cat = "Recurred"
            elif not has_correction and fails_in_w2:
                cat = "Pending"
            else:
                cat = "Corrected-unlogged"

            counts[cat] += 1

            w1_rows = df_p_mei[df_p_mei['pid'] == pid]
            sample_row = w1_rows.iloc[0]
            corr_info = latest_corrections.get(pid, {})

            p_dev = corr_info.get('PERCENTAGE', None)
            p_dev_val = float(p_dev) if pd.notna(p_dev) else None

            classified_pids.append({
                "pid": pid,
                "classification": cat,
                "reason_cluster": sample_row['reason_cluster'],
                "raw_reason": sample_row['reason_qc_fail'],
                "qc_person_id": sample_row['qc_person_id'],
                "vendor_invoice_number": sample_row['vendor_invoice_number'],
                "first_fail_timestamp": str(sample_row['QC_created_date'])[:10],
                "correction_timestamp": str(corr_info.get('timestamp', 'N/A'))[:10],
                "done_by": str(corr_info.get('DONE BY', 'N/A')),
                "percentage_dev": p_dev_val,
                "history_corrections_count": len(all_corrections_by_pid.get(pid, [])),
                "fail_event_count": len(w1_rows)
            })

        total_w1_fails_pids = len(w1_failed_pids)
        weekly_correction_pct = round((counts["Corrected"] / total_w1_fails_pids * 100), 2) if total_w1_fails_pids > 0 else 0.0

        # --- EVENT-BASED Pareto (failure events, not unique PIDs) ---
        pareto_data = self._build_event_pareto(df_p_mei)

        # --- Machine Problem Table ---
        machine_table = self._build_machine_table(df_p_mei, df_t_mei, latest_corrections, w2_failed_pids, total_qc_done_past)

        # --- Machine x Issue Heatmap ---
        heatmap_machine_issue = self._build_heatmap(df_p_mei, 'qc_person_id', 'reason_cluster')

        # --- Correction Effectiveness ---
        correction_effectiveness = {
            "corrected": counts["Corrected"],
            "recurred": counts["Recurred"],
            "pending": counts["Pending"],
            "corrected_unlogged": counts["Corrected-unlogged"]
        }

        # --- Shift Drift (event-based) ---
        shift_drift_data = self._build_shift_drift(df_p_mei)

        return {
            "summary": {
                "mei_fail_rate": float(mei_fail_rate),
                "total_mei_fail_events": int(total_mei_fail_events_past),
                "total_qc_done": int(total_qc_done_past),
                "total_w1_fails": int(total_w1_fails_pids),
                "corrected": counts["Corrected"],
                "recurred": counts["Recurred"],
                "pending": counts["Pending"],
                "corrected_unlogged": counts["Corrected-unlogged"],
                "weekly_correction_pct": float(weekly_correction_pct),
                "week_past_label": self.week_past_label,
                "week_this_label": self.week_this_label,
                "row_cap_warning": self.row_cap_warning
            },
            "classified_pids": classified_pids,
            "pareto": pareto_data,
            "machine_table": machine_table,
            "heatmap_machine_issue": heatmap_machine_issue,
            "correction_effectiveness": correction_effectiveness,
            "shift_drift": shift_drift_data
        }

    def _build_event_pareto(self, df_mei_fails):
        """Build Pareto from failure EVENTS (rows), not unique PIDs."""
        if df_mei_fails.empty:
            return []

        # Map each cluster reason to a normalized shape bucket for the Pareto
        shape_bucket_map = {}
        for cluster_reason in df_mei_fails['reason_cluster'].unique():
            upper = cluster_reason.upper()
            if 'SMALL' in upper and 'FITTER' not in upper:
                shape_bucket_map[cluster_reason] = "SMALL SIZE (Machine)"
            elif 'BIG' in upper:
                shape_bucket_map[cluster_reason] = "BIG SIZE (Machine)"
            elif 'WRONG SHAPE' in upper or 'W/SHAPE' in upper:
                shape_bucket_map[cluster_reason] = "WRONG SHAPE (Machine)"
            elif 'SLIP' in upper:
                shape_bucket_map[cluster_reason] = "LENS SLIP (Machine)"
            else:
                shape_bucket_map[cluster_reason] = cluster_reason

        reason_counts = {}
        for _, row in df_mei_fails.iterrows():
            bucket = shape_bucket_map.get(row['reason_cluster'], row['reason_cluster'])
            reason_counts[bucket] = reason_counts.get(bucket, 0) + 1

        sorted_reasons = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)
        total_fails = sum(reason_counts.values())

        pareto = []
        cum_count = 0
        for reason, count in sorted_reasons:
            cum_count += count
            pct = round((count / total_fails * 100), 2) if total_fails > 0 else 0.0
            cum_pct = round((cum_count / total_fails * 100), 2) if total_fails > 0 else 0.0
            pareto.append({
                "reason": reason,
                "count": int(count),
                "percentage": float(pct),
                "cumulative_pct": float(cum_pct)
            })
        return pareto

    def _build_machine_table(self, df_p_mei, df_t_mei, latest_corrections, w2_failed_pids, total_qc_done):
        """Build Machine Problem Table: Machine | Failures | Fail Rate | Top Issue | Recurred."""
        if df_p_mei.empty:
            return []

        machines = {}
        for machine_id, group in df_p_mei.groupby('qc_person_id'):
            fail_count = len(group)

            # Get total QC done by this machine for fail rate calc
            machine_total = len(self.df_past[self.df_past['qc_person_id'] == machine_id])
            fail_rate = round((fail_count / machine_total * 100), 2) if machine_total > 0 else 0.0

            # Top issue
            top_issue = group['reason_cluster'].value_counts().index[0] if not group['reason_cluster'].value_counts().empty else 'N/A'

            # Recurred count for this machine
            machine_pids = set(group['pid'].unique())
            recurred = 0
            for pid in machine_pids:
                has_corr = pid in latest_corrections
                still_fails = pid in w2_failed_pids
                if has_corr and still_fails:
                    recurred += 1

            machines[machine_id] = {
                "machine": machine_id,
                "failures": int(fail_count),
                "fail_rate": float(fail_rate),
                "machine_qc_total": int(machine_total),
                "top_issue": top_issue,
                "recurred": int(recurred)
            }

        result = sorted(machines.values(), key=lambda x: x["failures"], reverse=True)
        return result[:20]

    def _build_heatmap(self, df_subset, col_x, col_y):
        if df_subset.empty:
            return {"x": [], "y": [], "z": []}

        ct = pd.crosstab(df_subset[col_y], df_subset[col_x])
        return {
            "x": [str(c) for c in ct.columns],
            "y": [str(r) for r in ct.index],
            "z": ct.values.tolist()
        }

    def _build_shift_drift(self, df_p_mei):
        if df_p_mei.empty:
            return []
        shifts = {}
        for _, row in df_p_mei.iterrows():
            sb = row.get('shift_bucket', 'Day Shift')
            rc = row.get('reason_cluster', 'Other')
            if sb not in shifts:
                shifts[sb] = {"shift": sb, "total_fails": 0, "reasons": {}}
            shifts[sb]["total_fails"] += 1
            shifts[sb]["reasons"][rc] = shifts[sb]["reasons"].get(rc, 0) + 1

        order = ['Morning Shift (06:00-14:00)', 'Evening Shift (14:00-22:00)', 'Night Shift (22:00-06:00)', 'Day Shift', 'Unknown']
        result = []
        for s in order:
            if s in shifts:
                result.append({
                    "shift": s,
                    "total_fails": shifts[s]["total_fails"],
                    "reasons": shifts[s]["reasons"]
                })
        return result

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
                df_fails['vendor_invoice_number'].str.lower().str.contains(q, na=False)
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
            
        if not matched.empty:
            clean_pid = str(matched.iloc[0]['pid'])

        # 1. QC Fail History for PID
        qc_rows = df_combined[(df_combined['pid'] == clean_pid) & (df_combined['status'] == 'QCFailed')]

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