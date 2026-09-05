# MEI E2 Analytics & Escalation Logging Architecture

This document provides a comprehensive technical architectural specification for the **MEI E2 Escalation Logging & Analytics System**.

---

## 🏗️ System Architecture Overview

```
+---------------------------------------------------------------------------------------------------+
|                                 SHOP-FLOOR OPERATOR INTERFACE                                      |
|                                                                                                   |
|  [ Handheld USB Barcode Scanner ] ---->  [ Modern Web Dashboard (Browser) ]                       |
|                                           |-- Tab 1: Escalation Entries                           |
|                                           |-- Tab 2: Analytics & Trends                           |
+-------------------------------------------|-------------------------------------------------------+
                                            | (HTTP / REST API)
                                            v
+---------------------------------------------------------------------------------------------------+
|                                     FLASK BACKEND SERVER                                          |
|                                                                                                   |
|  [ Flask Web App (Python) ]                                                                       |
|            |                                                                                      |
|            | (Internal TCP Socket / localhost:13306)                                              |
|            v                                                                                      |
|  [ Adaptive Access Proxy Session ] (adaptive connect mysql_ro_nexs-slave02.prod.internal2 -p 13306)  |
+------------|--------------------------------------------------------------------------------------+
             | (Encrypted TLS Tunnel)
             v
+---------------------------------------------------------------------------------------------------+
|                                       MYSQL DATABASE (wms / app)                                  |
|                                                                                                   |
|  LOOKUP TABLES (Live Fetch < 10ms):                                                               |
|  1. wms.order_items      --> Primary Active Location Check (location_id -> fitting_id)            |
|  2. wms.tray_monitoring  --> Historical Fallback Ledger (tray_id -> wms_fitting_id)               |
|  3. wms.order_items      --> Item Lookup (fitting_id -> product_id, barcode, fitting_type)        |
|  4. wms.fitting_detail   --> Order Link (fitting_id -> order_id)                                  |
|  5. wms.power            --> Optical Powers & Lens Index (order_id -> lens_index, SPH, CYL, etc.) |
|                                                                                                   |
|  LOGGING TABLE (Escalation Records):                                                              |
|  5. wms_e2_escalations   --> Stores all logged escalations & analytics data in MySQL            |
+---------------------------------------------------------------------------------------------------+
```

---

## 🎨 Frontend UI Architecture (2-Tab Layout)

The web client is structured as a responsive single-page web application (SPA) with **2 primary tabs**:

```mermaid
graph TD
    A[Top Header Bar: Logo, Shift Status, Operator, DB Health Indicator] --> B[Tab Controls]
    B --> C[Tab 1: Escalation Logging & Entries]
    B --> D[Tab 2: Analytics & Trends]

    C --> C1[Scanner Card: Focal Tray ID Input]
    C --> C2[Live Auto-Fetched DB Card: Fitting ID, Barcodes, Lens Index, Powers]
    C --> C3[Escalation Form: Fail Category, Issue, Status, Machine]
    C --> C4[Logged Entries Grid: Live Search, Column Sort, Excel/CSV Export Buttons]

    D --> D1[KPI Scorecards: Total Today, NG Ratio %, Top Defect]
    D --> D2[Donut Chart: Failure Scope Breakdown]
    D --> D3[Bar Chart: Top Defect Issues Ranking]
    D --> D4[Table: Operator & Shift Volume Analysis]
```

### Component Details
1. **Top Navigation & Status Bar**:
   - Displays real-time database status (`🟢 MySQL Connected (8ms)`).
   - Auto-detects current shift (**Shift A**, **Shift B**, **Shift C**).
2. **Tab 1 — Escalation Logging & Entries**:
   - **Barcode Trigger**: Auto-submits query on scanner `Enter` keypress or input paste.
   - **Auto-Fill Card**: Displays `Fitting ID`, `Order ID`, `Frame PID`, `Right Lens Barcode`, `Left Lens Barcode`, `Lens Index` (`1.56`, `1.60`, etc.), `Lens Name`, and `Optical Powers` (`SPH`, `CYL`, `AXIS`, `ADDN`).
   - **Form Submission**: Submits escalation log directly to MySQL database and updates the table instantly.
   - **Export Controls**: 1-Click **`Export as .XLSX`** (matches `E2 Escalation` Excel template) and **`Export as .CSV`**.
3. **Tab 2 — Analytics & Trends**:
   - **Interactive Charts**: Rendered using Chart.js with dark-mode styling.
   - **Date & Shift Filters**: Filter quality metrics across custom date ranges and production shifts.

---

