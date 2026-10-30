# MEI Shape Correction Dashboard — Project Documentation

## 1. Purpose

In a lens manufacturing / QC (Quality Control) facility, cutting machines shape lenses to spec. When a machine cuts a lens incorrectly — too small, too big, wrong shape, or the lens slips during cutting — it results in a **QC failure**. These machine-attributable shape failures are collectively referred to as **MEI (Machine Error Investigation) shape issues**.

### The Problem This Dashboard Solves

Before this dashboard, the entire correction tracking workflow was **manual and Excel-driven**:

- **QC fail data** was exported weekly from Zoho as large `.xlsx` files (up to 500,000 rows each), covering two consecutive periods (Period A and Period B).
- **Physical corrections** — when a technician physically re-adjusted a machine — were logged by hand across **20+ sheets** in a separate Excel workbook ("MEI SHAPE CORRECTION.xlsx"), with inconsistent column names, free-text issue descriptions, and varying date formats per sheet.
- To determine whether a correction actually worked, someone had to **manually cross-reference** the correction log against the next week's QC data to see if the same PID (Product ID) failed again.
- **Reason strings were inconsistent** across datasets — e.g., "W/SHAPE", "WRONG SHAPE", "Wrong shape cut by machine" all meant the same thing but appeared differently. There was no automated way to group them.
- There was **no visibility** into which machines were the worst offenders, which shifts had the most failures, or what the overall correction success rate was.

### What This Dashboard Provides

This dashboard **automates the entire workflow end-to-end**:

1. **Automated data ingestion** — Reads both QC exports and the 20-sheet correction logbook, normalizes messy data, and cross-references everything automatically.
2. **Fuzzy string matching** — Uses RapidFuzz to cluster inconsistent reason strings (e.g., "W/SHAPE" ≈ "WRONG SHAPE") so analysis isn't broken by free-text inconsistencies.
3. **PID classification** — Automatically classifies every failed PID into Corrected, Recurred, Pending, or Corrected-unlogged by comparing Period A failures against the correction log and Period B outcomes.
4. **Root cause analytics** — Identifies which machines fail the most, which shape issues dominate (Pareto), which shifts have higher defect rates, and whether corrections are actually effective.
5. **Single PID drill-down** — Lets QC leads look up any PID or Invoice and instantly see its full failure history, every correction attempt, before/after lens dimensions, and current status.
6. **Manual correction logging** — Provides a form to log new physical corrections directly from the browser, which get folded into the analysis pipeline immediately.
7. **Data explorer** — Gives full browsable, searchable, sortable access to raw QC fails, correction log entries, PID classifications, and fuzzy clusters for auditing.

In short: **what used to take hours of manual Excel cross-referencing now loads in seconds as an interactive, live dashboard.**

---

## 2. Technical Summary

This project replaces a **manual Excel-based workflow** for tracking MEI lens shape correction issues with a **fully automated, live web dashboard**. It ingests raw QC data exports and a physical correction logbook, cross-references them, and produces interactive analytics and a searchable data explorer — all served from a single `localhost:8000` URL.

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                       Browser (Frontend)                  │
│   index.html  ·  styles.css  ·  app.js  ·  Plotly.js     │
└──────────────────────┬───────────────────────────────────┘
                       │  REST API (JSON)
┌──────────────────────▼───────────────────────────────────┐
│                   FastAPI Backend                          │
│   main.py  — routes, uploads, CORS, static file serving   │
│   analyzer.py  — MEIAnalyzer class (data pipeline + API)  │
└──────────────────────┬───────────────────────────────────┘
                       │  pandas / openpyxl / calamine
