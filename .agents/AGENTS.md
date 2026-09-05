# MEI E2 System - Permanent Immutable Backend Directives

> **CRITICAL MANDATE**: The backend configuration, database socket protocol, and thread-safety rules in this repository are **FINAL AND IMMUTABLE**. No AI agent or automated script may alter, refactor, or revert these core backend rules under any circumstances.

---

## ⚠️ MANDATORY SESSION-START CHECKLIST (Read BEFORE touching any file)

Before making ANY change, every agent session MUST confirm:

1. ✅ **DO NOT run `git checkout`, `git reset`, or `git restore` on any file** — this repo has 1 commit and will destroy ALL user's work permanently (Rule 12).
2. ✅ **DO NOT run background ping threads** — crashes adaptive.exe (Rule 1).
3. ✅ **DO NOT auto-spawn adaptive.exe via subprocess** — kills user terminal (Rule 2).
4. ✅ **ALWAYS check `fitting_id != 0` before querying `wms.order_items`** — unindexed 0 causes 25-30s table scan (Rule 4).
5. ✅ **DO NOT add fake defaults** — if DB has no data, show `--`. Do NOT default lens_index to `1.56`, do NOT default FR Tag from `oi_processing_type` (Rule 13).
6. ✅ **DO NOT re-run SQL lookup when user clicks Log Escalation** — lookup fires automatically on 7-char tray ID input only (Rule 14).
7. ✅ **When `wms_fitting_id = 0`, fall back to `espresso_fitting_id`** before returning 444 (Rule 15).

---

## 1. Frozen Core Backend Rules (DO NOT MODIFY)

### Rule 1: Adaptive Proxy Tunnel Stability (Silent Persistent Connection)
- `app.py` MUST use a SILENT global persistent MySQL connection (`GLOBAL_DB_CONN`) with `ping(reconnect=True)` during request time, but MUST NEVER run background keep-alive ping threads (e.g., `_db_keep_alive_daemon` sending `SELECT 1`).
- **Reason**: Polling sockets asynchronously via background threads breaks socket multiplexing in `adaptive.exe` (the local Zero-Trust TCP proxy), causing it to crash with `[WinError 10054]` and exit back to the command prompt. A silent idle connection is safe.

### Rule 2: NO Subprocess Auto-Spawning (`adaptive.exe`)
- `app.py` MUST NEVER execute `subprocess.Popen([ADAPTIVE_EXE, ...])` or auto-spawn background tunnel processes.
- **Reason**: Spawning competing background processes causes the proxy to force-close the user's interactive terminal session. `app.py` must strictly listen to local port `13306`.

### Rule 3: Unverified Password Guard
- `get_fresh_db_connection()` MUST NEVER attempt `pymysql.connect()` if `DYNAMIC_PASSWORD` is `None` or invalid.
- **Reason**: Sending stale or candidate passwords to port `13306` triggers MySQL Error 1045, which causes Adaptive's proxy daemon to security-kill the user's terminal window.

### Rule 4: The Unindexed `LEFT JOIN` Timeout Hazard
- NEVER execute queries using `LEFT JOIN wms.order_items oi ON oi.fitting_id = tm.wms_fitting_id` without first checking if `fitting_id` is valid.
- **Reason**: `wms.order_items` is unindexed for `0`. If a tray is unregistered (`fitting_id = 0`), MySQL performs a full table scan, causing a 25-30 second query hang that crashes the MySQL connection proxy.
- **Enforcement**: Always use the Optimized 2-Step Indexed Query method: 1) Query `wms.tray_monitoring` first to fast-fail if `fitting_id` is `0` or null. 2) Only then query `wms.order_items` separately (NOT via JOIN) with the verified `fitting_id`. 3) Query `wms.fitting_detail` separately with `LIMIT 1` for order_id only.
- **Reason for no JOIN**: The `LEFT JOIN wms.fitting_detail` adds 2-4 seconds to every query. Always keep them as separate small queries.