## ⚡ Data Flow & Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Operator
    participant UI as Web Dashboard (Frontend)
    participant Flask as Flask Server (Backend)
    participant Proxy as Adaptive Proxy (port 13306)
    participant MySQL as MySQL Database (wms)

    Note over Operator, UI: Step 1: Scan Tray ID
    Operator->>UI: Scans / Types Tray ID (e.g. CT18518)
    UI->>Flask: GET /api/lookup/CT18518
    Flask->>Proxy: Check localhost:13306 socket (150ms timeout)
    alt Socket Closed
        Flask-->>UI: ⚠️ Terminal Tunnel Offline (User manually runs `adaptive connect`)
    end
    
    Flask->>MySQL: 1a. SELECT fitting_id FROM wms.order_items WHERE location_id='CT18518'
    MySQL-->>Flask: Returns fitting_id=985621562 (< 2ms) (If None, fallbacks to wms.tray_monitoring)
    Flask->>MySQL: 2. SELECT order_items & fitting_detail order_id WHERE fitting_id=985621562
    MySQL-->>Flask: Returns items & order_id=742782924 (< 3ms)
    Flask->>MySQL: 3. SELECT lens_index, sph, cyl, axis, ap FROM wms.power WHERE order_id=742782924
    MySQL-->>Flask: Returns optical powers & lens details (< 2ms)
    
    Flask-->>UI: JSON Payload (Tray, Fitting ID, PIDs, Barcodes, Index, Powers) [< 10ms Total]
    UI->>UI: Auto-populate Live DB Card & Form Fields

    Note over Operator, UI: Step 2: Log Escalation Entry
    Operator->>UI: Selects Fail Category, Issue, Status & Clicks "Log Escalation"
    UI->>Flask: POST /api/escalations (Form Data)
    Flask->>MySQL: INSERT INTO wms_e2_escalations (entry_date, entry_time, shift, tray_id, fitting_id...)
    MySQL-->>Flask: Success
    Flask-->>UI: 201 Created (New Entry JSON)
    UI->>UI: Refresh Log Table & Update Analytics Charts
```

---

## 🗄️ MySQL Database Schemas

### 1. Live Lookup Tables (`wms`)
* **`wms.tray_monitoring`**: `tray_id` (VARCHAR), `wms_fitting_id` (BIGINT)
* **`wms.order_items`**: `fitting_id` (BIGINT), `product_id` (INT), `barcode` (VARCHAR), `fitting_type` (ENUM: `FRAME`, `RIGHTLENS`, `LEFTLENS`, `REQD`, `NOT_REQD`)
* **`wms.fitting_detail`**: `fitting_id` (BIGINT), `order_id` (INT)
* **`wms.power`**: `order_id` (INT, Indexed PK), `product_id` (INT), `lens_index` (DOUBLE), `sph` (VARCHAR), `cyl` (VARCHAR), `axis` (VARCHAR), `ap` (VARCHAR), `lensname` (VARCHAR)

### 2. Escalation Logging MySQL Schema
Table: **`wms_e2_escalations`** (Stores all logged escalation records in MySQL)

| Column Name | MySQL Data Type | Description |
| :--- | :--- | :--- |
| `id` | BIGINT AUTO_INCREMENT PRIMARY KEY | Unique record ID |
| `entry_date` | DATE | Entry Date (`YYYY-MM-DD`) |
| `entry_time` | TIME | Entry Time (`HH:MM:SS`) |
| `shift` | VARCHAR(10) | Production Shift (`Shift A`, `Shift B`, `Shift C`) |
| `shift_ic` | VARCHAR(50) | Shift In-Charge Supervisor |
| `operator` | VARCHAR(50) | E2 Machine Operator |
| `tray_id` | VARCHAR(30) | Unique Tray ID scanned |
| `fitting_id` | VARCHAR(30) | Auto-fetched Fitting ID |
| `order_id` | VARCHAR(30) | Auto-fetched Order ID |
| `jit_status` | VARCHAR(20) | Classification (`JIT`, `NON JIT`) |
| `cut_status` | VARCHAR(20) | Lens Status (`CUT`, `UNCUT`) |
| `frame_pid` | VARCHAR(30) | Required Frame PID |
| `right_lens_barcode` | VARCHAR(50) | Required Right Lens Barcode |
| `left_lens_barcode` | VARCHAR(50) | Required Left Lens Barcode |
| `lens_index` | VARCHAR(10) | Optical Lens Index (`1.56`, `1.60`, etc.) |
| `sph` | VARCHAR(10) | Prescription Sphere Power |
| `cyl` | VARCHAR(10) | Prescription Cylinder Power |
| `axis` | VARCHAR(10) | Prescription Axis Angle |
| `addn` | VARCHAR(10) | Prescription Addition Power |
| `fail_category` | VARCHAR(30) | Scope (`LEFT LENS`, `RIGHT LENS`, `BOTH LENS`, `ALL ITEMS`) |
| `issue` | VARCHAR(100) | Defect Cause (`WRONG PICKING`, `WRONG POWER SPH`, etc.) |
| `status` | VARCHAR(30) | Result (`NG`, `OK`, `RETURN TO JIT ASRS`) |
| `machine` | VARCHAR(30) | Machine Tag / Identifier |
| `created_at` | DATETIME | Timestamp of entry creation |

---

## 🛡️ 24/7 Availability & Resilience Architecture

1. **Automatic Port 13306 Health Monitoring & Threading Limits**:
   - Python checks port `13306` socket before executing live DB queries.
   - If port `13306` is disconnected, Python automatically launches `adaptive connect mysql_ro_nexs-slave02.prod.internal2 -p 13306` in a background daemon thread.
   - Global `threading.Lock()` ensures the PyMySQL connection is thread-safe across concurrent scans.
2. **Non-Blocking Query Capping (DoS Prevention)**:
   - Queries strictly use `connect_timeout=3`, `read_timeout=4`, and `write_timeout=3` to guarantee that silent proxy network drops never deadlock the UI thread.
3. **1-Click Excel Export Compatibility**:
   - The export module utilizes `openpyxl` to build `.xlsx` workbooks formatted identically to `E2 escalation (1).xlsx`.