┌──────────────────────▼───────────────────────────────────┐
│                    Data Sources                            │
│  QC Raw Data-2.xlsx   (Period A — past week QC export)    │
│  QC Raw Data-3.xlsx   (Period B — current week QC export) │
│  MEI SHAPE CORRECTION.xlsx  (20-sheet correction logbook) │
│  data/manual_corrections.json  (user-entered corrections) │
└──────────────────────────────────────────────────────────┘
```

| Layer | Tech |
|---|---|
| Backend | Python 3, FastAPI, Uvicorn, pandas, openpyxl, python-calamine, rapidfuzz |
| Frontend | Vanilla HTML/CSS/JS, Plotly.js for charts, Google Fonts (Inter, Outfit) |
| Data | Excel `.xlsx` files + local JSON file for manual entries |

---

## 4. Data Pipeline (What `analyzer.py` Does)

### 3.1 Data Loading (`_load_data`)
1. **Reads two QC Raw Data exports** (Period A & B) using the `calamine` engine for speed.
2. Parses date-range headers from row 1 to auto-label each period (e.g., "Wk 7/28/2026 – 8/3/2026").
3. **Filters to lens items only** (`RIGHTLENS` / `LEFTLENS`), excluding frames and sunglasses.
4. Keeps rows that are either `QCPassed` or `QCFailed` with a machine-attributable shape reason.
5. Derives shift buckets (Morning / Evening / Night) from `QC_created_date` timestamps.
6. Flags a **500k row cap warning** if any dataset hits exactly 500,000 rows (Zoho export ceiling).

### 3.2 Correction Log Ingestion
1. Reads the 20-sheet physical correction logbook, dynamically discovering PID, date, issue, and dimension columns per sheet.
2. Normalizes raw issue strings (e.g., "W/SHAPE" → "WRONG SHAPE", "SMALL SIZE" → "SMALL") via `_normalize_correction_issue()`.
3. Excludes non-shape entries like CHIP, SCRATCH, POWER, COATING, etc.
4. Merges user-submitted manual corrections from `data/manual_corrections.json`.

### 3.3 Fuzzy String Clustering (`_cluster_reasons`)
- Uses **RapidFuzz** (threshold ≥ 85% similarity) with Union-Find to cluster all raw reason strings from both QC data and correction logs.
- Tags clusters matching known MEI reasons (≥ 80% fuzzy match) as machine-attributable.
- Enables consistent grouping despite inconsistent free-text reasons across datasets.

### 3.4 Classification Logic (`analyze`)
For every unique PID that failed in Period A with a machine-attributable reason:

| Classification | Condition |
|---|---|
| **Corrected** | Has a correction entry AND did NOT fail again in Period B |
| **Recurred** | Has a correction entry BUT still failed in Period B |
| **Pending** | No correction logged AND still failing in Period B |
| **Corrected-unlogged** | No correction logged BUT did NOT fail in Period B (likely fixed informally) |

### 3.5 Analytical Outputs
- **MEI Shape Fail Rate** = MEI failure events / total QC Done (both pass + fail)
- **Event-based Pareto** — failure events bucketed by shape type (SMALL / BIG / WRONG SHAPE / SLIP)
- **Machine Problem Table** — per-machine: total failures, machine-specific fail rate, top issue, recurrence count
- **Machine × Issue Heatmap** — crosstab of machines vs. failure reasons
- **Shift Defect Drift** — failures distributed across Morning / Evening / Night shifts
- **Correction Effectiveness** — pie/donut of Corrected / Recurred / Pending / Corrected-unlogged

---

## 5. API Endpoints

### Analytics
| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/status` | Active dataset dates, row cap warning |
| `GET` | `/api/metrics` | Full analytics payload (KPIs, charts, classified PIDs) |
| `POST` | `/api/drilldown` | Drill into filtered PID lists by category |
| `GET` | `/api/export_csv` | Download classified PIDs as CSV |

### Data Explorer
| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/explorer/pid/{pid}` | Single PID history — fails + corrections side-by-side |
| `GET` | `/api/explorer/classifications` | Paginated full classification table (sortable, filterable) |
| `GET` | `/api/explorer/clusters` | RapidFuzz cluster inspector (all clusters + members) |
| `GET` | `/api/explorer/fails` | Paginated raw QC fail rows |
| `GET` | `/api/explorer/corrections` | Paginated correction log entries |

### Manual Corrections
| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/manual_corrections` | List all user-entered corrections |
| `POST` | `/api/manual_corrections` | Create/update a manual correction entry |
| `DELETE` | `/api/manual_corrections/{id}` | Delete a manual correction entry |

