# MEI E2 Analytics & Escalation Logging Context

## 🎯 Project Objective
The objective of this project is to replace manual Excel-based record-keeping with a digital logging and analytics dashboard for **MEI E2 Machine Escalations**.

The active template file for this project is **`E2 escalation (1).xlsx`** (specifically the sheet named **`E2 Escalation`**). Note that an additional sheet named `OMT` is present in the template for future functionality.

The system enables production shop-floor operators and supervisors to:
1. **Live SQL Database Auto-Fetch**: Automatically query the live `wms` MySQL database when a **`TRAY ID`** is scanned or entered, performing real-time indexed queries utilizing a **2-Step Live Priority Check**: first checking `wms.order_items` for active location mapping, and falling back to `wms.tray_monitoring`. It securely fetches `FITTING ID`, `ORDER ID`, `REQ. FRAME PID`, `REQ. RIGHT LENS BARCODE`, `REQ. LEFT LENS BARCODE`, `LENS INDEX` (`1.56`, `1.60`, etc.), and **SEPARATE Optical Powers for BOTH Right Lens & Left Lens** (`SPH`, `CYL`, `AXIS`, `ADDN`) in under 10 milliseconds. Empty/discarded ghost trays are instantly rejected.
2. **Dynamic Failed Item Barcode Recording**: Automatically display dynamic barcode input entry boxes based on the selected **`FAIL CATEGORY`**:
   - `LEFT LENS` ➔ `FAILED LEFT LENS BARCODE (RECEIVED)`
   - `RIGHT LENS` ➔ `FAILED RIGHT LENS BARCODE (RECEIVED)`
   - `BOTH LENS` ➔ `RECEIVED RIGHT LENS BARCODE` & `RECEIVED LEFT LENS BARCODE`
   - `ALL ITEMS` ➔ `RECEIVED FRAME PID`, `RECEIVED RIGHT LENS BARCODE`, & `RECEIVED LEFT LENS BARCODE`
3. **Log Escalations Rapidly**: Streamlined digital entry interface with auto-timestamps, smart defaults, autocompletion, and validation.
4. **Pure MySQL Storage**: Store all historical and new escalation entries directly in a dedicated MySQL table (`wms_e2_escalations`) following the exact structure defined in `E2 escalation (1).xlsx`.
5. **1-Click Export (.XLSX / .CSV)**: Export all logged entries or filtered datasets into `.xlsx` (matching `E2 Escalation` sheet format) or `.csv` with a single click.
6. **Analyze Escalation Trends Effortlessly**: Gain immediate visibility into escalation patterns, shift-wise breakdowns, failure categories, and issue causes.

---

## 🖥️ User Interface Architecture (2-Tab Layout)

The web dashboard is organized into **2 dedicated tabs** for optimal workflow separation:

```
+---------------------------------------------------------------------------------------+
|  TOP HEADER BAR                                                                       |
|  [Logo] MEI E2 Escalation System | Shift: Shift A | Operator: PRACHI | DB: 🟢 Connected  |
|                                                                                       |
|  [ 📝 TAB 1: ESCALATION LOGGING & ENTRIES ]   [ 📊 TAB 2: ANALYTICS & TRENDS ]        |
+---------------------------------------------------------------------------------------+
```

### 📝 Tab 1: Escalation Logging & Entries (Operator & Shop-Floor View)
Dedicated to rapid data entry, live data inspection, and data export:
* **Barcode / Tray ID Scanner**: High-visibility trigger input field for fast USB scanner input.
* **Auto-Fetched Live DB Card**: Instant display (< 10ms) showing:
  * `Fitting ID` & `Order ID`
  * `Req. Frame PID` & `Frame Barcode`
  * `Req. Right Lens Barcode` & `Req. Left Lens Barcode`
  * `Lens Index` (`1.56`, `1.60`, `1.67`, `1.74`) & `Lens Name`
  * **Dual Lens Optical Powers**: Dedicated rows for **Right Lens (R)** and **Left Lens (L)** (`SPH`, `CYL`, `AXIS`, `ADDN`).
