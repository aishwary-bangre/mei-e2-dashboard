from fastapi import FastAPI, UploadFile, File, HTTPException, Response, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import shutil
import os
import tempfile
import pandas as pd
import io
import uvicorn

from backend.analyzer import MEIAnalyzer

app = FastAPI(title="MEI Shape Correction Dashboard & Data Explorer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = tempfile.mkdtemp(prefix="mei_dashboard_")

DEFAULT_PAST = "QC Raw Data-2.xlsx"
DEFAULT_THIS = "QC Raw Data-3.xlsx"
DEFAULT_LOG = "/Users/khushi.bodhwani_240893/Downloads/MEI SHAPE CORRECTION .xlsx"

session_past_path = DEFAULT_PAST
session_this_path = DEFAULT_THIS

analyzer_instance: Optional[MEIAnalyzer] = None

def init_analyzer():
    global analyzer_instance, session_past_path, session_this_path
    past_path = session_past_path if os.path.exists(session_past_path) else DEFAULT_PAST
    this_path = session_this_path if os.path.exists(session_this_path) else DEFAULT_THIS
    
    if os.path.exists(past_path) and os.path.exists(this_path):
        try:
            print(f"Initializing MEIAnalyzer with:\n  Period A: {past_path}\n  Period B: {this_path}")
            analyzer_instance = MEIAnalyzer(past_path, this_path, DEFAULT_LOG)
            print("MEIAnalyzer startup initialization successful.")
        except Exception as e:
            print(f"Startup initialization error: {e}")
            analyzer_instance = None
            raise RuntimeError(f"Error parsing uploaded data: {e}")

@app.on_event("startup")
async def startup_event():
    try:
        init_analyzer()
    except Exception as e:
        print(f"Startup warning: {e}")

@app.get("/api/status")
async def get_status():
    global analyzer_instance
    if analyzer_instance is not None:
        return {
            "uploaded": True,
            "week_past_label": analyzer_instance.week_past_label,
            "week_this_label": analyzer_instance.week_this_label,
            "row_cap_warning": analyzer_instance.row_cap_warning,
            "row_cap_notes": analyzer_instance.row_cap_notes
        }
    return {
        "uploaded": False,
        "message": "No sample data loaded."
    }

@app.post("/api/upload/period_a")
async def upload_period_a(file: UploadFile = File(...)):
    global session_past_path, analyzer_instance
    try:
        temp_path = os.path.join(TEMP_DIR, f"period_a_{file.filename}")
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        session_past_path = temp_path
        init_analyzer()
        return {
            "success": True,
            "message": "Period A file uploaded to session.",
            "week_past_label": analyzer_instance.week_past_label if analyzer_instance else "Period A",
            "row_cap_warning": analyzer_instance.row_cap_warning if analyzer_instance else False
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process Period A upload: {str(e)}")

@app.post("/api/upload/period_b")
async def upload_period_b(file: UploadFile = File(...)):
    global session_this_path, analyzer_instance
    try:
        temp_path = os.path.join(TEMP_DIR, f"period_b_{file.filename}")
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        session_this_path = temp_path
        init_analyzer()
        return {
            "success": True,
            "message": "Period B file uploaded to session.",
            "week_this_label": analyzer_instance.week_this_label if analyzer_instance else "Period B",
            "row_cap_warning": analyzer_instance.row_cap_warning if analyzer_instance else False
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process Period B upload: {str(e)}")

@app.get("/api/metrics")
async def get_metrics():
    global analyzer_instance
    if analyzer_instance is None:
        raise HTTPException(status_code=400, detail="Analyzer not initialized.")
    try:
        return analyzer_instance.analyze()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error computing metrics: {str(e)}")

class DrilldownRequest(BaseModel):
    category_type: str
    filter_value: str
    filter_secondary: Optional[str] = None

@app.post("/api/drilldown")
async def get_drilldown(req: DrilldownRequest):
    global analyzer_instance
    if analyzer_instance is None:
        raise HTTPException(status_code=400, detail="Analyzer not initialized.")
        
    analysis = analyzer_instance.analyze()
    all_pids = analysis["classified_pids"]
    
    filtered = []
    if req.category_type in ["sankey_outcome", "pareto"]:
        filtered = [p for p in all_pids if p["classification"] == req.filter_value or p["reason_cluster"] == req.filter_value]
    elif req.category_type in ["heatmap_machine", "machine"]:
        filtered = [p for p in all_pids if p["qc_person_id"] == req.filter_value]
    elif req.category_type == "machine_outcome":
        filtered = [p for p in all_pids if p["qc_person_id"] == req.filter_value and (not req.filter_secondary or p["classification"] == req.filter_secondary)]
    elif req.category_type == "heatmap_vendor":
        filtered = [p for p in all_pids if p["vendor_invoice_number"] == req.filter_value and (not req.filter_secondary or p["pid"] == req.filter_secondary)]
    else:
        filtered = all_pids
        
    return {"count": len(filtered), "pids": filtered}

@app.get("/api/export_csv")
async def export_csv():
    global analyzer_instance
    if analyzer_instance is None:
        raise HTTPException(status_code=400, detail="Analyzer not initialized.")
        
    analysis = analyzer_instance.analyze()
    df_export = pd.DataFrame(analysis["classified_pids"])
    
    stream = io.StringIO()
    df_export.to_csv(stream, index=False)
    
    return Response(
        content=stream.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=mei_pid_classification.csv"}
    )

# ==========================================
# DATA EXPLORER API ENDPOINTS
# ==========================================

@app.get("/api/explorer/fails")
async def get_explorer_fails(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    search: str = Query(""),
    sort_by: str = Query("QC_created_date"),
    sort_order: str = Query("desc"),
    period: str = Query("all")
):
    global analyzer_instance
    if analyzer_instance is None:
        raise HTTPException(status_code=400, detail="Analyzer not initialized.")
    return analyzer_instance.get_explorer_fails(page, limit, search, sort_by, sort_order, period)

@app.get("/api/explorer/corrections")
async def get_explorer_corrections(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    search: str = Query(""),
    sort_by: str = Query("timestamp"),
    sort_order: str = Query("desc")
):
    global analyzer_instance
    if analyzer_instance is None:
        raise HTTPException(status_code=400, detail="Analyzer not initialized.")
    return analyzer_instance.get_explorer_corrections(page, limit, search, sort_by, sort_order)

@app.get("/api/explorer/clusters")
async def get_explorer_clusters():
    global analyzer_instance
    if analyzer_instance is None:
        raise HTTPException(status_code=400, detail="Analyzer not initialized.")
    return analyzer_instance.get_explorer_clusters()

@app.get("/api/explorer/pid/{pid}")
async def get_explorer_pid(pid: str):
    global analyzer_instance
    if analyzer_instance is None:
        raise HTTPException(status_code=400, detail="Analyzer not initialized.")
    return analyzer_instance.get_explorer_pid_history(pid)

@app.get("/api/explorer/classifications")
async def get_explorer_classifications(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    search: str = Query(""),
    sort_by: str = Query("pid"),
    sort_order: str = Query("asc"),
    status: str = Query("all")
):
    global analyzer_instance
    if analyzer_instance is None:
        raise HTTPException(status_code=400, detail="Analyzer not initialized.")
    return analyzer_instance.get_explorer_classifications(page, limit, search, sort_by, sort_order, status)

class DimEntry(BaseModel):
    date: Optional[str] = None
    a: Optional[float] = None
    b: Optional[float] = None
    circ_r: Optional[float] = None
    circ_l: Optional[float] = None
    a1: Optional[float] = None
    b1: Optional[float] = None
    circ_r1: Optional[float] = None
    circ_l1: Optional[float] = None
    percentage_dev: Optional[float] = None

class ManualCorrectionRequest(BaseModel):
    id: Optional[str] = None
    pid: str
    pid_invoice: Optional[str] = None   # exact PID.Invoice as entered
    done_by: str = "Operator"
    timestamp: Optional[str] = None
    issue_raw: str = "Wrong shape cut by machine"
    percentage_dev: Optional[float] = None
    a: Optional[float] = None
    b: Optional[float] = None
    circ_r: Optional[float] = None
    circ_l: Optional[float] = None
    a1: Optional[float] = None
    b1: Optional[float] = None
    circ_r1: Optional[float] = None
    circ_l1: Optional[float] = None
    notes: Optional[str] = None
    dim_entries: Optional[List[DimEntry]] = None  # daily dimension readings

@app.get("/api/manual_corrections")
async def get_manual_corrections():
    global analyzer_instance
    if analyzer_instance is None:
        return []
    return analyzer_instance.get_manual_corrections()

@app.post("/api/manual_corrections")
async def create_manual_correction(req: ManualCorrectionRequest):
    global analyzer_instance
    if analyzer_instance is None:
        raise HTTPException(status_code=400, detail="Analyzer not initialized.")
    
    saved = analyzer_instance.save_manual_correction(req.dict())
    updated_analysis = analyzer_instance.analyze()
    return {
        "success": True,
        "message": f"Manual correction saved for PID {req.pid}.",
        "entry": saved,
        "summary": updated_analysis["summary"]
    }

@app.delete("/api/manual_corrections/{entry_id}")
async def delete_manual_correction(entry_id: str):
    global analyzer_instance
    if analyzer_instance is None:
        raise HTTPException(status_code=400, detail="Analyzer not initialized.")
    
    ok = analyzer_instance.delete_manual_correction(entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Manual correction entry not found.")
    
    updated_analysis = analyzer_instance.analyze()
    return {
        "success": True,
        "message": "Manual correction removed.",
        "summary": updated_analysis["summary"]
    }

@app.get("/api/explorer/master/summary")
async def get_master_summary():
    global analyzer_instance
    if analyzer_instance is None:
        raise HTTPException(status_code=400, detail="Analyzer not initialized.")
    return analyzer_instance.get_master_summary()

@app.get("/api/explorer/master")
async def get_explorer_master(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    search: str = Query(""),
    type: str = Query("all"),
    date_from: str = Query(""),
    date_to: str = Query(""),
    sort_order: str = Query("desc")
):
    global analyzer_instance
    if analyzer_instance is None:
        raise HTTPException(status_code=400, detail="Analyzer not initialized.")
    return analyzer_instance.get_explorer_master(page, limit, search, type, date_from, date_to, sort_order)

@app.get("/api/explorer/master/export")
async def export_master(
    search: str = Query(""),
    type: str = Query("all"),
    date_from: str = Query(""),
    date_to: str = Query(""),
    sort_order: str = Query("asc")
):
    global analyzer_instance
    if analyzer_instance is None:
        raise HTTPException(status_code=400, detail="Analyzer not initialized.")
    df = analyzer_instance.export_master_rows(search, type, date_from, date_to, sort_order)
    stream = io.StringIO()
    df.to_csv(stream, index=False)
    return Response(content=stream.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=master_database.csv"})

class DimsUpdateRequest(BaseModel):
    a: Optional[float] = None
    b: Optional[float] = None
    circ_r: Optional[float] = None
    circ_l: Optional[float] = None
    a1: Optional[float] = None
    b1: Optional[float] = None
    circ_r1: Optional[float] = None
    circ_l1: Optional[float] = None

@app.patch("/api/manual_corrections/{entry_id}/dims")
async def update_manual_dims(entry_id: str, req: DimsUpdateRequest):
    """Daily update of A/B/CIRC R/CIRC L (before) and A1/B1/CIRC R1/CIRC L1 (after)."""
    global analyzer_instance
    if analyzer_instance is None:
        raise HTTPException(status_code=400, detail="Analyzer not initialized.")
    entry = analyzer_instance.update_manual_dims(entry_id, req.dict())
    if entry is None:
        raise HTTPException(status_code=404, detail="Only manual entries can be edited (id not found).")
    return {"success": True, "entry": entry}

os.makedirs("frontend", exist_ok=True)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