### Data Upload
| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/upload/period_a` | Upload new Period A Excel file |
| `POST` | `/api/upload/period_b` | Upload new Period B Excel file |

---

## 6. Frontend — Two Main Views

### 5.1 📊 Analytics Dashboard
- **PID Search Bar** — quick lookup by PID or Invoice number, plus a "Log Correction" button.
- **Period Banner** — shows the active Period A → Period B date ranges.
- **4 KPI Cards** — MEI Shape Fail Rate, Machine Failures, Recurred, Pending.
- **5 Interactive Charts** (Plotly.js):
  1. Shape Failure Pareto (bar + cumulative line)
  2. Machine Problem Table (clickable rows for drill-down)
  3. Machine × Issue Heatmap
  4. Correction Effectiveness (donut chart)
  5. Shift Defect Drift (grouped bar)
- **Upload Section** — drag-and-drop or click to upload new Period A / B Excel files without restarting.

### 5.2 🔍 Audit / Data Explorer
Five sub-views accessible via pill navigation:

| Sub-View | What It Shows |
|---|---|
| **PID Lookup** | Enter a PID or Invoice → see QC fail history + correction history side-by-side, with before/after lens dimensions and precision shift deltas |
| **Classification Table** | All classified PIDs with sorting, search, pagination, and status filters |
| **RapidFuzz Clusters** | Every discovered fuzzy cluster, its canonical label, MEI tag, total count, and all raw strings merged into it |
| **Raw QC Fails** | Browsable table of all QC failure rows across both periods |
| **Correction Log** | Browsable table of all physical correction entries from the 20-sheet logbook |

### 5.3 Manual Correction Entry
- A modal form accessible from both the Dashboard and Data Explorer.
- Lets users log corrections with: PID, done-by, timestamp, issue type, before/after dimensions (A, B, CIRC R, CIRC L), and notes.
- Entries persist to `data/manual_corrections.json` and are automatically folded into the analysis pipeline on save.

---

## 7. Key Design Decisions

1. **Event-level vs. PID-level counting** — Pareto and fail-rate KPIs count *failure events* (rows), not unique PIDs, to accurately reflect volume. Classification (Corrected/Recurred/Pending) operates on unique PIDs.
2. **Only machine-attributable reasons** — Fitter-related reasons are excluded; the dashboard focuses purely on MEI shape issues (SMALL, BIG, WRONG SHAPE, SLIP, POP OUT, CHIP during fitting).
3. **Correction log normalization** — Free-text entries like "W/SHAPE", "SMALL SIZE", "BIG" are mapped to standard buckets. Non-shape entries (SCRATCH, POWER, COATING, etc.) are filtered out.
4. **Fuzzy clustering with RapidFuzz** — Handles the inconsistency of manually entered reasons across 20+ sheets and two QC data exports.
5. **No database** — The system is intentionally file-based (Excel + JSON) to match the existing operational workflow and avoid infrastructure overhead.

---

## 8. How to Run

```bash
cd projeect/
./run.sh
# Opens at http://localhost:8000
```

The startup script:
1. Checks for Python 3 availability
2. Auto-installs missing dependencies (pandas, openpyxl, fastapi, uvicorn, python-calamine, python-multipart, rapidfuzz)
3. Starts the FastAPI server with hot-reload enabled

---

## 9. File Structure

```
projeect/
├── run.sh                          # One-command startup script
├── README.md                       # Quick-reference README
├── DOCUMENTATION.md                # This file
├── QC Raw Data-2.xlsx              # Period A — default QC export
├── QC Raw Data-3.xlsx              # Period B — default QC export
├── backend/
│   ├── main.py                     # FastAPI app, routes, file uploads
│   └── analyzer.py                 # MEIAnalyzer — full data pipeline + explorer APIs
├── frontend/
│   ├── index.html                  # Dashboard + Data Explorer UI
│   ├── styles.css                  # Glassmorphism dark theme styling
│   └── app.js                      # Frontend logic, API calls, chart rendering
├── data/
│   ├── manual_corrections.json     # User-entered correction entries (persisted)
│   └── manual_corrections_old.json # Backup/old corrections
└── debug_*.py                      # Debug scripts used during development
```

---

## 10. Debug Scripts

Several one-off debug scripts were created during development to inspect data issues:

| Script | Purpose |
|---|---|
| `debug_cols.py` | Inspect column names in the QC Excel exports |
| `debug_fails.py` | Debug QC fail filtering and reason matching |
| `debug_frame.py` | Debug DataFrame structure after loading |
| `debug_pid.py` | Debug PID parsing and matching logic |
| `debug_row.py` | Inspect raw row data |
| `debug_types.py` | Check column data types and value distributions |