### Rule 5: Protecting Manual Website Entries (Clearing Data)
- When clearing imported Excel records, ALWAYS use `if not r.get('is_imported', False):` to filter and preserve manual records.
- **Reason**: Older manual entries may not have the explicit `is_imported: False` key attached. Using `is False` strictly would result in permanently deleting user's manually typed escalation entries along with the Excel dump.

### Rule 6: Stage 2 Power Query Isolation (No Batching)
- Stage 2 queries on `wms.power` by `product_id` MUST be split into **two strictly independent queries** with `LIMIT 1` (one for `right_lens_pid` and one for `left_lens_pid`).
- **Reason**: Using a single `IN (right_pid, left_pid)` query with `LIMIT 4` results in cross-contamination, as MySQL will return 4 arbitrary rows for just one of the PIDs (e.g. 0.0 power), completely missing the other PID. A `product_id` inherently dictates the power, so a single isolated query per PID guarantees the exact prescription is fetched.

### Rule 6b: Monitor Panel Data Joins (JIT & FR Tags)
- JIT status and FR Tags MUST be fetched from `nexs_dp.monitor_panel_data` (columns `jit_type` and `v3_fr_tag`).
- **CRITICAL**: The join MUST use `shipping_package_id` retrieved exclusively from `wms.order_items`. DO NOT join using `tray_id` and DO NOT join `wms.fitting_detail` (as older trays have missing fitting detail records).
- **JIT Mapping**: `jit_type == 'Lens Lab'` -> `AUTO`. `jit_type == 'EXTERNAL VENDOR'` -> `MANUAL`. Everything else (including NULL) -> `NO`.
- **No Fallback**: If `monitor_panel_data` has no entry for a tray's shipping_package_id, show `--` for FR Tag and `NO` for JIT. DO NOT fall back to `oi_processing_type` from `order_items` — that would show fake data.

---

## 2. Dashboard Service Scope

### Rule 7: Exclusive MEI E2 Dashboard Execution
- When the user asks to start "dashboard", ONLY start `python app.py` (MEI E2 Main Escalation Dashboard on Port 5000).
- DO NOT start the QA/QC dashboard (`QA/app.py`). The QA/QC project is completed and moved to `github_projects/QA`.

---

## 3. UI, Formatting & Edge Case Rules

### Rule 8: Excel US Locale Date Swap Anomaly (DD-MM-YYYY)
- **Symptom**: When importing Excel files in India, dates from the 1st to the 12th (e.g., `02-08-2026`) are incorrectly parsed into the database with swapped days and months (e.g., `08/02/2026` or February 8th).
- **Enforcement**: `parse_excel_date` explicitly intercepts parsed `datetime` objects and undoes the swap by formatting with `%m/%d/%Y` whenever `val_obj.day <= 12 and val_obj.month <= 12`. **DO NOT REMOVE THIS LOGIC**.

### Rule 9: Header Layout & Theme Toggle Stability
- **Flex Wrap**: The `<header>` and `.header-stats` MUST use `flex-wrap: wrap` instead of `nowrap`. Do not add long text labels to buttons in the header (like the Theme Toggle), as it will overflow horizontally on small screens.
- **Theme Button**: The Theme Toggle button MUST remain an icon (`☀️` or `🌙`) with a circular padding (`width: 32px; height: 32px; border-radius: 50%;`). Do not add text to it.
- **Dropdown Visibility (Light Mode)**: DO NOT hardcode `#fff` or `#111827` to `<select>` or `<option>` elements. Always use CSS variables (`var(--card-bg)` and `var(--text-main)`) so dropdown text doesn't turn completely invisible when the user switches to Light Mode.

### Rule 10: Tab Persistence
- The UI MUST save the active tab to `localStorage.getItem('mei_active_tab')` and restore it inside `DOMContentLoaded` so the user is not forced back to Tab 1 on page refresh.

