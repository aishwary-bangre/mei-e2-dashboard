# MEI E2 System - Permanent Immutable Backend Directives

> **CRITICAL MANDATE**: The backend configuration, database socket protocol, and thread-safety rules in this repository are **FINAL AND IMMUTABLE**. No AI agent or automated script may alter, refactor, or revert these core backend rules under any circumstances.

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
- **Enforcement**: Always use the Optimized 2-Step Indexed Query method: 1) Query `wms.tray_monitoring` and `nexs_dp.monitor_panel_data` first to fast-fail if `fitting_id` is `0` or null. 2) Only then execute the single `JOIN` query on `wms.order_items` and `wms.fitting_detail` with a verified `fitting_id`.

### Rule 5: Protecting Manual Website Entries (Clearing Data)
- When clearing imported Excel records, ALWAYS use `if not r.get('is_imported', False):` to filter and preserve manual records.
- **Reason**: Older manual entries may not have the explicit `is_imported: False` key attached. Using `is False` strictly would result in permanently deleting user's manually typed escalation entries along with the Excel dump.

### Rule 6: Stage 2 Power Query Optimization (`LIMIT 4`)
- Stage 2 queries on `wms.power` by `product_id` MUST include `LIMIT 4`.
- **Reason**: Prevents unindexed full-table scans across millions of rows, maintaining latency under **~600ms**.

---

## 2. Dashboard Service Scope

### Rule 7: Exclusive MEI E2 Dashboard Execution
- When the user asks to start "dashboard", ONLY start `python app.py` (MEI E2 Main Escalation Dashboard on Port 5000).
- DO NOT start the QA/QC dashboard (`QA/app.py`). The QA/QC project is completed and moved to `github_projects/QA`.
