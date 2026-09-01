# Phasewise Implementation Plan - MEI E2 Analytics & Escalation Logging Dashboard

This document outlines the step-by-step **Phasewise Execution Plan** for building the web-based **MEI E2 Escalation Logging & Analytics Dashboard**.

---

## 🎯 Architecture & Layout Summary

### 2-Tab Layout Architecture
- **Tab 1: Escalation Entries**: Operator & shop-floor interface for Tray ID scanning, live DB auto-fill, rapid logging form, and active log table with 1-click Excel/CSV export.
- **Tab 2: Analysis & Trends**: Supervisor & management interface for KPI scorecards, failure scope donut charts, top defect bar charts, and shift breakdown analytics.

### Pure MySQL Connection & Storage
- **Live Data Lookup**: Connects via local proxy (`127.0.0.1:13306`) to query `wms.tray_monitoring`, `wms.order_items`, `wms.fitting_detail`, and `wms.power` in < 10ms.
- **Escalation Records Storage**: Stores all logged escalations directly in MySQL table `wms_e2_escalations`.

---

## 🚀 Phasewise Execution Plan

### 📌 Phase 1: Database Setup & Backend Core Infrastructure (`app.py`)
**Goal**: Build the Flask backend, MySQL connection pool, and REST API endpoints.

- [x] **1.1. Create Logging Table in MySQL (`wms_e2_escalations`)**:
  - Auto-create table `wms_e2_escalations` / persistent storage in MySQL.
  - Columns: `id`, `entry_date`, `entry_time`, `shift`, `shift_ic`, `operator`, `tray_id`, `fitting_id`, `order_id`, `jit_status`, `cut_status`, `frame_pid`, `right_lens_barcode`, `left_lens_barcode`, `lens_index`, `sph`, `cyl`, `axis`, `addn`, `fail_category`, `issue`, `status`, `machine`, `created_at`.

- [x] **1.2. Implement Live SQL Lookup Endpoint (`GET /api/lookup/<tray_id>`)**:
  - Execute 3-step indexed MySQL query (< 10ms execution).
  - Return JSON payload: `fitting_id`, `order_id`, `frame_pid`, `right_lens_barcode`, `left_lens_barcode`, `lens_index`, `sph`, `cyl`, `axis`, `addn`, `lens_name`.

- [x] **1.3. Implement Escalation Entry Submission Endpoint (`POST /api/escalations`)**:
  - Validate and insert escalation entry into MySQL database `wms_e2_escalations`.
  - Auto-assign current timestamp and production shift (`Shift A`, `Shift B`, `Shift C`).

- [x] **1.4. Implement Real-Time Analytics Endpoint (`GET /api/analytics`)**:
  - Calculate total daily/shift count, NG ratio %, failure scope distribution (% Left Lens, % Right Lens, % Both Lens, % All Items), and top defect causes ranking.

- [x] **1.5. Implement 1-Click Excel & CSV Export Endpoints (`GET /api/export/excel`, `GET /api/export/csv`)**:
  - Build `.xlsx` workbook using `openpyxl` formatted identically to sheet `E2 Escalation` in `E2 escalation (1).xlsx`.
  - Build raw `.csv` download stream.

---

### 🎨 Phase 2: Frontend UI Layout & Design System (`templates/index.html`, `static/style.css`)
**Goal**: Create modern dark-mode UI with glassmorphism cards and 2-tab navigation.

- [x] **2.1. Top Navigation & Status Bar**:
  - Logo, Live Shift badge (`Shift A`, `Shift B`, `Shift C`), current Operator, and DB Health Indicator (`🟢 MySQL Connected 8ms`).

- [x] **2.2. 2-Tab Navigation Bar**:
  - Navigation controls to switch seamlessly between `📝 Tab 1: Escalation Entries` and `📊 Tab 2: Analytics & Trends`.

