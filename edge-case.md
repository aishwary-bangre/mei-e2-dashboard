# MEI E2 System - Comprehensive Edge-Case Catalog & Resiliency Architecture

> [!IMPORTANT]
> **PERMANENT IMMUTABLE ARCHITECTURE MANDATE**
> The backend settings, thread locks, proxy connection protocol, and UI button layout documented below are **PERMANENTLY FROZEN**. Future AI assistants and developers MUST NOT modify, refactor, or revert these core rules.

This document catalogs all technical edge cases, failure modes, root causes, and defensive engineering solutions implemented in the **MEI E2 Analytics & Escalation Logging System**.

---

## 1. Database Proxy & Tunnel Edge Cases

### EC-01: Session Password Mismatch Causes Security Kill
* **Symptom**: `adaptive.exe` in the terminal window terminates automatically after a query is executed.
* **Root Cause**: `adaptive.exe` generates a fresh random password on every session launch. If `app.py` sends an outdated password, MySQL returns Error 1045 (Access Denied), causing Adaptive's proxy to immediately force-close the terminal process.
* **Defensive Fix**: `app.py` catches Error 1045 and clears `CACHED_CREDS`. Operators must manually sync the password by clicking the **`🟢 MySQL Connected`** badge.

### EC-02: Background Subprocess Collisions
* **Symptom**: Terminal session exits when background processes attempt to bind port 13306.
* **Root Cause**: Spawning a second `adaptive.exe` process creates a port binding collision on `13306`, causing the proxy daemon to shut down the active session.
* **Defensive Fix**: Removed all background `subprocess.Popen` auto-spawners from `app.py`.

### EC-03: Persistent Connections & Keep-Alive Crashes (The Terminal Crash Fix)
* **Symptom**: `adaptive.exe` in the terminal window auto-exits back to `C:\>` after 1 or 2 queries or when sitting idle.
* **Root Cause**: Running a background keep-alive thread polling `SELECT 1` completely breaks socket multiplexing inside `adaptive.exe`, causing a `[WinError 10054]` pipe crash.
* **Defensive Fix**: `app.py` uses a SILENT global persistent connection (`GLOBAL_DB_CONN`). It never runs background ping threads. Instead, it securely uses `GLOBAL_DB_CONN.ping(reconnect=True)` at the moment of request, ensuring the proxy stays perfectly stable while avoiding the 0.85s handshake latency on every query.

---

## 2. MySQL Schema & Query Resiliency Edge Cases

### EC-04: The 30-Second Unindexed `LEFT JOIN` Timeout Hazard
* **Symptom**: Scanning an unregistered tray ID (like `CT52520`) causes the dashboard UI to hang on `Fetching SQL...` for 30 seconds before timing out.
* **Root Cause**: The backend used a `LEFT JOIN wms.order_items oi ON oi.fitting_id = tm.wms_fitting_id`. When a tray doesn't exist, `fitting_id` is `0` or NULL. `wms.order_items` is completely unindexed for `fitting_id = 0`, forcing MySQL to scan millions of rows and freezing the database proxy.
* **Defensive Fix**: Replaced the single `LEFT JOIN` with an **Optimized 2-Step Indexed Query**:
  1. Check `wms.tray_monitoring` and `nexs_dp.monitor_panel_data` first to guarantee `fitting_id > 0` (Fast-fails in `0.2s`).
  2. Only query `wms.order_items` and `wms.fitting_detail` as a single JOIN if `fitting_id` is valid.

### EC-05: Missing Table Columns (`fitting_id` on `wms.power`)
* **Symptom**: `Unknown column 'fitting_id' in 'where clause' (Error 1054)` resulting in HTTP 500 error.
* **Root Cause**: `wms.power` schema contains `order_id` and `product_id`, but DOES NOT contain `fitting_id` or `barcode`.
* **Defensive Fix**: Multi-stage lookup pipeline. (Stage 1: query by `order_id`, Stage 2: query by numeric `product_id`). Included `LIMIT 4` to prevent slow table scans.

### EC-06: Zero-Power / Plano Lenses (`SPH: 0.0`, `CYL: 0.0`)
* **Symptom**: Trays like `CT52838` return `0.0` for all powers.
* **Defensive Fix**: Backend maps numeric `0.0` values to string `"0.0"` instead of falsy empty strings `""`.

---

## 3. Frontend UI & DOM Resiliency Edge Cases

### EC-07: Protecting Manual Website Entries When Clearing Excel Imports
* **Symptom**: 5 earlier manually logged website entries were accidentally deleted when the user clicked `Clear Imported Data & Reset`.
* **Root Cause**: Older manually logged entries lacked the explicit `'is_imported': False` tag. The clear logic used `if r.get('is_imported') is False`, silently wiping them out.
* **Defensive Fix**: Updated clear filter in `app.py` to `if not r.get('is_imported', False):`. This guarantees that ANY entry without `is_imported: True` is permanently protected as a manual entry.

### EC-08: Excel US Locale Date Swap Anomaly (DD-MM-YYYY)
* **Symptom**: When importing Excel files in India, dates from the 1st to the 12th (e.g., `02-08-2026`) are incorrectly parsed into the database with swapped days and months (e.g., `08/02/2026` or February 8th).
* **Root Cause**: Excel's US Locale automatically misinterprets `DD-MM-YYYY` text as `MM-DD-YYYY` if the Day is `<= 12`.
* **Defensive Fix**: `parse_excel_date` explicitly intercepts parsed `datetime` objects and undoes the swap by formatting with `%m/%d/%Y` whenever `val_obj.day <= 12 and val_obj.month <= 12`. **DO NOT REMOVE THIS LOGIC**.

### EC-09: Frontend Fetch Timeout Hangups
* **Symptom**: UI stuck on `Fetching SQL...` permanently if the backend/proxy crashes mid-query.
* **Defensive Fix**: Implemented a 5-second `AbortController` fetch timeout in `triggerLookup()` in `static/app.js`. If the lookup hangs, it safely aborts and displays `⏱️ Query Timeout`.
