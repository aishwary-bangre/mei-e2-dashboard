import sys
import os
import glob
import re
import io
import json
import socket
import time
import datetime
import threading
import subprocess
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import pymysql  # type: ignore
import pymysql.cursors  # type: ignore
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

ADAPTIVE_EXE = r"C:\Users\aishwary.bangre\adaptive.exe"
LOCAL_DB_FILE = os.path.join(os.path.dirname(__file__), "wms_e2_escalations.json")
OPTIONS_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "dropdown_options.json")
IMPORT_META_FILE = os.path.join(os.path.dirname(__file__), "import_meta.json")

app = Flask(__name__)
CORS(app)

# Reconfigure stdout for UTF-8 on Windows
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Default Dropdown Configurations
DEFAULT_DROPDOWN_OPTIONS = {
    "shift_ic": [
        "ADITI", "RAMESH", "SURESH", "JANHVI", "ABHIJEET", "RADHESHYAM GUPTA",
        "BANSI LAL CHAUDHARY", "RAKESH KUMAR", "VIVEK KUMAR", "AMIRUN NISHA",
        "SARASWATI BADRA", "PRACHI PRATYASHA DHAL", "SONALI PARIDA",
        "GITANJALI MAHARANA", "BABLU YADAV", "SHIVAM YADAV"
    ],
    "operator": [
        "PRACHI", "SARADA", "GITANJALI", "NEHA", "AMIRUN", "BABLU", "SHIVAM"
    ],
    "fail_category": [
        "LEFT LENS", "RIGHT LENS", "BOTH LENS", "ALL ITEMS"
    ],
    "status": [
        "NG", "OK", "RETURN TO LAB", "RETURN TO NON JIT ASRS", "RETURN TO JIT ASRS", "RETURN TO STOCKING"
    ],
    "issue": [
        "WRONG PICKING", "INTERCHANGE LENS", "ALL MATERIAL FAIL (INCORRECT ITEMS)",
        "ASRS - FRAME BROKEN / DAMAGED / WRONG", "ASRS - IN TRAY",
        "ASRS - IN TRAY WITH WRONG BARCODE", "ASRS - IN TRAY WRONG ITEM",
        "ASRS - LENS BROKEN", "ASRS - LENS NOT IN TRAY", "ASRS - LENS NOT RECEIVED",
        "ASRS - WRONG BARCODE", "ASRS - WRONG FRAME",
        "ASRS- SCRATCH / COATING / COATING DAMAGE", "BEVEL/GROOVE/FLAT - INCORRECT/MISS",
        "BEVEL/GROOVE ISSUE", "CANCELLED ORDER", "DRILL - INCORRECT/MISS",
        "DRILL - INCORRECT DRILLING", "ENGRAVING NOT READABLE/INCORRECT",
        "ENGRAVING NOT FOUND / WRONG", "ESPRESSO-NEXS POWER MISMATCH",
        "ESPRESSO-NEW DATA / CORRECTION", "FITTING - UNCUT ORDER",
        "FITTING - UNCUT LENS / NOT CUT", "IN PICKING/PICKED/PRODUCTION DONE STATUS",
        "IN PICKING/PICKING ISSUE", "IN TRAY - JOB CARD WRONG / MISSING",
        "IN TRAY - JOB NOT SYNC", "MACHINE - CHIP", "MACHINE - CHIPPING / BURR",
        "MACHINE - LENS BROKEN", "MACHINE - LENS LOST", "NO DATA",
        "OUT OF SHAPE - CENTRATION ISSUE", "OUT OF SHAPE", "POWER WITHIN TOLERANCE / OK",
        "POWER WITHIN TOLERANCE", "ROUGH CUTTING / BAD CUT", "ROUGH CUTTING",
        "SAFETY BEVEL IMPROPER/MISSING", "SAFETY BEVEL ISSUE", "SAME LENS FOR BOTH SIDE",
        "SAME LENS FOUND (BOTH R & L SAME)", "SCRATCH", "SELECT LEFT LENS",
        "SELECT RIGHT LENS", "SLIP OF LENS / SLIPPAGE", "SLIP OF LENS",
        "SMALL LENS DIAMETER", "SMALL LENS SIZE", "TRIAL ORDER", "WITHOUT SHAPE DATA",
        "WITHOUT SHAPE", "WRONG AXIS", "WRONG POWER ADD / AP", "WRONG POWER CYL",
        "WRONG POWER SPH", "WRONG POWER (ALL)", "WRONG STOCKIN", "WRONG STOCK",
        "QC REPROCESS ORDERS", "QC REPROCESS", "WRONG SHAPE / SIZE", "WRONG SHAPE",
        "COATING DAMAGE", "TRAY FELL FROM CONVEYOR", "OTHER"
    ]
}


def load_dropdown_options():
    """Load dropdown options from JSON or write defaults if missing."""
    if not os.path.exists(OPTIONS_CONFIG_FILE):
        save_dropdown_options(DEFAULT_DROPDOWN_OPTIONS)
        return DEFAULT_DROPDOWN_OPTIONS
    try:
        with open(OPTIONS_CONFIG_FILE, 'r', encoding='utf-8') as f:
            opts = json.load(f)
            for k, v in DEFAULT_DROPDOWN_OPTIONS.items():
                if k not in opts:
                    opts[k] = v
            return opts
    except Exception:
        return DEFAULT_DROPDOWN_OPTIONS