- [x] **2.3. Tab 1 Components (Escalation Entries & Shop-Floor View)**:
  - **Focal Barcode Scanner Input**: High-visibility trigger input box with glowing barcode icon.
  - **Auto-Populated Live DB Details Card**: Glassmorphism card displaying Fitting ID, Order ID, Frame PID, Lens Barcodes, Lens Index badge, and Optical Powers.
  - **Escalation Logging Form**: Dropdowns for `Shift IC`, `E2 Operator`, `Fail Category`, `Issue`, `Status` (`NG`, `OK`, `RETURN TO JIT ASRS`), `Machine`.
  - **Active Data Table**: Searchable table displaying logged entries with 1-Click **`[ 📥 EXPORT AS .XLSX ]`** and **`[ 📄 EXPORT AS .CSV ]`** buttons.

- [x] **2.4. Tab 2 Components (Analytics & Management View)**:
  - **4 Top KPI Scorecards**: Total Today, NG %, Top Defect Cause, Active Shift Volume.
  - **Interactive Chart Containers**: Canvas containers for Donut Chart (Failure Scope) and Horizontal Bar Chart (Top Issues).
  - **Operator & Shift Volume Breakdown Table**: Summary table grouped by Shift and Machine Operator.

---

### ⚡ Phase 3: Client Interactivity, Barcode Scanner & Chart.js (`static/app.js`)
**Goal**: Wire up client-side logic, scanner debouncing, AJAX API calls, and charts.

- [ ] **3.1. Handheld Barcode Scanner Handler**:
  - Auto-capture scanner input on `Enter` keypress or paste.
  - Trigger debounced AJAX fetch to `/api/lookup/<tray_id>`.

- [ ] **3.2. Live Data Card Auto-Fill**:
  - Fill DB details card in < 10ms with smooth fade-in animation.
  - Handle missing/not-found trays gracefully with clear alert badges.

- [ ] **3.3. Form Submission & Table Live Refresh**:
  - Submit form via AJAX to `/api/escalations`.
  - Append new row to log table instantly with status pill badges (`NG` red, `OK` green, `ASRS` amber).

- [ ] **3.4. Chart.js Data Visualizations**:
  - Initialize Donut Chart for Failure Scope distribution (`LEFT LENS`, `RIGHT LENS`, `BOTH LENS`, `ALL ITEMS`).
  - Initialize Horizontal Bar Chart for Top 5 Defect Causes.
  - Auto-refresh charts when new escalations are logged.

- [ ] **3.5. 1-Click Export Handlers**:
  - Connect export buttons to `/api/export/excel` and `/api/export/csv` endpoints for instant file download.

---

### 🛡️ Phase 4: 24/7 Availability & Auto-Reconnect Daemon
**Goal**: Ensure zero-downtime 24/7 continuous operation on shop floor.

- [x] **4.1. Automatic Port 13306 Health Monitoring**:
  - Python background monitor checks port `13306` socket health before executing queries.
  - Gracefully alerts user if `adaptive connect` tunnel is offline so they can start it manually (Auto-spawn removed to prevent proxy crashes).

- [x] **4.2. Strict Short-Lived Connections**:
  - Use `get_fresh_db_connection()` for every query and strictly `conn.close()` inside a `finally` block to prevent persistent connection pipe crashes in Adaptive Zero-Trust proxy.

---

### 🧪 Phase 5: Verification & End-to-End Testing
**Goal**: Validate full system workflow, performance, and template alignment.

- [ ] **5.1. Live Scan Test**:
  - Scan Tray ID `CT18518` and verify live DB details card auto-fills in < 10ms with Fitting ID `987349684`, Barcodes, and Lens Index `1.56`.

- [ ] **5.2. Escalation Logging & MySQL Verification**:
  - Log test escalation entries and verify direct insertion into MySQL table `wms_e2_escalations`.

- [ ] **5.3. Analytics Dashboard Verification**:
  - Switch to Tab 2 and verify real-time update of Donut chart, Bar chart, and KPI scorecards.

- [ ] **5.4. Excel Export Header Alignment**:
  - Click **Export to Excel** and verify downloaded `.xlsx` file matches sheet `E2 Escalation` in `E2 escalation (1).xlsx` header for header.