### Rule 11: Escalation Form - Lens PIDs
- The `updateDynamicForm` function in `app.js` MUST always explicitly include input fields for `txtFailedLeftPid` and `txtFailedRightPid` whenever a Lens failure category (`LEFT LENS`, `RIGHT LENS`, `BOTH LENS`, or `ALL ITEMS`) is selected. If these fields are omitted from the dynamically injected HTML, the frontend will fail to capture the lens PIDs, permanently breaking the "Lenses Only" PID chart on the Analytics dashboard.

### Rule 12: NEVER Use Destructive File Commands
- **STRICTLY FORBIDDEN**: `git checkout`, `git reset --hard`, `git restore`, or any command that overwrites files from git history.
- **Reason**: This repository has only 1 commit. Running `git checkout HEAD <file>` destroys ALL uncommitted code the user has written (including yesterday's work), with no recovery possible.
- **Enforcement**: Always use targeted file edits (`replace_file_content`, `multi_replace_file_content`) on specific line ranges. If a file is broken, READ it first and edit only the broken section. NEVER overwrite the whole file.

### Rule 13: NO Fake Defaults in UI or Backend
- **FORBIDDEN**: Defaulting `lens_index` to `"1.56"`, defaulting FR Tag from `oi_processing_type`, or any other value that masks missing DB data.
- **Enforcement**: If the DB has no data for a field, the field MUST show `--` or empty in the UI. The user explicitly wants to know when data is missing — do not hide it.

### Rule 14: SQL Lookup Fires ONLY on 7-Character Tray ID Input
- The `triggerLookup()` function in `app.js` MUST only be called when the user types exactly 7 characters in the tray ID barcode input.
- **FORBIDDEN**: Calling `triggerLookup()` again inside `logEscalation()` — the lookup already happened at scan time. Re-running it wastes time and causes duplicate DB queries.

### Rule 15: Tray Lookup - espresso_fitting_id Fallback
- When `wms.tray_monitoring.wms_fitting_id = 0`, the lookup MUST NOT immediately return 444.
- **Enforcement**: Query `espresso_fitting_id` from the same row. If it is valid (non-zero, non-null), use it as the `fitting_id` for the `wms.order_items` query.
- **Reason**: Some older trays (e.g. CT04350) have `wms_fitting_id = 0` but have valid `espresso_fitting_id` with live order data. Returning 444 immediately loses this data.

### Rule 16: PyMySQL TCP Socket Timeouts (DoS Prevention)
- **MANDATORY**: `pymysql.connect` MUST include strict TCP socket timeouts (e.g., `read_timeout=4` and `write_timeout=3`).
- **Reason**: The "adaptive connect" proxy drops idle connections without sending TCP RST packets. If `GLOBAL_DB_CONN.ping(reconnect=True)` executes on a dead socket without timeouts, it will hang indefinitely, freezing the thread lock and causing a Denial of Service (DoS) for all future queries.

### Rule 17: Thread-Safe Database Lookups
- **MANDATORY**: All database queries within `api_lookup_tray` (or any other API endpoint using the global connection) MUST be wrapped in a `with LOOKUP_LOCK:` block.
- **Reason**: A barcode scanner can fire rapid concurrent requests. Since PyMySQL connections are NOT thread-safe, concurrent usage of `GLOBAL_DB_CONN` will corrupt the connection stream, causing random hangs and `Commands out of sync` errors.

### Rule 18: Frontend Scanner Debounce Lock
- **MANDATORY**: `triggerLookup(trayId)` in `app.js` MUST use a state lock (e.g., `currentFetchingTray = trayId`) to abort duplicate concurrent requests.
- **Reason**: Barcode scanners type rapidly and automatically press `Enter`. This triggers BOTH the `input` event (at exactly 7 characters) and the `keydown` event simultaneously. Without a debounce lock, the frontend fires two identical API requests at the exact same millisecond, amplifying the risk of backend thread collisions.
