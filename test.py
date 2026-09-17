import sys, os
sys.path.insert(0, os.getcwd())
from app import get_fresh_db_connection

conn = get_fresh_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT oi.item_type, oi.product_id, oi.barcode FROM wms.tray_monitoring tm JOIN wms.order_items oi ON oi.fitting_id = tm.wms_fitting_id WHERE tm.tray_id='CT16015'")
print(cursor.fetchall())