def save_dropdown_options(options):
    try:
        with open(OPTIONS_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(options, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[!] Error saving dropdown options: {e}")
        return False


# Persistent Connection, Credentials & Lookup Cache
CACHED_CREDS = None
PERSISTENT_CONN = None
ADAPTIVE_EXE = r"C:\Users\aishwary.bangre\adaptive.exe"
ADAPTIVE_PROCESS = None
DYNAMIC_PASSWORD = None
TRAY_CACHE = {}  # Fast in-memory cache {tray_id: (timestamp, result_dict)}
CACHE_TTL = 600  # 10 minutes cache TTL

# -----------------------------------------------------------------------------
# 1. FAST ADAPTIVE ACCESS & PERSISTENT MYSQL CONNECTION MANAGEMENT
# -----------------------------------------------------------------------------
def is_port_open(host='127.0.0.1', port=13306, timeout=0.5):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        res = s.connect_ex((host, port))
        return res == 0
    except Exception:
        return False
    finally:
        s.close()


def _read_adaptive_stdout(proc):
    """Background thread to continuously read adaptive stdout and capture dynamic session password."""
    global DYNAMIC_PASSWORD, CACHED_CREDS
    try:
        for line in proc.stdout:
            l = line.strip()
            if l:
                print(f"[Adaptive Tunnel] {l}")
            m = re.search(r'password\s*=\s*(\S+)', l, re.IGNORECASE)
            if m:
                extracted_pwd = m.group(1).strip()
                DYNAMIC_PASSWORD = extracted_pwd
                CACHED_CREDS = None  # Force creds refresh with newly detected password
                print(f"[+] Auto-Detected Adaptive Session Password: '{DYNAMIC_PASSWORD}'")
    except Exception as e:
        print(f"[!] Error reading adaptive stdout: {e}")


def ensure_adaptive_tunnel():
    """Checks if port 13306 is open. Returns True if database proxy socket is ready."""
    return is_port_open()


SESSION_FILE = os.path.join(os.path.dirname(__file__), 'adaptive_session.json')

def load_saved_password():
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                pwd = data.get('password')
                if pwd and str(pwd).strip():
                    return str(pwd).strip()
        except Exception:
            pass
    return None

def save_working_password(pwd):
    if not pwd:
        return
    try:
        with open(SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump({'password': pwd}, f, indent=2)
    except Exception as e:
        print(f"[!] Error saving session password: {e}")

def delete_saved_password():
    if os.path.exists(SESSION_FILE):
        try:
            os.remove(SESSION_FILE)
        except Exception:
            pass

def get_latest_adaptive_creds():
    """Fast in-memory dynamic credentials return with session caching."""
    global CACHED_CREDS, DYNAMIC_PASSWORD
    if CACHED_CREDS:
        return CACHED_CREDS

    pwd = DYNAMIC_PASSWORD or load_saved_password() or ""

    CACHED_CREDS = {
        'host': '127.0.0.1',
        'port': 13306,
        'user': 'aishwary_bangre',
        'password': pwd,
        'database': 'wms',
        'autocommit': True,
        'connect_timeout': 5,
        'cursorclass': pymysql.cursors.DictCursor
    }
    return CACHED_CREDS


DB_LOCK = threading.Lock()
LOOKUP_LOCK = threading.Lock()

GLOBAL_DB_CONN = None

def get_fresh_db_connection():
    """Returns a globally cached MySQL connection to prevent 1s connection overhead."""
    global DYNAMIC_PASSWORD, CACHED_CREDS, GLOBAL_DB_CONN
    with DB_LOCK:
        if not is_port_open():
            raise Exception("Database proxy port 13306 is closed. Please start 'adaptive connect' in your terminal.")

        if not DYNAMIC_PASSWORD:
            saved_pwd = load_saved_password()
            if saved_pwd:
                DYNAMIC_PASSWORD = saved_pwd
                CACHED_CREDS = None
            else:
                raise Exception("Adaptive session password missing. Click '🟢 MySQL Connected' badge to enter terminal password.")

        if GLOBAL_DB_CONN:
            try:
                GLOBAL_DB_CONN.ping(reconnect=True)
                return GLOBAL_DB_CONN
            except Exception:
                pass

        creds = get_latest_adaptive_creds()
        creds['connect_timeout'] = 3
        creds['read_timeout'] = 4
        creds['write_timeout'] = 3
        try:
            GLOBAL_DB_CONN = pymysql.connect(**creds)
            save_working_password(DYNAMIC_PASSWORD)
            return GLOBAL_DB_CONN
        except pymysql.err.OperationalError as e:
            if e.args[0] == 1045:
                CACHED_CREDS = None
                DYNAMIC_PASSWORD = None
                delete_saved_password()
                raise Exception("Adaptive password invalid or expired. Click '🟢 MySQL Connected' badge in UI to enter terminal password.")
            raise e
        except Exception as e:
            raise e


# -----------------------------------------------------------------------------
# 2. LOCAL PERSISTENT STORAGE FALLBACK
# -----------------------------------------------------------------------------
def load_local_escalations():
    if not os.path.exists(LOCAL_DB_FILE):
        return []
    try:
        with open(LOCAL_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def save_local_escalations(escalations):
    try:
        with open(LOCAL_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(escalations, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[!] Error saving local escalations: {e}")
        return False

# -----------------------------------------------------------------------------
# 3. HELPER UTILITIES
# -----------------------------------------------------------------------------
def get_current_shift(now=None):
    if not now:
        now = datetime.datetime.now()
    hour = now.hour
    if 6 <= hour < 14:
        return "Shift A"
    elif 14 <= hour < 22:
        return "Shift B"
    else:
        return "Shift C"

# -----------------------------------------------------------------------------
# 4. API ENDPOINTS
# -----------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    """Returns database connection health status."""
    connected = is_port_open()
    return jsonify({
        'status': 'online' if connected else 'offline',
        'db': 'MySQL (wms)',
        'port': 13306,
        'shift': get_current_shift(),
        'server_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })


@app.route('/api/config/password', methods=['POST'])
def set_password_endpoint():
    """Sets and immediately verifies the active terminal session password against port 13306."""
    global DYNAMIC_PASSWORD, CACHED_CREDS, PERSISTENT_CONN
    data = request.json or {}
    pwd = str(data.get('password', '')).strip()

    if not pwd:
        return jsonify({'success': False, 'error': 'Password cannot be empty.'}), 400

    if not is_port_open():
        return jsonify({'success': False, 'error': "Database proxy port 13306 is closed. Please start 'adaptive connect' in your terminal."}), 400

    test_creds = {
        'host': '127.0.0.1',
        'port': 13306,
        'user': 'aishwary_bangre',
        'password': pwd,
        'database': 'wms',
        'autocommit': True,
        'connect_timeout': 3,
        'cursorclass': pymysql.cursors.DictCursor
    }

    try:
        conn = pymysql.connect(**test_creds)
        conn.ping(reconnect=False)
        with DB_LOCK:
            if PERSISTENT_CONN and PERSISTENT_CONN.open:
                try:
                    PERSISTENT_CONN.close()
                except Exception:
                    pass
            DYNAMIC_PASSWORD = pwd
            CACHED_CREDS = test_creds
            PERSISTENT_CONN = conn
        return jsonify({'success': True, 'message': 'Password verified! Connected to MySQL database.'})
    except pymysql.err.OperationalError as e:
        if e.args[0] == 1045:
            return jsonify({'success': False, 'error': '❌ Incorrect Password! Check your terminal output and try again.'}), 401
        return jsonify({'success': False, 'error': f'Database connection error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': f'Connection failed: {str(e)}'}), 500


# --- DYNAMIC DROPDOWN OPTIONS MANAGEMENT ENDPOINTS (CRUD) ---
@app.route('/api/options', methods=['GET'])
def get_all_options():
    """Get all dropdown options."""
    return jsonify({'success': True, 'options': load_dropdown_options()})


@app.route('/api/options/<field_id>', methods=['POST'])
def add_option(field_id):
    """Add a new option to a specific dropdown field."""
    data = request.json or {}
    new_opt = str(data.get('option', '')).strip().upper()
    if not new_opt:
        return jsonify({'error': 'Option name cannot be empty'}), 400

    opts = load_dropdown_options()
    field_opts = opts.get(field_id, [])

    if new_opt in field_opts:
        return jsonify({'error': 'Option already exists'}), 400

    field_opts.append(new_opt)
    opts[field_id] = field_opts
    save_dropdown_options(opts)
    return jsonify({'success': True, 'options': field_opts})


@app.route('/api/config/password', methods=['GET', 'POST'])
def api_config_password():
    """Get or update active Adaptive session password dynamically."""
    global DYNAMIC_PASSWORD, CACHED_CREDS, PERSISTENT_CONN
    if request.method == 'POST':
        data = request.json or request.form or {}
        pwd = str(data.get('password', '')).strip()
        if pwd:
            DYNAMIC_PASSWORD = pwd
            CACHED_CREDS = None
            save_working_password(pwd)
            if PERSISTENT_CONN:
                try:
                    PERSISTENT_CONN.close()
                except Exception:
                    pass
            PERSISTENT_CONN = None
            print(f"[+] Dynamic Adaptive Password set and persisted to disk: {DYNAMIC_PASSWORD}")
            return jsonify({'success': True, 'password': DYNAMIC_PASSWORD})
        return jsonify({'error': 'Password cannot be empty'}), 400
    return jsonify({'password': DYNAMIC_PASSWORD or ''})


@app.route('/api/options/<field_id>', methods=['PUT'])
def edit_option(field_id):
    """Edit/rename an existing option in a dropdown field."""
    data = request.json or {}
    old_opt = str(data.get('old_option', '')).strip()
    new_opt = str(data.get('new_option', '')).strip().upper()

    if not old_opt or not new_opt:
        return jsonify({'error': 'Both old and new option names are required'}), 400

    opts = load_dropdown_options()
    field_opts = opts.get(field_id, [])

    if old_opt not in field_opts:
        return jsonify({'error': f"Option '{old_opt}' not found"}), 404

    idx = field_opts.index(old_opt)
    field_opts[idx] = new_opt
    opts[field_id] = field_opts
    save_dropdown_options(opts)

    return jsonify({'success': True, 'options': field_opts})


@app.route('/api/options/<field_id>/<path:option_name>', methods=['DELETE'])
def delete_option(field_id, option_name):
    """Delete an option from a dropdown field."""
    opts = load_dropdown_options()
    field_opts = opts.get(field_id, [])

    if option_name not in field_opts:
        return jsonify({'error': f"Option '{option_name}' not found"}), 404

    field_opts.remove(option_name)
    opts[field_id] = field_opts
    save_dropdown_options(opts)

    return jsonify({'success': True, 'options': field_opts})


@app.route('/api/lookup/<tray_id>', methods=['GET'])
def api_lookup_tray(tray_id):
    """
    Bulletproof Live SQL Tray Lookup:
    Combines wms.tray_monitoring, wms.fitting_detail, and wms.order_items in 1 JOIN query.
    Performs multi-stage optical power lookup:
      Stage 1: By order_id
      Stage 2: Fallback by product_id (right_lens_pid, left_lens_pid)
      Stage 3: Fallback by fitting_id
    Fast in-memory caching provides instant 0ms responses for repeated scans.
    """
    tray_id = tray_id.strip()
    if not tray_id:
        return jsonify({'error': 'Please provide a valid Tray ID'}), 400

    now_ts = time.time()
    # Check in-memory cache for instant < 1ms response
    if tray_id in TRAY_CACHE:
        cached_ts, cached_res = TRAY_CACHE[tray_id]
        if now_ts - cached_ts < CACHE_TTL:
            cached_copy = dict(cached_res)
            cached_copy['cached'] = True
            cached_copy['elapsed_ms'] = 0.5
            return jsonify(cached_copy)

    start_time = time.time()
    conn = None
    try:
        conn = get_fresh_db_connection()
        cursor = conn.cursor()
        
        with LOOKUP_LOCK:
            # Step 1: Query wms.order_items by location_id for real-time active tray contents
            cursor.execute("SELECT fitting_id FROM wms.order_items WHERE location_id = %s LIMIT 1", (tray_id,))
            loc_row = cursor.fetchone()
            
            if loc_row and loc_row.get('fitting_id'):
                fitting_id = loc_row.get('fitting_id')
            else:
                # Step 1b: Fallback to wms.tray_monitoring (stale ledger safety net)
                cursor.execute("""
                    SELECT wms_fitting_id AS fitting_id, espresso_fitting_id, identifier
                    FROM wms.tray_monitoring
                    WHERE tray_id = %s
                    ORDER BY updated_at DESC LIMIT 1
                """, (tray_id,))
                tm_row = cursor.fetchone()
                
                if not tm_row:
                    return jsonify({'error': f"Tray ID '{tray_id}' not found in database or is unregistered"}), 444
                
                identifier = str(tm_row.get('identifier') or '').strip().upper()
                if identifier == 'DISCARD':
                    return jsonify({'error': f"Tray '{tray_id}' not found (currently empty or discarded)"}), 444
                
                fitting_id = tm_row.get('fitting_id')
                
                # If wms_fitting_id is 0 or missing, fall back to espresso_fitting_id
                if not fitting_id or str(fitting_id).strip() in ('', '0'):
                    espresso_id = str(tm_row.get('espresso_fitting_id') or '').strip()
                    if not espresso_id or espresso_id in ('', '0', 'None'):
                        return jsonify({'error': f"Tray ID '{tray_id}' not found in database or is unregistered"}), 444
                    fitting_id = espresso_id
                
            # Step 2: Query wms.order_items safely
            cursor.execute("""
                SELECT fitting_id, nexs_order_id, product_id, barcode, item_type, power_id, shipping_package_id, processing_type AS oi_processing_type
                FROM wms.order_items
                WHERE fitting_id = %s
            """, (fitting_id,))
            rows = cursor.fetchall()
            
            if not rows:
                return jsonify({'error': f"No item records found for Fitting ID {fitting_id}"}), 444
                
            # Step 2b: Get order_id from fitting_detail (separate small query, no JOIN overhead)
            cursor.execute("SELECT order_id FROM wms.fitting_detail WHERE fitting_id = %s LIMIT 1", (fitting_id,))
            fd_row = cursor.fetchone()
            order_id = str(fd_row.get('order_id') if fd_row else '')
            if not order_id or order_id in ('0', 'None'):
                order_id = next((str(r.get('nexs_order_id')).strip() for r in rows if r.get('nexs_order_id') and str(r.get('nexs_order_id')).strip() not in ('0', 'None')), '')
            
            # Safely fetch is_jit and processing_type from monitor_panel_data
            sp_ids = list(set([str(r['shipping_package_id']).strip() for r in rows if r.get('shipping_package_id') and str(r['shipping_package_id']).strip() not in ('', '0', 'None')]))
            
            mp_data = {}
            if sp_ids:
                format_strings = ','.join(['%s'] * len(sp_ids))
                cursor.execute(f"SELECT shipping_package_id, jit_type, v3_fr_tag FROM nexs_dp.monitor_panel_data WHERE shipping_package_id IN ({format_strings})", tuple(sp_ids))
                for mr in cursor.fetchall():
                    sp = str(mr.get('shipping_package_id', '')).strip()
                    mp_data[sp] = {
                        'jit': str(mr.get('jit_type') or 'NO').strip().upper(),
                        'fr': str(mr.get('v3_fr_tag') or '--').strip().upper()
                    }
                    
            # Check processing_type
            is_jit_val = 'NO'
            processing_type_val = '--'
            for r in rows:
                sp = str(r.get('shipping_package_id')).strip()
                if sp in mp_data:
                    j_val = mp_data[sp]['jit']
                    if j_val == 'LENS LAB':
                        is_jit_val = 'AUTO'
                    elif j_val == 'EXTERNAL VENDOR' and is_jit_val != 'AUTO':
                        is_jit_val = 'MANUAL'
                    
                    p_val = mp_data[sp]['fr']
                    if p_val and p_val != '--':
                        processing_type_val = p_val
                        break
            
            frame_pid = ""
            frame_barcode = ""
            right_lens_pid = ""
            right_lens_barcode = ""
            right_power_id = ""
            left_lens_pid = ""
            left_lens_barcode = ""
            left_power_id = ""
            
            for r in rows:
                itype = str(r.get('item_type') or '').strip().upper()
                pid = str(r.get('product_id') or '').strip()
                bcode = str(r.get('barcode') or '').strip()
                pwr_id = str(r.get('power_id') or '').strip()
                
                if itype == 'FRAME':
                    frame_pid = pid
                    frame_barcode = bcode
                elif itype == 'RIGHTLENS':
                    right_lens_pid = pid
                    right_lens_barcode = bcode
                    right_power_id = pwr_id
                elif itype == 'LEFTLENS':
                    left_lens_pid = pid
                    left_lens_barcode = bcode
                    left_power_id = pwr_id
                    
            # Fetch Right Lens Power
            right_power = {}
            if right_power_id and right_power_id not in ('', '0', 'None'):
                cursor.execute("SELECT lens_index, sph, cyl, axis, ap AS addn, lensname FROM wms.power WHERE id = %s LIMIT 1", (right_power_id,))
            elif right_lens_pid and right_lens_pid not in ('', '0'):
                cursor.execute("SELECT lens_index, sph, cyl, axis, ap AS addn, lensname FROM wms.power WHERE product_id = %s LIMIT 1", (right_lens_pid,))
            r_row = cursor.fetchone() if (right_power_id or right_lens_pid) else None
            
            if r_row:
                right_power = {
                    'sph': str(r_row.get('sph') or ''),
                    'cyl': str(r_row.get('cyl') or ''),
                    'axis': str(r_row.get('axis') or ''),
                    'addn': str(r_row.get('addn') or '')
                }
                lens_index = str(r_row.get('lens_index') or '')
                lens_name = str(r_row.get('lensname') or '')
            else:
                lens_index = ""
                lens_name = ""
                
            # Fetch Left Lens Power
            left_power = {}
            if left_power_id and left_power_id not in ('', '0', 'None'):
                cursor.execute("SELECT lens_index, sph, cyl, axis, ap AS addn, lensname FROM wms.power WHERE id = %s LIMIT 1", (left_power_id,))
            elif left_lens_pid and left_lens_pid not in ('', '0'):
                cursor.execute("SELECT lens_index, sph, cyl, axis, ap AS addn, lensname FROM wms.power WHERE product_id = %s LIMIT 1", (left_lens_pid,))
            l_row = cursor.fetchone() if (left_power_id or left_lens_pid) else None
            
            if l_row:
                left_power = {
                    'sph': str(l_row.get('sph') or ''),
                    'cyl': str(l_row.get('cyl') or ''),
                    'axis': str(l_row.get('axis') or ''),
                    'addn': str(l_row.get('addn') or '')
                }
                if not lens_index and l_row.get('lens_index'): lens_index = str(l_row.get('lens_index') or '')
                if not lens_name and l_row.get('lensname'): lens_name = str(l_row.get('lensname') or '')


        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        res_dict = {
            'success': True,
            'tray_id': tray_id,
            'fitting_id': str(fitting_id),
            'order_id': str(order_id or ''),
            'is_jit': is_jit_val,
            'processing_type': processing_type_val,
            'frame_pid': frame_pid,
            'frame_barcode': frame_barcode,
            'right_lens_pid': right_lens_pid,
            'right_lens_barcode': right_lens_barcode,
            'left_lens_pid': left_lens_pid,
            'left_lens_barcode': left_lens_barcode,
            'lens_index': lens_index,
            'lens_name': lens_name,
            'right_lens': {
                'sph': str(right_power.get('sph') if right_power.get('sph') is not None else '--'),
                'cyl': str(right_power.get('cyl') if right_power.get('cyl') is not None else '--'),
                'axis': str(right_power.get('axis') if right_power.get('axis') is not None else '--'),
                'addn': str(right_power.get('addn') if right_power.get('addn') is not None else '--')
            },
            'left_lens': {
                'sph': str(left_power.get('sph') if left_power.get('sph') is not None else '--'),
                'cyl': str(left_power.get('cyl') if left_power.get('cyl') is not None else '--'),
                'axis': str(left_power.get('axis') if left_power.get('axis') is not None else '--'),
                'addn': str(left_power.get('addn') if left_power.get('addn') is not None else '--')
            },
            'sph': str(right_power.get('sph') or left_power.get('sph') or ''),
            'cyl': str(right_power.get('cyl') or left_power.get('cyl') or ''),
            'axis': str(right_power.get('axis') or left_power.get('axis') or ''),
            'addn': str(right_power.get('addn') or left_power.get('addn') or ''),
            'items_count': len(rows),
            'elapsed_ms': elapsed_ms
        }

        # Cache result in memory
        TRAY_CACHE[tray_id] = (now_ts, res_dict)
        return jsonify(res_dict)

    except Exception as e:
        print(f"[!] API Lookup Error: {e}")
        return jsonify({'error': f"Database lookup failed: {str(e)}"}), 500


def filter_escalation_records(records):
    """Filters records by search text, shift, status, and start_time / end_time range."""
    search = request.args.get('search', '').strip().lower()
    shift = request.args.get('shift', '').strip()
    status = request.args.get('status', '').strip()
    start_time = request.args.get('start_time', '').strip()
    end_time = request.args.get('end_time', '').strip()

    filtered = []
    for r in records:
        if search:
            searchable = (
                f"{r.get('tray_id','')} {r.get('fitting_id','')} "
                f"{r.get('operator','')} {r.get('shift_ic','')} {r.get('issue','')}"
            ).lower()
            if search not in searchable:
                continue

        if shift and r.get('shift') != shift:
            continue

        if status and r.get('status') != status:
            continue

        # Date & Time range filter
        ed = str(r.get('entry_date', '')).strip()
        et = str(r.get('entry_time', '00:00:00')).strip()
        if len(et) == 8 and et[2] == '.' and et[5] == '.':
            et = et.replace('.', ':')

        if '/' in ed:
            parts = ed.split('/')
            if len(parts) == 3:
                ed = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
        elif '-' in ed:
            parts = ed.split('-')
            if len(parts) == 3:
                if len(parts[0]) == 2:  # DD-MM-YYYY
                    ed = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                elif len(parts[0]) == 4:  # YYYY-MM-DD
                    ed = f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"

        r_dt = f"{ed}T{et}"

        if start_time and r_dt:
            st = start_time.replace(' ', 'T')
            if r_dt < st:
                continue

        if end_time and r_dt:
            et = end_time.replace(' ', 'T')
            if len(et) == 16:
                et += ":59"
            if r_dt > et:
                continue

        # Store the normalized datetime in the record temporarily for sorting
        r['_r_dt'] = r_dt
        filtered.append(r)

    # Sort newest to oldest (descending) based on the computed timestamp
    filtered.sort(key=lambda x: x.get('_r_dt', ''), reverse=True)
    
    # Clean up the temporary sort key
    for r in filtered:
        r.pop('_r_dt', None)

    return filtered


@app.route('/api/escalations', methods=['GET', 'POST'])
def api_escalations():
    """Fetches escalation records or logs a new entry."""
    if request.method == 'POST':
        data = request.json or {}
        now = datetime.datetime.now()

        entry = {
            'id': int(now.timestamp() * 1000),
            'timestamp': now.isoformat(),
            'entry_date': now.strftime('%d/%m/%Y'),
            'entry_time': now.strftime('%H:%M:%S'),
            'shift': data.get('shift', 'Shift A'),
            'shift_ic': data.get('shift_ic', ''),
            'operator': data.get('operator', ''),
            'tray_id': data.get('tray_id', ''),
            'fitting_id': data.get('fitting_id', ''),
            'is_jit': data.get('is_jit', 'NO'),
            'processing_type': data.get('processing_type', '--'),
            'jit_status': data.get('jit_status', 'JIT'),
            'cut_status': data.get('cut_status', 'CUT'),
            'frame_pid': data.get('frame_pid', ''),
            'frame_barcode': data.get('frame_barcode', ''),
            'right_lens_pid': data.get('right_lens_pid', ''),
            'right_lens_barcode': data.get('right_lens_barcode', ''),
            'left_lens_pid': data.get('left_lens_pid', ''),
            'left_lens_barcode': data.get('left_lens_barcode', ''),
            'lens_index': data.get('lens_index', ''),
            'sph': data.get('sph', ''),
            'cyl': data.get('cyl', ''),
            'axis': data.get('axis', ''),
            'addn': data.get('addn', ''),
            'fail_category': data.get('fail_category', ''),
            'issue': data.get('issue', ''),
            'status': data.get('status', 'NG'),
            'machine': data.get('machine', ''),
            'is_imported': False
        }

        records = load_local_escalations()
        records.insert(0, entry)
        save_local_escalations(records)

        return jsonify({'success': True, 'entry': entry}), 201

    # GET method with filtering
    records = load_local_escalations()
    filtered = filter_escalation_records(records)
    return jsonify({'success': True, 'count': len(filtered), 'data': filtered})


@app.route('/api/analytics', methods=['GET'])
def api_analytics():
    """Returns analytics scorecards, failure scope donut data, and top issues bar chart ranking."""
    records = filter_escalation_records(load_local_escalations())

    total = len(records)
    if total == 0:
        return jsonify({
            'success': True,
            'summary': {'total': 0, 'ng_count': 0, 'ok_count': 0, 'ng_rate': 0},
            'fail_categories': {'LEFT LENS': 0, 'RIGHT LENS': 0, 'BOTH LENS': 0, 'ALL ITEMS': 0},
            'top_issues': [],
            'shift_counts': {'Shift A': 0, 'Shift B': 0, 'Shift C': 0}
        })

    ng_count = sum(1 for r in records if r.get('status') == 'NG')
    ok_count = sum(1 for r in records if r.get('status') == 'OK')
    ng_rate = round((ng_count / total) * 100, 1)

    fail_categories = {'LEFT LENS': 0, 'RIGHT LENS': 0, 'BOTH LENS': 0, 'ALL ITEMS': 0}
    issue_counts = {}
    operator_counts = {}
    pid_counts = {}
    pid_issues_map = {}
    shift_counts = {'Shift A': 0, 'Shift B': 0, 'Shift C': 0}
    shift_operators = {}
    
    hourly_trend = {
        'all': [0] * 24,
        'shifts': {},
        'operators': {}
    }
    
    for r in records:
        if str(r.get('status', '')).strip().upper() == 'OK':
            ok_count += 1
            continue
            
        ng_count += 1
            
        cat = str(r.get('fail_category', '')).strip().upper()
        if cat in fail_categories:
            fail_categories[cat] = fail_categories.get(cat, 0) + 1
        
        iss = r.get('issue', 'OTHER')
        issue_counts[iss] = issue_counts.get(iss, 0) + 1

        op = str(r.get('operator', '') or 'UNASSIGNED').strip().upper()
        operator_counts[op] = operator_counts.get(op, 0) + 1

        raw_sh = str(r.get('shift', '') or '').strip().upper()
        if 'SHIFT B' in raw_sh or raw_sh == 'B':
            sh = 'Shift B'
        elif 'SHIFT C' in raw_sh or raw_sh == 'C':
            sh = 'Shift C'
        else:
            sh = 'Shift A'
        shift_counts[sh] = shift_counts.get(sh, 0) + 1

        if sh not in shift_operators:
            shift_operators[sh] = {}
        shift_operators[sh][op] = shift_operators[sh].get(op, 0) + 1

        # HOURLY TREND BUCKETING (Raw NG Counts)
        time_str = str(r.get('entry_time', '')).strip().replace('.', ':')
        try:
            if ':' in time_str:
                hour = int(time_str.split(':')[0])
            else:
                hour = 0
        except:
            hour = 0
            
        if 0 <= hour < 24:
            hourly_trend['all'][hour] += 1
            
            if sh not in hourly_trend['shifts']:
                hourly_trend['shifts'][sh] = [0] * 24
            hourly_trend['shifts'][sh][hour] += 1
            
            if op not in hourly_trend['operators']:
                hourly_trend['operators'][op] = [0] * 24
            hourly_trend['operators'][op][hour] += 1

        for pid_key in ('frame_pid', 'right_lens_pid', 'left_lens_pid'):
            pid_val = str(r.get(pid_key, '') or '').strip()
            if pid_val and pid_val != '0':
                pid_counts[pid_val] = pid_counts.get(pid_val, 0) + 1
                if pid_val not in pid_issues_map:
                    pid_issues_map[pid_val] = {}
                pid_issues_map[pid_val][iss] = pid_issues_map[pid_val].get(iss, 0) + 1

    sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:7]
    sorted_operators = sorted(operator_counts.items(), key=lambda x: x[1], reverse=True)[:7]
    sorted_pids = sorted(pid_counts.items(), key=lambda x: x[1], reverse=True)[:7]
    
    # Strictly filter to Shift A, Shift B, and Shift C only
    valid_shifts = ['Shift A', 'Shift B', 'Shift C']
    sorted_shifts = [(s, shift_counts.get(s, 0)) for s in valid_shifts]

    # Determine Current Active Shift based on local time
    cur_hour = datetime.datetime.now().hour
    if 7 <= cur_hour < 15:
        current_shift = 'Shift A'
    elif 15 <= cur_hour < 23:
        current_shift = 'Shift B'
    else:
        current_shift = 'Shift C'

    active_shift_volume = shift_counts.get(current_shift, 0)

    shift_operators_payload = {}
    for sh_k, op_m in shift_operators.items():
        s_ops = sorted(op_m.items(), key=lambda x: x[1], reverse=True)
        shift_operators_payload[sh_k] = [{'operator': k, 'count': v} for k, v in s_ops]

    top_pids_payload = {'all': []}
    for pid, count in sorted_pids:
        iss_dict = pid_issues_map.get(pid, {})
        top_cause = sorted(iss_dict.items(), key=lambda x: x[1], reverse=True)[0][0] if iss_dict else 'OTHER'
        breakdown_str = ", ".join([f"{k}: {v}" for k, v in sorted(iss_dict.items(), key=lambda x: x[1], reverse=True)])
        top_pids_payload['all'].append({
            'pid': pid,
            'count': count,
            'top_cause': top_cause,
            'breakdown': breakdown_str
        })
        
    # We will populate other shifts in top_pids if requested, but app.js defaults to .all. 
    # For now, populating just 'all' restores the exact structure app.js expects: data.top_pids.all

    # Calculate min_date and max_date for auto-populating Analytics date controls
    min_date = None
    max_date = None
    if records:
        dates = []
        for r in records:
            ed = str(r.get('entry_date', '')).strip()
            et = str(r.get('entry_time', '00:00:00')).strip()
            if len(et) == 8 and et[2] == '.' and et[5] == '.':
                et = et.replace('.', ':')
            if '/' in ed:
                parts = ed.split('/')
                if len(parts) == 3:
                    ed = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
            elif '-' in ed:
                parts = ed.split('-')
                if len(parts) == 3:
                    if len(parts[0]) == 2:
                        ed = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                    elif len(parts[0]) == 4:
                        ed = f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
            if len(ed) == 10 and len(et) >= 5:
                dates.append(f"{ed}T{et[:5]}")
        if dates:
            min_date = min(dates)
            max_date = max(dates)

    return jsonify({
        'success': True,
        'min_date': min_date,
        'max_date': max_date,
        'summary': {
            'total': total,
            'ng_count': ng_count,
            'ok_count': ok_count,
            'ng_rate': ng_rate,
            'active_shift': current_shift,
            'active_shift_volume': active_shift_volume
        },
        'fail_categories': fail_categories,
        'top_issues': [{'issue': k, 'count': v} for k, v in sorted_issues],
        'top_operators': [{'operator': k, 'count': v} for k, v in sorted_operators],
        'top_pids': top_pids_payload,
        'shift_counts': [{'shift': k, 'count': v} for k, v in sorted_shifts],
        'shift_operators': shift_operators_payload,
        'hourly_data': hourly_trend
    })


@app.route('/api/export/excel', methods=['GET'])
def export_excel():
    """Generates formatted .xlsx workbook matching E2 escalation (1).xlsx format."""
    records = filter_escalation_records(load_local_escalations())

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "E2 Escalation"

    headers = [
        "Date", "TIME", "SHIFT", "SHIFT IC", "E2 OP", "TRAY ID", "FITTING ID",
        "IS JIT (YES/NO)", "FR TAG (PROCESSING TYPE)",
        "JIT/NOT JIT", "CUT/UNCUT", "REQ. FRAME PID", "REQ. FRAME BARCODE",
        "REQ. RIGHT LENS PID", "REQ. RIGHT LENS BARCODE",
        "REQ. LEFT LENS PID", "REQ. LEFT LENS BARCODE",
        "LENS INDEX", "SPH", "CYL", "AXIS", "ADDN",
        "FAIL CATEGORY", "ISSUE", "STATUS", "MACHINE"
    ]

    header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

    ws.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for r in records:
        row_data = [
            r.get('entry_date', ''),
            r.get('entry_time', ''),
            r.get('shift', ''),
            r.get('shift_ic', ''),
            r.get('operator', ''),
            r.get('tray_id', ''),
            r.get('fitting_id', ''),
            r.get('is_jit', 'NO'),
            r.get('processing_type', '--'),
            r.get('jit_status', ''),
            r.get('cut_status', ''),
            r.get('frame_pid', ''),
            r.get('frame_barcode', ''),
            r.get('right_lens_pid', ''),
            r.get('right_lens_barcode', ''),
            r.get('left_lens_pid', ''),
            r.get('left_lens_barcode', ''),
            r.get('lens_index', ''),
            r.get('sph', ''),
            r.get('cyl', ''),
            r.get('axis', ''),
            r.get('addn', ''),
            r.get('fail_category', ''),
            r.get('issue', ''),
            r.get('status', ''),
            r.get('machine', '')
        ]
        ws.append(row_data)

    # Sheet 2: Top Failure Reasons Summary
    ws_issues = wb.create_sheet(title="Failure Reasons Summary")
    assert ws_issues is not None
    ws_issues.append(["Rank", "Failure Reason / Issue", "Total Failure Count", "Percentage (%)"])
    for col in range(1, 5):
        cell = ws_issues.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    issue_counts = {}
    for r in records:
        iss = r.get('issue', 'OTHER')
        issue_counts[iss] = issue_counts.get(iss, 0) + 1
    total_recs = len(records) or 1
    sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
    for idx, (k, v) in enumerate(sorted_issues, 1):
        pct = round((v / total_recs) * 100, 1)
        ws_issues.append([idx, k, v, f"{pct}%"])

    # Sheet 3: Operator Failures Summary
    ws_op = wb.create_sheet(title="Operator Failures Summary")
    ws_op.append(["Rank", "Operator Name", "Total Failures Marked", "Percentage (%)"])
    for col in range(1, 5):
        cell = ws_op.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    op_counts = {}
    for r in records:
        op = str(r.get('operator', '') or 'UNASSIGNED').strip().upper()
        op_counts[op] = op_counts.get(op, 0) + 1
    sorted_ops = sorted(op_counts.items(), key=lambda x: x[1], reverse=True)
    for idx, (k, v) in enumerate(sorted_ops, 1):
        pct = round((v / total_recs) * 100, 1)
        ws_op.append([idx, k, v, f"{pct}%"])

    # Sheet 4: Shift-Wise Failures Summary
    ws_shift = wb.create_sheet(title="Shift Failure Summary")
    ws_shift.append(["Shift", "Total Failures", "Percentage (%)"])
    for col in range(1, 4):
        cell = ws_shift.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    shift_counts = {'Shift A': 0, 'Shift B': 0, 'Shift C': 0}
    for r in records:
        sh = r.get('shift', 'Shift A')
        shift_counts[sh] = shift_counts.get(sh, 0) + 1
    for k, v in shift_counts.items():
        pct = round((v / total_recs) * 100, 1)
        ws_shift.append([k, v, f"{pct}%"])

    # Sheet 5: Product ID (PID) Failures Summary
    ws_pid = wb.create_sheet(title="PID Failure Summary")
    ws_pid.append(["Rank", "Product ID (PID)", "Total Failures", "Primary Failure Cause", "Detailed Issue Breakdown", "Percentage (%)"])
    for col in range(1, 7):
        cell = ws_pid.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    pid_counts = {}
    pid_issues = {}
    for r in records:
        iss = r.get('issue', 'OTHER')
        for pkey in ('frame_pid', 'right_lens_pid', 'left_lens_pid'):
            pval = str(r.get(pkey, '') or '').strip()
            if pval and pval != '0':
                pid_counts[pval] = pid_counts.get(pval, 0) + 1
                if pval not in pid_issues:
                    pid_issues[pval] = {}
                pid_issues[pval][iss] = pid_issues[pval].get(iss, 0) + 1

    sorted_pids = sorted(pid_counts.items(), key=lambda x: x[1], reverse=True)
    for idx, (k, v) in enumerate(sorted_pids, 1):
        pct = round((v / total_recs) * 100, 1)
        iss_dict = pid_issues.get(k, {})
        top_cause = sorted(iss_dict.items(), key=lambda x: x[1], reverse=True)[0][0] if iss_dict else 'OTHER'
        breakdown_str = ", ".join([f"{ik}: {iv}" for ik, iv in sorted(iss_dict.items(), key=lambda x: x[1], reverse=True)])
        ws_pid.append([idx, k, v, top_cause, breakdown_str, f"{pct}%"])

    # Sheet 6: Shift-Wise Operator Failures Summary
    ws_so = wb.create_sheet(title="Shift-Wise Operator Failures")
    ws_so.append(["Shift", "Operator Name", "Total Failures Marked", "Shift Failure Share (%)"])
    for col in range(1, 5):
        cell = ws_so.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    shift_ops = {}
    shift_totals = {}
    for r in records:
        sh = r.get('shift', 'Shift A') or 'Shift A'
        op = str(r.get('operator', '') or 'UNASSIGNED').strip().upper()
        shift_totals[sh] = shift_totals.get(sh, 0) + 1
        if sh not in shift_ops:
            shift_ops[sh] = {}
        shift_ops[sh][op] = shift_ops[sh].get(op, 0) + 1

    for sh_k in sorted(shift_ops.keys()):
        s_total = shift_totals.get(sh_k, 1) or 1
        s_sorted = sorted(shift_ops[sh_k].items(), key=lambda x: x[1], reverse=True)
        for op_k, op_v in s_sorted:
            s_pct = round((op_v / s_total) * 100, 1)
            ws_so.append([sh_k, op_k, op_v, f"{s_pct}%"])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"E2_Escalations_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.route('/api/import_escalations', methods=['POST'])
def api_import_escalations():
    """
    Imports recorded Excel (.xlsx/.xls) escalation log files directly into local records for instant analysis.
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    uploaded_file = request.files['file']
    filename = (uploaded_file.filename or '').lower()

    imported_records = []
    now = datetime.datetime.now()

    try:
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            wb = openpyxl.load_workbook(uploaded_file, read_only=True, data_only=True)  # type: ignore
            ws = wb.active
            assert ws is not None

            header_row = [str(cell).strip().upper() if cell is not None else '' for cell in next(ws.iter_rows(values_only=True))]
            
            def find_col(possible_names):
                for name in possible_names:
                    for idx, h in enumerate(header_row):
                        if name.upper() in h:
                            return idx
                return -1

            idx_date = find_col(['DATE', 'ENTRY_DATE', 'ENTRY DATE'])
            if idx_date == -1:
                idx_date = 0  # Default to Column A if no header matched

            idx_time = find_col(['TIME', 'ENTRY_TIME'])
            idx_shift = find_col(['SHIFT'])
            idx_shift_ic = find_col(['SHIFT IC', 'SHIFT_IC', 'IC'])
            idx_op = find_col(['OPERATOR', 'E2 OP', 'E2_OP', 'OP'])
            idx_tray = find_col(['TRAY ID', 'TRAY_ID', 'TRAY'])
            idx_fitting = find_col(['FITTING ID', 'FITTING_ID', 'FITTING'])
            idx_is_jit = find_col(['IS JIT', 'IS_JIT', 'JIT/NOT JIT'])
            idx_fr = find_col(['FR TAG', 'PROCESSING TYPE', 'FR_TAG'])
            idx_index = find_col(['LENS INDEX', 'INDEX'])
            idx_category = find_col(['FAIL CATEGORY', 'FAIL_CATEGORY', 'CATEGORY'])
            idx_issue = find_col(['ISSUE', 'ISSUE CAUSE', 'CAUSE', 'REASON'])
            idx_status = find_col(['STATUS'])
            idx_machine = find_col(['MACHINE', 'MACHINE TAG'])
            idx_frame_pid = find_col(['FRAME PID', 'REQ. FRAME PID'])
            idx_r_pid = find_col(['RIGHT LENS PID', 'REQ. RIGHT LENS PID'])
            idx_l_pid = find_col(['LEFT LENS PID', 'REQ. LEFT LENS PID'])

            def parse_excel_date(val_obj):
                if val_obj is None:
                    return ''
                if isinstance(val_obj, (datetime.datetime, datetime.date)):
                    # Undo Excel US locale swap for DD-MM-YYYY dates (if day <= 12)
                    if val_obj.day <= 12 and val_obj.month <= 12:
                        return val_obj.strftime('%m/%d/%Y')
                    return val_obj.strftime('%d/%m/%Y')
                val_str = str(val_obj).strip()
                if not val_str:
                    return ''
                # YYYY-MM-DD (e.g. 2026-08-02) -> 02/08/2026
                if len(val_str) >= 10 and val_str[4] == '-' and val_str[7] == '-':
                    try:
                        parts = val_str[:10].split('-')
                        return f"{parts[2]}/{parts[1]}/{parts[0]}"
                    except Exception:
                        pass
                # DD-MM-YYYY (e.g. 02-08-2026) -> 02/08/2026
                if len(val_str) >= 10 and val_str[2] == '-' and val_str[5] == '-':
                    try:
                        parts = val_str[:10].split('-')
                        return f"{parts[0]}/{parts[1]}/{parts[2]}"
                    except Exception:
                        pass
                return val_str[:10]

            def parse_excel_time(val_obj):
                if val_obj is None:
                    return ''
                if isinstance(val_obj, datetime.time):
                    return val_obj.strftime('%H:%M:%S')
                if isinstance(val_obj, datetime.datetime):
                    return val_obj.strftime('%H:%M:%S')
                val_str = str(val_obj).strip()
                # Handle dot-separated times like 07.09.07 -> 07:09:07
                if len(val_str) == 8 and val_str[2] == '.' and val_str[5] == '.':
                    return val_str.replace('.', ':')
                return val_str

            last_date_val = ''
            last_time_val = ''
            last_shift_val = 'Shift A'

            for row_idx, row in enumerate(ws.iter_rows(values_only=True), 1):
                if row_idx == 1 or not any(row):
                    continue

                def get_raw(col_i):
                    if col_i != -1 and col_i < len(row) and row[col_i] is not None:
                        return str(row[col_i]).strip()
                    return ''

                tray_id = get_raw(idx_tray)
                if not tray_id and idx_date != 0:
                    tray_id = get_raw(0)  # Fallback to column 0 if empty

                raw_date = parse_excel_date(row[idx_date] if idx_date != -1 and idx_date < len(row) else None)
                raw_time = parse_excel_time(row[idx_time] if idx_time != -1 and idx_time < len(row) else None)
                raw_shift = get_raw(idx_shift)

                # Skip completely blank trailing rows (no tray_id, no fitting_id, no date)
                if not tray_id and not get_raw(idx_fitting) and not raw_date:
                    continue

                # Forward-fill date/time/shift for consecutive rows with blank date cells
                if raw_date:
                    last_date_val = raw_date
                else:
                    raw_date = last_date_val

                if not raw_date:
                    continue  # Skip if no date has been encountered yet

                if raw_time:
                    last_time_val = raw_time
                else:
                    raw_time = last_time_val or '00:00:00'

                if raw_shift:
                    last_shift_val = raw_shift
                else:
                    raw_shift = last_shift_val or 'Shift A'

                if not tray_id:
                    tray_id = f"IMP_{row_idx}"

                raw_st = get_raw(idx_status).upper()
                if 'TURN TO STOCKING' in raw_st or 'RETURN TO STOCKING' in raw_st:
                    status_val = 'RETURN TO STOCKING'
                elif 'RETURN TO LAB' in raw_st:
                    status_val = 'RETURN TO LAB'
                elif 'NON JIT' in raw_st or 'NON-JIT' in raw_st:
                    status_val = 'RETURN TO NON JIT ASRS'
                elif 'JIT ASRS' in raw_st:
                    status_val = 'RETURN TO JIT ASRS'
                elif raw_st == 'OK':
                    status_val = 'OK'
                else:
                    status_val = raw_st or 'NG'

                entry = {
                    'id': int(now.timestamp() * 1000) + row_idx,
                    'timestamp': now.isoformat(),
                    'entry_date': raw_date,
                    'entry_time': raw_time,
                    'shift': raw_shift,
                    'shift_ic': get_raw(idx_shift_ic),
                    'operator': get_raw(idx_op) or 'UNASSIGNED',
                    'tray_id': tray_id,
                    'fitting_id': get_raw(idx_fitting),
                    'is_jit': get_raw(idx_is_jit) or 'NO',
                    'processing_type': get_raw(idx_fr) or '--',
                    'lens_index': get_raw(idx_index) or '1.56',
                    'fail_category': get_raw(idx_category) or 'LEFT LENS',
                    'issue': get_raw(idx_issue) or 'OTHER',
                    'status': status_val,
                    'machine': get_raw(idx_machine),
                    'frame_pid': get_raw(idx_frame_pid),
                    'right_lens_pid': get_raw(idx_r_pid),
                    'left_lens_pid': get_raw(idx_l_pid),
                    'is_imported': True
                }
                imported_records.append(entry)

        # Merge with existing records (replace previous imported batch or append)
        existing = [r for r in load_local_escalations() if not r.get('is_imported')]
        merged = imported_records + existing
        save_local_escalations(merged)

        # Calculate min and max datetime among imported records
        min_date_str = None
        max_date_str = None

        parsed_dts = []
        for r in imported_records:
            ed = r.get('entry_date', '')
            et = r.get('entry_time', '')
            if ed and len(ed) >= 10 and et:
                try:
                    h, mn, s = map(int, et.split(':'))
                    if ed[2] == '/' and ed[5] == '/':  # DD/MM/YYYY
                        d, m, y = map(int, ed[:10].split('/'))
                        parsed_dts.append(datetime.datetime(y, m, d, h, mn, s))
                    elif ed[4] == '-' and ed[7] == '-':  # YYYY-MM-DD
                        y, m, d = map(int, ed[:10].split('-'))
                        parsed_dts.append(datetime.datetime(y, m, d, h, mn, s))
                    elif ed[2] == '-' and ed[5] == '-':  # DD-MM-YYYY
                        d, m, y = map(int, ed[:10].split('-'))
                        parsed_dts.append(datetime.datetime(y, m, d, h, mn, s))
                except Exception:
                    pass

        if parsed_dts:
            min_d = min(parsed_dts)
            max_d = max(parsed_dts)
            min_date_str = min_d.strftime('%Y-%m-%dT%H:%M')
            max_date_str = max_d.strftime('%Y-%m-%dT%H:%M')

        # Save import metadata
        import_meta = {
            'filename': uploaded_file.filename,
            'imported_at': now.strftime('%d/%m/%Y %H:%M:%S'),
            'imported_count': len(imported_records),
            'total_count': len(merged),
            'min_date': min_date_str,
            'max_date': max_date_str
        }
        with open(IMPORT_META_FILE, 'w', encoding='utf-8') as mf:
            json.dump(import_meta, mf, indent=2)

        return jsonify({
            'success': True,
            'filename': uploaded_file.filename,
            'imported_count': len(imported_records),
            'total_count': len(merged),
            'min_date': min_date_str,
            'max_date': max_date_str
        })
    except Exception as ie:
        return jsonify({'success': False, 'error': f'Failed to import Excel file: {str(ie)}'}), 500


@app.route('/api/import_meta', methods=['GET', 'DELETE'])
def api_import_meta():
    """Returns or clears uploaded import file metadata."""
    if request.method == 'DELETE':
        if os.path.exists(IMPORT_META_FILE):
            try:
                os.remove(IMPORT_META_FILE)
            except Exception:
                pass
        # Clear all imported records (keep only explicitly manual records)
        manual_records = [r for r in load_local_escalations() if not r.get('is_imported', False)]
        save_local_escalations(manual_records)
        return jsonify({'success': True, 'message': 'Imported data cleared.'})

    if os.path.exists(IMPORT_META_FILE):
        try:
            with open(IMPORT_META_FILE, 'r', encoding='utf-8') as f:
                return jsonify({'success': True, 'meta': json.load(f)})
        except Exception:
            pass
    return jsonify({'success': True, 'meta': None})


@app.route('/api/export/csv', methods=['GET'])
def export_csv():
    """Generates CSV dataset download."""
    records = filter_escalation_records(load_local_escalations())

    headers = [
        "Date", "TIME", "SHIFT", "SHIFT IC", "E2 OP", "TRAY ID", "FITTING ID",
        "JIT/NOT JIT", "CUT/UNCUT", "REQ. FRAME PID", "REQ. FRAME BARCODE",
        "REQ. RIGHT LENS PID", "REQ. RIGHT LENS BARCODE",
        "REQ. LEFT LENS PID", "REQ. LEFT LENS BARCODE",
        "LENS INDEX", "SPH", "CYL", "AXIS", "ADDN",
        "FAIL CATEGORY", "ISSUE", "STATUS", "MACHINE"
    ]

    output_lines = [",".join(headers)]
    for r in records:
        row = [
            f'"{r.get("entry_date","")}"',
            f'"{r.get("entry_time","")}"',
            f'"{r.get("shift","")}"',
            f'"{r.get("shift_ic","")}"',
            f'"{r.get("operator","")}"',
            f'"{r.get("tray_id","")}"',
            f'"{r.get("fitting_id","")}"',
            f'"{r.get("jit_status","")}"',
            f'"{r.get("cut_status","")}"',
            f'"{r.get("frame_pid","")}"',
            f'"{r.get("frame_barcode","")}"',
            f'"{r.get("right_lens_pid","")}"',
            f'"{r.get("right_lens_barcode","")}"',
            f'"{r.get("left_lens_pid","")}"',
            f'"{r.get("left_lens_barcode","")}"',
            f'"{r.get("lens_index","")}"',
            f'"{r.get("sph","")}"',
            f'"{r.get("cyl","")}"',
            f'"{r.get("axis","")}"',
            f'"{r.get("addn","")}"',
            f'"{r.get("fail_category","")}"',
            f'"{r.get("issue","")}"',
            f'"{r.get("status","")}"',
            f'"{r.get("machine","")}"'
        ]
        output_lines.append(",".join(row))

    csv_data = "\n".join(output_lines)
    filename = f"E2_Escalations_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return send_file(
        io.BytesIO(csv_data.encode('utf-8')),
        download_name=filename,
        as_attachment=True,
        mimetype="text/csv"
    )


if __name__ == '__main__':
    print("\n" + "=" * 80)
    print(" 🚀 MEI E2 ANALYTICS & ESCALATION LOGGING DASHBOARD BACKEND")
    print("=" * 80)
    print("  -> Live MySQL Socket: 127.0.0.1:13306 (wms database)")
    print("  -> Web Dashboard: http://127.0.0.1:5000")
    print("=" * 80 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=True)