* **Rapid Escalation Form**:
  * Dropdowns for `Shift IC`, `E2 Operator`, `Fail Category`, `Issue`, `Status` (`NG`, `OK`, `RETURN TO JIT ASRS`).
  * **Dynamic Failed Item Barcode Input Boxes**: Contextual input boxes rendered automatically based on selected `Fail Category`.
  * Primary `[ LOG ESCALATION ENTRY ]` submission button.
* **Escalation Data Table Toolbar**:
  * Live search bar & column filters (Tray ID, Operator, Shift, Status, Date).
  * **🟢 `[ 📥 EXPORT AS .XLSX ]` Button**: Downloads complete formatted Excel workbook matching `E2 Escalation` sheet.
  * **🔵 `[ 📄 EXPORT AS .CSV ]` Button**: Downloads raw CSV dataset for custom analysis.

### 📊 Tab 2: Analytics & Trends (Supervisor & Management View)
Dedicated to production metrics and quality analysis:
* **Top KPI Scorecards**:
  * Total Escalations Count (Daily / Shift-wise)
  * NG Defect Rate (%)
  * Top Defect Cause
  * Active Shift Volume
* **Interactive Visualizations (Chart.js)**:
  * **Failure Scope Breakdown (Donut Chart)**: Visualizing proportional distribution across `LEFT LENS`, `RIGHT LENS`, `BOTH LENS`, and `ALL ITEMS`.
  * **Top 5 Defect Causes Ranking (Horizontal Bar Chart)**: Ranking primary failure reasons (`WRONG PICKING`, `WRONG POWER SPH`, `MACHINE - LENS BROKEN`, etc.).

---

## 📄 Excel Template Structure & Mapping

The application outputs exports matching **`E2 escalation (1).xlsx`** (`E2 Escalation` sheet):

| Header Column | Source Field / Logic | Example Value |
| :--- | :--- | :--- |
| **Date** | System Date (`YYYY-MM-DD`) | `2026-08-25` |
| **TIME** | System Time (`HH:MM:SS`) | `14:32:05` |
| **SHIFT** | Auto-calculated from time (`Shift A`, `Shift B`, `Shift C`) | `Shift A` |
| **SHIFT IC** | Supervisor Dropdown | `ADITI` |
| **E2 OP** | E2 Machine Operator Dropdown | `PRACHI` |
| **TRAY ID** | Scanned Barcode Input | `CT18518` |
| **FITTING ID** | Live SQL Lookup (`wms.tray_monitoring.wms_fitting_id`) | `982229724` |
| **JIT/NOT JIT** | Auto-derived / Selected | `JIT` |
| **CUT/UNCUT** | Auto-derived / Selected | `UNCUT` |
| **REQ. FRAME PID** | Live SQL Lookup (`wms.order_items` where `item_type = 'FRAME'`) | `227035` |
| **REQ. RIGHT LENS BARCODE** | Live SQL Lookup (`wms.order_items` where `item_type = 'RIGHTLENS'`) | `AAA057108556` |
| **REQ. LEFT LENS BARCODE** | Live SQL Lookup (`wms.order_items` where `item_type = 'LEFTLENS'`) | `AAA057108555` |
| **LENS INDEX** | Live SQL Lookup (`wms.power.lens_index`) | `1.74` |
| **SPH** | Live SQL Lookup (`wms.power.sph`) | `-13.0` |
| **CYL** | Live SQL Lookup (`wms.power.cyl`) | `-6.0` |
| **AXIS** | Live SQL Lookup (`wms.power.axis`) | `165` |
| **ADDN** | Live SQL Lookup (`wms.power.ap`) | `0.00` |
| **FAIL CATEGORY** | Dropdown (`LEFT LENS`, `RIGHT LENS`, `BOTH LENS`, `ALL ITEMS`) | `LEFT LENS` |
| **ISSUE** | Primary Issue Dropdown (`WRONG PICKING`, etc.) | `WRONG PICKING` |
| **STATUS** | Status Dropdown (`NG`, `OK`, `RETURN TO JIT ASRS`) | `NG` |
| **MACHINE** | Machine Identification Tag | `E2-01` |
