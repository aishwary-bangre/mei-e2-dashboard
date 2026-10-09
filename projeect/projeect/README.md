# MEI Shape Correction System — Analytics Dashboard & Data Explorer

This project replaces the manual "MEI Shape Correction" Excel workbook with an automated, live interactive FastAPI + Plotly.js web application featuring both an **Analytics Dashboard** and a standalone **Data Explorer** query tool.

---

## ⚡ Data Explorer Features

1. **Header Navigation Switcher**:
   - **📈 Analytics Dashboard**: Plotly charts (Sankey, Heatmaps, SPC Control, Quartile Sequence Position), KPI cards, and summary audit.
   - **⚡ Data Explorer**: Fast, table-driven query tool separate from chart rendering.

2. **Five Sub-Views inside Data Explorer**:
   - **🔍 Single PID Query Lookup (`/api/explorer/pid/{pid}`)**: Type any PID to see every fail row (Period A & B) and every physical correction row (including superseded ones) side-by-side.
   - **📊 Unfiltered Classification Table (`/api/explorer/classifications`)**: Live-browsable table of all classified PIDs with column sorting, pagination, and status filters.
   - **🧬 RapidFuzz Cluster Inspector (`/api/explorer/clusters`)**: Dedicated view showing each discovered `rapidfuzz` cluster, canonical label, MEI tag, total count, and all raw strings merged into it.
   - **📁 Raw QC Fails Table (`/api/explorer/fails`)**: Paginated browser for raw QC Fails across Period A and Period B.
   - **📝 Physical Correction Log Table (`/api/explorer/corrections`)**: Paginated browser for physical correction log entries across all 20 sheets.

---

## 📡 API Endpoints

- `GET /api/status`: Active dataset dates & 500k row cap warning status
- `GET /api/metrics`: Core analytics summary & Plotly chart payloads
- `GET /api/explorer/pid/{pid}`: Single PID history lookup (side-by-side fails & corrections)
- `GET /api/explorer/classifications`: Paginated full PID classification table
- `GET /api/explorer/clusters`: RapidFuzz fuzzy string cluster inspector payload
- `GET /api/explorer/fails`: Paginated raw QC fails data
- `GET /api/explorer/corrections`: Paginated raw physical correction log data
- `GET /api/export_csv`: Classification CSV download

---

## 🚀 How to Run & Access

1. Open terminal in `projeect/`.
2. Execute startup script:
   ```bash
   ./run.sh
   ```
3. Open browser:
   **[http://localhost:8000](http://localhost:8000)**
