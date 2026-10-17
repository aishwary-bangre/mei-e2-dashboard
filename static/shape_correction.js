let globalData = null;

// Explorer state management
const expClassState = { page: 1, limit: 50, search: "", sort_by: "pid", sort_order: "asc", status: "all" };
const expFailsState = { page: 1, limit: 50, search: "", sort_by: "QC_created_date", sort_order: "desc", period: "all" };
const expMasterState = { page: 1, limit: 50, search: "", sort_by: "date", sort_order: "desc", type: "all", date_from: "", date_to: "" };
const expCorrState = { page: 1, limit: 50, search: "", sort_by: "timestamp", sort_order: "desc" };

let shapeCorrectionInitialized = false;
let scDateFrom = '';
let scDateTo = '';

function initShapeCorrectionTab() {
    if (!shapeCorrectionInitialized) {
        setupDropzones();
        setupMainTabs();
        setupExplorerSubtabs();
        setupExplorerControls();
        setupRecentCorrectionsLog();
        setupControlStrip();
        setupLoggingStrip();
        setupShapeHeaderControls();

        const btnClose = document.getElementById('btn-close-modal');
        if (btnClose) {
            btnClose.addEventListener('click', () => {
                const dm = document.getElementById('drilldown-modal');
                if (dm) dm.classList.add('hidden');
            });
        }
        shapeCorrectionInitialized = true;
    }
    checkStatus();
    loadRecentCorrections();
}

function switchShapeSubView(viewId) {
    const map = {
        'analytics': 'tab-btn-analytics',
        'explorer': 'tab-btn-explorer',
        'impact': 'tab-btn-impact'
    };
    const btnId = map[viewId] || 'tab-btn-analytics';
    const btn = document.getElementById(btnId);
    if (btn) btn.click();
}

document.addEventListener('DOMContentLoaded', () => {
    const activeSys = localStorage.getItem('mei_active_system');
    const activeTab = localStorage.getItem('mei_active_tab');
    if (activeSys === 'shape' || activeTab === 'tab3') {
        initShapeCorrectionTab();
    }
});

// =====================
// SHAPE HEADER CONTROLS
// =====================
function setupShapeHeaderControls() {
    // 1. Shift: Auto-select current shift based on hour or restore from localStorage
    const shiftSel = document.getElementById('scHeaderShift');
    if (shiftSel) {
        const savedShift = localStorage.getItem('sc_shift');
        if (savedShift) {
            shiftSel.value = savedShift;
        } else {
            const hour = new Date().getHours();
            if (hour >= 6 && hour < 14) shiftSel.value = 'Shift A';
            else if (hour >= 14 && hour < 22) shiftSel.value = 'Shift B';
            else shiftSel.value = 'Shift C';
        }
        shiftSel.addEventListener('change', () => {
            localStorage.setItem('sc_shift', shiftSel.value);
        });
    }

    // 2. Populate Shift IC & Operator dropdowns
    populateShapeHeaderDropdowns();
}

async function populateShapeHeaderDropdowns() {
    let opts = (typeof cachedDropdownOptions !== 'undefined' && cachedDropdownOptions) ? cachedDropdownOptions : null;
    if (!opts || !opts.shift_ic || !opts.operator) {
        try {
            const res = await fetch('/api/options');
            const data = await res.json();
            if (data.success && data.options) {
                opts = data.options;
                if (typeof cachedDropdownOptions !== 'undefined') {
                    cachedDropdownOptions = opts;
                }
            }
        } catch (e) {
            console.error('Failed to load options for shape header:', e);
        }
    }

    const shiftIcSel = document.getElementById('scHeaderShiftIc');
    if (shiftIcSel && opts && opts.shift_ic) {
        const curVal = localStorage.getItem('sc_shift_ic') || shiftIcSel.value;
        shiftIcSel.innerHTML = opts.shift_ic.map(o => `<option value="${o}">${o}</option>`).join('');
        if (curVal && opts.shift_ic.includes(curVal)) {
            shiftIcSel.value = curVal;
        } else if (opts.shift_ic.length > 0) {
            shiftIcSel.value = opts.shift_ic[0];
        }
        shiftIcSel.onchange = () => localStorage.setItem('sc_shift_ic', shiftIcSel.value);
    }

    const opSel = document.getElementById('scHeaderOperator');
    if (opSel && opts && opts.operator) {
        const curVal = localStorage.getItem('sc_operator') || opSel.value;
        opSel.innerHTML = opts.operator.map(o => `<option value="${o}">${o}</option>`).join('');
        if (curVal && opts.operator.includes(curVal)) {
            opSel.value = curVal;
        } else if (opts.operator.length > 0) {
            opSel.value = opts.operator[0];
        }
        opSel.onchange = () => localStorage.setItem('sc_operator', opSel.value);
    }
}
window.populateShapeHeaderDropdowns = populateShapeHeaderDropdowns;

// =====================
// CONTROL STRIP SETUP
// =====================
function setupControlStrip() {
    // Import Correction Sheet
    const importBtn = document.getElementById('btn-import-corrections');
    const importInput = document.getElementById('input-import-corrections');
    const importStatus = document.getElementById('lbl-import-status');
    if (importBtn && importInput) {
        importBtn.addEventListener('click', () => importInput.click());
        importInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) uploadImportCorrections(e.target.files[0], importStatus);
        });
    }

    // Date filter
    const applyBtn = document.getElementById('btn-sc-date-apply');
    const clearBtn = document.getElementById('btn-sc-date-clear');
    if (applyBtn) applyBtn.addEventListener('click', () => {
        scDateFrom = document.getElementById('sc-date-from').value;
        scDateTo   = document.getElementById('sc-date-to').value;
        fetchMetrics();
    });
    if (clearBtn) clearBtn.addEventListener('click', () => {
        document.getElementById('sc-date-from').value = '';
        document.getElementById('sc-date-to').value = '';
        scDateFrom = ''; scDateTo = '';
        fetchMetrics();
    });

    // Corrections log export
    const expLog = document.getElementById('btn-sc-export-corrections-log');
    if (expLog) expLog.addEventListener('click', () => {
        const from = document.getElementById('sc-date-from').value;
        const to   = document.getElementById('sc-date-to').value;
        let url = '/api/shape/export/corrections_log';
        const params = [];
        if (from) params.push(`date_from=${from}`);
        if (to)   params.push(`date_to=${to}`);
        if (params.length) url += '?' + params.join('&');
        window.location = url;
    });
}

// =====================
// LOGGING STRIP SETUP
// =====================
function setupLoggingStrip() {
    // Restore persisted operator / shift IC
    ['sc_shift_ic', 'sc_operator'].forEach(key => {
        const el = document.querySelector(`[data-persist="${key}"]`);
        if (el) {
            const saved = localStorage.getItem(key);
            if (saved) el.value = saved;
            el.addEventListener('change', () => localStorage.setItem(key, el.value));
        }
    });

    // Auto-set timestamp to now
    const tsInput = document.getElementById('sc-log-timestamp');
    if (tsInput && !tsInput.value) {
        const now = new Date();
        tsInput.value = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    }

    // Collapse toggle
    const collapseBtn = document.getElementById('btn-sc-log-collapse');
    const logBody = document.getElementById('sc-log-body');
    if (collapseBtn && logBody) {
        collapseBtn.addEventListener('click', () => {
            const collapsed = logBody.classList.toggle('collapsed');
            collapseBtn.textContent = collapsed ? '▼' : '▲';
        });
    }

    // Dimensions toggle
    const dimsToggle = document.getElementById('btn-sc-dims-toggle');
    const dimsPanel = document.getElementById('sc-log-dims');
    if (dimsToggle && dimsPanel) {
        dimsToggle.addEventListener('click', () => {
            const shown = dimsPanel.classList.toggle('hidden');
            dimsToggle.classList.toggle('active', !shown);
            dimsToggle.textContent = shown ? '+ Dimensions' : '− Dimensions';
        });
    }

    // Custom reason toggle
    const issueSelect = document.getElementById('sc-log-issue');
    const customRow = document.getElementById('sc-log-custom-row');
    if (issueSelect && customRow) {
        issueSelect.addEventListener('change', () => {
            customRow.classList.toggle('hidden', issueSelect.value !== 'OTHER');
        });
    }

    // Submit
    const submitBtn = document.getElementById('btn-sc-log-submit');
    if (submitBtn) submitBtn.addEventListener('click', saveInlineCorrection);
}

async function uploadImportCorrections(file, statusEl) {
    const importBtn = document.getElementById('btn-import-corrections');
    const origText = importBtn ? importBtn.innerHTML : '📥 Import Correction Sheet';
    if (importBtn) { importBtn.disabled = true; importBtn.innerHTML = '⏳ Importing...'; }
    if (statusEl) statusEl.innerHTML = `<span style="color:#38bdf8;">⏳ Uploading ${escHtml(file.name)}...</span>`;
    showScLoading(`Importing ${file.name}: Parsing 'Tracing New Correction' sheet...`);

    const formData = new FormData();
    formData.append('file', file);
    try {
        const res = await fetch('/api/shape/import_corrections', { method: 'POST', body: formData });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || data.error || 'Import failed');
        if (statusEl) statusEl.innerHTML = `<span style="color:#10b981; font-weight:600;">✓ ${data.imported} imported</span> <span style="color:var(--text-muted);">(${data.skipped} skipped)</span>`;
        showScLoading("Updating metrics and recalculating correction impact...");
        await checkStatus();
        await loadRecentCorrections();
    } catch (e) {
        if (statusEl) statusEl.innerHTML = `<span style="color:#ef4444;">✗ ${escHtml(e.message)}</span>`;
        alert(`Import failed: ${e.message}`);
    } finally {
        if (importBtn) { importBtn.disabled = false; importBtn.innerHTML = origText; }
        hideScLoading();
    }
}

async function saveInlineCorrection() {
    const pid = (document.getElementById('sc-log-pid').value || '').trim();
    if (!pid) { showLogFeedback('PID / Invoice is required.', 'error'); return; }

    const correctionType = (document.getElementById('sc-log-type') || {}).value || 'Traced';

    const issueRaw = document.getElementById('sc-log-issue').value === 'OTHER'
        ? (document.getElementById('sc-log-issue-custom').value.trim() || 'Other')
        : document.getElementById('sc-log-issue').value;

    const shift    = (document.getElementById('scHeaderShift') || {}).value || 'Shift A';
    const shiftIc  = (document.getElementById('scHeaderShiftIc') || {}).value || '';
    const operator = (document.getElementById('scHeaderOperator') || {}).value || '';
    const ts       = document.getElementById('sc-log-timestamp').value;

    const floatOrNull = (id) => {
        const v = document.getElementById(id).value;
        const n = parseFloat(v);
        return isNaN(n) ? null : n;
    };

    const payload = {
        pid, pid_invoice: pid,
        correction_type: correctionType,
        issue_raw: issueRaw,
        shift: shift,
        shift_ic: shiftIc,
        done_by: operator,
        timestamp: ts ? ts.replace('T', ' ') + ':00' : null,
        percentage_dev: floatOrNull('sc-dim-dev'),
        a:  floatOrNull('sc-dim-a'),  b:  floatOrNull('sc-dim-b'),
        circ_r: floatOrNull('sc-dim-cr'), circ_l: floatOrNull('sc-dim-cl'),
        a1: floatOrNull('sc-dim-a1'), b1: floatOrNull('sc-dim-b1'),
        circ_r1: floatOrNull('sc-dim-cr1'), circ_l1: floatOrNull('sc-dim-cl1'),
        notes: document.getElementById('sc-dim-notes').value.trim()
    };

    const btn = document.getElementById('btn-sc-log-submit');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    try {
        const res = await fetch('/api/shape/manual_corrections', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || 'Save failed');

        // Reset form
        document.getElementById('sc-log-pid').value = '';
        // Reset timestamp to now
        const now = new Date();
        document.getElementById('sc-log-timestamp').value =
            new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
        // Collapse dims
        const dimsPanel = document.getElementById('sc-log-dims');
        if (dimsPanel && !dimsPanel.classList.contains('hidden')) {
            dimsPanel.classList.add('hidden');
            const t = document.getElementById('btn-sc-dims-toggle');
            if (t) { t.classList.remove('active'); t.textContent = '+ Dimensions'; }
        }
        showLogFeedback(`✓ Correction saved for PID ${pid}`, 'success');
        await loadRecentCorrections();
        await fetchMetrics();
        if (currentLookupPID && currentLookupPID === pid) fetchPIDHistory(pid);
    } catch (e) {
        showLogFeedback(`✗ ${e.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '✓ Log Correction';
    }
}

function showLogFeedback(msg, type) {
    const fb = document.getElementById('sc-log-feedback');
    if (!fb) return;
    fb.textContent = msg;
    fb.className = `sc-log-feedback ${type}`;
    fb.classList.remove('hidden');
    setTimeout(() => fb.classList.add('hidden'), 4000);
}


// =====================
// LOADING BANNER HELPERS
// =====================
function showScLoading(text) {
    const banner = document.getElementById('sc-global-loading');
    const label = document.getElementById('sc-global-loading-text');
    if (banner && label) {
        label.textContent = text || 'Loading Shape Correction Data...';
        banner.classList.remove('hidden');
    }
}

function hideScLoading() {
    const banner = document.getElementById('sc-global-loading');
    if (banner) banner.classList.add('hidden');
}

// =====================
// STATUS & DATA LOADING
// =====================
async function checkStatus() {
    showScLoading("Checking shape analyzer & correction data...");
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        if (data.uploaded) {
            updateLabels(data);
            await fetchMetrics();
        }
    } catch (e) {
        console.error("Status check failed:", e);
    } finally {
        hideScLoading();
    }
}

function updateLabels(data) {
    if (data.week_past_label) {
        const elPast = document.getElementById('lbl-past-period');
        if (elPast) elPast.innerText = data.week_past_label;
        const elStatA = document.getElementById('lbl-period-a-status');
        if (elStatA) elStatA.innerText = `Loaded: ${data.week_past_label}`;
    }
    if (data.week_this_label) {
        const elThis = document.getElementById('lbl-this-period');
        if (elThis) elThis.innerText = data.week_this_label;
        const elStatB = document.getElementById('lbl-period-b-status');
        if (elStatB) elStatB.innerText = `Loaded: ${data.week_this_label}`;
    }

    // Update Correction Sheet indicator
    if (data.correction_sheet) {
        const cs = data.correction_sheet;
        const dotEl = document.getElementById('dot-corr-status');
        const infoEl = document.getElementById('lbl-corr-sheet-info');
        const importStatusEl = document.getElementById('lbl-import-status');
        if (cs.loaded) {
            if (dotEl) { dotEl.className = 'period-dot corr'; dotEl.style.background = '#10b981'; }
            if (infoEl) { infoEl.innerHTML = `<span style="color:#10b981; font-weight:600;">Loaded (${cs.rows_count} rows • ${escHtml(cs.sheet_name)})</span>`; }
            if (importStatusEl) {
                importStatusEl.innerHTML = `<span style="color:#10b981; font-weight:600;">✓ Active:</span> ${escHtml(cs.file_name)} (${cs.rows_count} rows)`;
                importStatusEl.title = `File: ${cs.file_name}\nSheet: ${cs.sheet_name}\nRows: ${cs.rows_count}\nTotal Logged: ${cs.total_corrections}`;
            }
        } else {
            if (dotEl) { dotEl.className = 'period-dot corr-missing'; dotEl.style.background = '#f59e0b'; }
            if (infoEl) { infoEl.innerHTML = `<span style="color:#f59e0b;">Not Loaded (Click 'Import Correction Sheet' above)</span>`; }
            if (importStatusEl) { importStatusEl.textContent = 'No sheet loaded'; }
        }
    }

    const banner = document.getElementById('row-cap-warning-banner');
    if (banner) {
        if (data.row_cap_notes && data.row_cap_notes.length) {
            const wt = banner.querySelector('.warning-text');
            if (wt) wt.innerHTML = `<strong>Warning:</strong> ${data.row_cap_notes.map(escHtml).join(' ')} Re-export in smaller date ranges to get complete numbers.`;
        }
        if (data.row_cap_warning) {
            banner.classList.remove('hidden');
        } else {
            banner.classList.add('hidden');
        }
    }
}

function setupDropzones() {
    setupZone('dropzone-period-a', 'input-period-a', '/api/upload/period_a', 'lbl-period-a-status');
    setupZone('dropzone-period-b', 'input-period-b', '/api/upload/period_b', 'lbl-period-b-status');
}

function setupZone(zoneId, inputId, apiUrl, labelId) {
    const zone = document.getElementById(zoneId);
    const input = document.getElementById(inputId);
    const label = document.getElementById(labelId);
    if (!zone || !input || !label) return;

    zone.addEventListener('click', (e) => {
        if (e.target !== input) {
            input.click();
        }
    });
    input.addEventListener('click', (e) => e.stopPropagation());
    zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('dragover'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) uploadFile(e.dataTransfer.files[0], apiUrl, label);
    });
    input.addEventListener('change', (e) => {
        if (e.target.files.length > 0) uploadFile(e.target.files[0], apiUrl, label);
    });
}

async function uploadFile(file, apiUrl, labelEl) {
    labelEl.innerText = `Uploading ${file.name}...`;
    showScLoading(`Uploading ${file.name} & re-computing shift trends...`);
    const formData = new FormData();
    formData.append('file', file);
    try {
        const res = await fetch(apiUrl, { method: 'POST', body: formData });
        if (!res.ok) {
            let errorMsg = "Upload failed";
            try {
                const errJson = await res.json();
                if (errJson.detail) errorMsg = errJson.detail;
                else if (errJson.error) errorMsg = errJson.error;
            } catch (_) {}
            throw new Error(errorMsg);
        }
        const data = await res.json();
        labelEl.innerText = `Loaded: ${file.name}`;
        updateLabels(data);
        await fetchMetrics();
    } catch (e) {
        alert(e.message);
        labelEl.innerText = "Upload failed. Try again.";
    } finally {
        hideScLoading();
    }
}

// =====================
// METRICS FETCH & RENDER
// =====================
async function fetchMetrics() {
    try { await fetchMetricsCore(); } finally { refreshImpactIfOpen(); }
}

async function fetchMetricsCore() {
    showScLoading("Loading shape metrics & Pareto charts...");
    try {
        const params = new URLSearchParams();
        if (scDateFrom) params.set('date_from', scDateFrom);
        if (scDateTo)   params.set('date_to', scDateTo);
        const url = '/api/metrics' + (params.toString() ? '?' + params.toString() : '');
        const res = await fetch(url);
        if (!res.ok) throw new Error("Error fetching metrics");
        const data = await res.json();
        globalData = data;

        renderKPIs(data.summary);
        renderPeriodBReasonsChart(data.pareto);
        renderShiftDriftChart(data.shift_drift);
        renderCorrectionEffectiveness(data.correction_effectiveness, data.summary);
        renderActionList(data.action_list);
    } catch (e) {
        console.error("Fetch metrics error:", e);
    } finally {
        hideScLoading();
    }
}

function getPlotBase() {
    const isLight = document.body.classList.contains('light-theme');
    return {
        font: { family: 'Inter', color: isLight ? '#475569' : '#8b949e', size: 11 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        margin: { l: 45, r: 15, t: 10, b: 70 },
        legend: { orientation: 'h', y: -0.25, font: { color: isLight ? '#0F172A' : '#f0f2f5', size: 11 } },
        yaxis: { gridcolor: isLight ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.08)', zeroline: false },
        xaxis: { gridcolor: isLight ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.08)' },
        barmode: 'group',
        dragmode: false,
        hovermode: 'closest'
    };
}
const PLOT_BASE = getPlotBase();

function renderAllShapeCharts() {
    if (typeof globalData !== 'undefined' && globalData) {
        if (typeof renderPeriodBReasonsChart === 'function') renderPeriodBReasonsChart(globalData.pareto);
        if (typeof renderShiftDriftChart === 'function') renderShiftDriftChart(globalData.shift_drift);
        if (typeof renderCorrectionEffectiveness === 'function') renderCorrectionEffectiveness(globalData.correction_effectiveness, globalData.summary);
    }
}
window.renderAllShapeCharts = renderAllShapeCharts;

const COLOR_A = '#8b949e', COLOR_B = '#00b0ff';

function changeText(a, b, unit, pct) {
    if (!a && !b) return '';
    const d = b - a;
    const arrow = d > 0 ? '▲' : (d < 0 ? '▼' : '=');
    return pct && a ? `${arrow} ${Math.abs(d / a * 100).toFixed(0)}%` : `${arrow} ${Math.abs(d).toFixed(2)}${unit}`;
}

function renderKPIs(s) {
    document.getElementById('kpi-fail-rate').innerText = `${s.fail_rate_b}%`;
    document.getElementById('kpi-fail-rate-desc').innerText =
        `A: ${s.fail_rate_a}% (${changeText(s.fail_rate_a, s.fail_rate_b, ' pts')}) · ${s.events_b.toLocaleString()} of ${s.qc_done_b.toLocaleString()} QC'd`;
    document.getElementById('kpi-machine-failures').innerText = s.events_b.toLocaleString();
    document.getElementById('kpi-events-desc').innerText =
        `A: ${s.events_a.toLocaleString()} (${changeText(s.events_a, s.events_b, '', true)}) · ${s.pids_b} PIDs in B`;
    document.getElementById('kpi-corrected').innerText = (s.corrected || 0).toLocaleString();
    document.getElementById('kpi-recurred').innerText = s.recurred.toLocaleString();
    document.getElementById('kpi-pending').innerText = s.pending.toLocaleString();
}

// -----------------------------------------------------------------------------
// TOP REASONS OF FAILURE (STRICTLY FOR PERIOD B) - SPAN-2
// -----------------------------------------------------------------------------
function renderPeriodBReasonsChart(pareto) {
    const el = document.getElementById('chart-period-b-reasons');
    if (!el) return;
    if (!pareto || !Array.isArray(pareto)) return;
    const isLight = document.body.classList.contains('light-theme');

    // Extract Period B failures only, filter out 0s, and sort ascending so top (worst) reason is on top
    const bItems = pareto
        .map(p => ({ reason: p.reason, count: Number(p.b) || 0 }))
        .filter(p => p.count > 0)
        .sort((x, y) => x.count - y.count);

    if (bItems.length === 0) {
        el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-size:0.85rem;">No failure records found for Period B</div>';
        return;
    }

    const totalB = bItems.reduce((acc, cur) => acc + cur.count, 0);
    const yReasons = bItems.map(p => p.reason);
    const xCounts = bItems.map(p => p.count);
    const textLabels = bItems.map(p => {
        const pct = totalB > 0 ? ((p.count / totalB) * 100).toFixed(1) : '0.0';
        return ` <b>${p.count}</b> (${pct}%)`;
    });

    // Dynamic gradient color: largest reason gets brightest cyan accent
    const colors = bItems.map((_, i) => {
        const ratio = (i + 1) / bItems.length;
        return isLight ? `rgba(2, 132, 199, ${0.4 + 0.6 * ratio})` : `rgba(0, 242, 254, ${0.45 + 0.55 * ratio})`;
    });

    const trace = {
        type: 'bar',
        orientation: 'h',
        x: xCounts,
        y: yReasons,
        marker: {
            color: colors,
            line: {
                color: isLight ? '#0284C7' : '#00F2FE',
                width: 1.5
            }
        },
        text: textLabels,
        textposition: 'outside',
        textfont: {
            color: isLight ? '#0F172A' : '#F8FAFC',
            size: 11,
            family: 'Inter, sans-serif'
        },
        hovertemplate: '<b>%{y}</b><br>Period B Failures: <b>%{x} lenses</b><br>Share: <b>%{text}</b><extra>Period B Only</extra>'
    };

    const maxCount = Math.max(...xCounts, 10);
    const base = getPlotBase();

    const layout = {
        ...base,
        margin: { l: 140, r: 85, t: 20, b: 40 },
        xaxis: {
            ...base.xaxis,
            title: 'Lenses Failed',
            range: [0, maxCount * 1.32],
            zeroline: false
        },
        yaxis: {
            ...base.yaxis,
            automargin: true,
            tickfont: {
                color: isLight ? '#334155' : '#CBD5E1',
                size: 11,
                weight: 500
            }
        },
        showlegend: false
    };

    Plotly.newPlot(el, [trace], layout, {
        responsive: true,
        displayModeBar: false,
        scrollZoom: false
    });
}
window.renderPeriodBReasonsChart = renderPeriodBReasonsChart;

// -----------------------------------------------------------------------------
// LOGGED CORRECTIONS / TRACING BY SHIFT (SHIFT A, B, C)
// -----------------------------------------------------------------------------
function renderShiftDriftChart(shift) {
    const el = document.getElementById('chart-shift-drift');
    if (!el) return;
    if (!shift || !Array.isArray(shift) || shift.length === 0) {
        el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-size:0.85rem;">No shift data available</div>';
        return;
    }
    const isLight = document.body.classList.contains('light-theme');
    const base = getPlotBase();

    // Check if shift has logged counts (traced / manual)
    if (shift[0] && (shift[0].traced !== undefined || shift[0].total !== undefined)) {
        const xCategories = shift.map(s => s.shift_label || s.shift);
        const tracedCounts = shift.map(s => s.traced || 0);
        const manualCounts = shift.map(s => s.manual || 0);
        const totals = shift.map(s => s.total || (s.traced + s.manual) || 0);

        const traceTraced = {
            name: 'Traced',
            x: xCategories,
            y: tracedCounts,
            type: 'bar',
            marker: { color: isLight ? '#0284C7' : '#00F2FE' },
            text: tracedCounts.map(v => v > 0 ? `${v}` : ''),
            textposition: 'inside',
            textfont: { color: isLight ? '#ffffff' : '#0F172A', size: 11, weight: 600 },
            hovertemplate: '<b>%{x}</b><br>Traced Corrections: <b>%{y}</b><extra>Traced</extra>'
        };

        const traceManual = {
            name: 'Manual',
            x: xCategories,
            y: manualCounts,
            type: 'bar',
            marker: { color: isLight ? '#EA580C' : '#F97316' },
            text: manualCounts.map(v => v > 0 ? `${v}` : ''),
            textposition: 'inside',
            textfont: { color: '#ffffff', size: 11, weight: 600 },
            hovertemplate: '<b>%{x}</b><br>Manual Corrections: <b>%{y}</b><extra>Manual</extra>'
        };

        const maxTotal = Math.max(...totals, 5);
        const layout = {
            ...base,
            barmode: 'stack',
            margin: { l: 45, r: 15, t: 20, b: 50 },
            yaxis: {
                ...base.yaxis,
                title: 'Logged Corrections',
                range: [0, maxTotal * 1.25],
                zeroline: false
            },
            xaxis: {
                ...base.xaxis,
                tickfont: { color: isLight ? '#334155' : '#CBD5E1', size: 11 }
            },
            legend: {
                orientation: 'h',
                y: -0.22,
                font: { color: isLight ? '#0F172A' : '#f0f2f5', size: 11 }
            }
        };

        Plotly.newPlot(el, [traceTraced, traceManual], layout, {
            responsive: true,
            displayModeBar: false,
            scrollZoom: false
        });
    } else {
        // Fallback for Period A vs Period B fail rate if older QC data format
        const x = shift.map(s => (s.shift || '').replace(/ Shift/, ''));
        const bar = (name, rk, ek, qk, color) => ({
            x, y: shift.map(s => s[rk]), name, type: 'bar', marker: { color },
            text: shift.map(s => s[rk] + '%'), textposition: 'outside', textfont: { color: isLight ? '#0F172A' : '#f0f2f5' },
            customdata: shift.map(s => [s[ek], s[qk]]), hovertemplate: '%{y}% (%{customdata[0]} fails of %{customdata[1]} QC\'d)<extra>' + name + '</extra>'
        });
        Plotly.newPlot(el, [bar('Period A', 'rate_a', 'events_a', 'qc_a', COLOR_A), bar('Period B', 'rate_b', 'events_b', 'qc_b', COLOR_B)],
            { ...base, barmode: 'group', yaxis: { ...base.yaxis, title: 'Fail rate %' } }, { responsive: true, displayModeBar: false });
    }
}
window.renderShiftDriftChart = renderShiftDriftChart;

function renderCorrectionEffectiveness(eff, summary) {
    if (!eff || !summary) return;
    const isLight = document.body.classList.contains('light-theme');
    const trace = {
        labels: ['Corrected', 'Recurred', 'Pending', 'Unlogged'],
        values: [eff.corrected, eff.recurred, eff.pending, eff.corrected_unlogged],
        type: 'pie', hole: 0.55, marker: { colors: ['#00e676', '#ff1744', '#ffeb3b', '#e040fb'] },
        textinfo: 'label+value', textfont: { color: '#ffffff', size: 12 }, hoverinfo: 'label+percent+value'
    };
    const base = getPlotBase();
    const el = document.getElementById('chart-correction-eff');
    if (!el) return;

    Plotly.newPlot(el, [trace], {
        font: base.font, paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
        margin: { l: 20, r: 20, t: 10, b: 10 }, showlegend: true,
        dragmode: false, hovermode: 'closest',
        legend: { orientation: 'h', y: -0.1, font: { color: isLight ? '#0F172A' : '#f0f2f5', size: 10 } },
        annotations: [{ text: `${summary.weekly_correction_pct}%<br>Fixed`, showarrow: false, font: { size: 18, color: '#00e676', family: 'Outfit' } }]
    }, { responsive: true, displayModeBar: false, scrollZoom: false });

    // Interactive Donut Click: Filter "PIDs Needing Action" table
    if (el.removeAllListeners) {
        el.removeAllListeners('plotly_click');
    }
    if (el.on) {
        el.on('plotly_click', function(data) {
            if (!data || !data.points || !data.points.length) return;
            const clickedLabel = data.points[0].label; // 'Pending', 'Recurred', 'Unlogged', 'Corrected'
            filterActionListByClassification(clickedLabel);
        });
    }
}

// -----------------------------------------------------------------------------
// PIDS NEEDING ACTION: TABLE RENDERING & DONUT SLICE FILTERING
// -----------------------------------------------------------------------------
let currentActionFilter = null;

function renderActionList(list) {
    const tbody = document.getElementById('action-table-body');
    if (!tbody) return;
    tbody.innerHTML = (list || []).map(c => `
        <tr>
            <td><strong class="cursor-pointer text-blue" onclick="quickLookupPID('${escHtml(c.pid)}')">${escHtml(c.pid)}</strong></td>
            <td><span class="tag tag-${escHtml(c.classification)}">${escHtml(c.classification)}</span></td>
            <td>${c.fail_event_count}</td><td>${c.fail_events_b}</td>
            <td>${escHtml(c.reason_cluster)}</td>
            <td>${c.correction_timestamp && c.correction_timestamp !== 'N/A' ? escHtml(c.correction_timestamp) : '-'}</td>
            <td>${escHtml(c.done_by) || '-'}</td>
        </tr>`).join('') || '<tr><td colspan="7" class="text-center text-muted" style="padding: 16px;">No PIDs match this selection</td></tr>';
}

function filterActionListByClassification(label) {
    if (currentActionFilter === label) {
        resetActionListFilter();
        return;
    }
    currentActionFilter = label;
    const all = (globalData && globalData.classified_pids && globalData.classified_pids.length)
        ? globalData.classified_pids
        : ((globalData && globalData.action_list) ? globalData.action_list : []);

    let filtered = all.filter(c => {
        if (label === 'Unlogged') {
            return c.classification === 'Corrected-unlogged' || c.classification === 'Unlogged';
        }
        return c.classification === label;
    });

    // Sort worst first: fail_events_b desc, fail_event_count desc
    filtered.sort((a, b) => (b.fail_events_b || 0) - (a.fail_events_b || 0) || (b.fail_event_count || 0) - (a.fail_event_count || 0));

    const headerTitle = document.getElementById('action-table-title');
    const headerSub = document.getElementById('action-table-sub');
    let tagColor = '#00F2FE';
    if (label === 'Pending') tagColor = '#eab308';
    else if (label === 'Recurred') tagColor = '#ef4444';
    else if (label === 'Unlogged') tagColor = '#a855f7';
    else if (label === 'Corrected') tagColor = '#22c55e';

    if (headerTitle) {
        headerTitle.innerHTML = `PIDs Needing Action &mdash; <span style="color:${tagColor}; font-weight:800;">${escHtml(label)} (${filtered.length})</span>`;
    }
    if (headerSub) {
        headerSub.innerHTML = `Filtered by slice <strong>${escHtml(label)}</strong> (${filtered.length} total PIDs). <button type="button" class="btn btn-sm btn-secondary" onclick="resetActionListFilter()" style="margin-left: 10px; padding: 2px 10px; font-size: 0.74rem; cursor: pointer; border-radius: 6px;">✕ Reset Filter</button>`;
    }

    renderActionList(filtered);

    // Smooth scroll down to table so user sees the filtered rows immediately
    const tableTitleEl = document.getElementById('action-table-title');
    if (tableTitleEl) {
        tableTitleEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}
window.filterActionListByClassification = filterActionListByClassification;

function resetActionListFilter() {
    currentActionFilter = null;
    const headerTitle = document.getElementById('action-table-title');
    const headerSub = document.getElementById('action-table-sub');
    if (headerTitle) headerTitle.innerText = 'PIDs Needing Action';
    if (headerSub) headerSub.innerText = 'Recurred and Pending PIDs, worst first (by Period B failures). Click a PID for its full history.';
    if (globalData && globalData.action_list) {
        renderActionList(globalData.action_list);
    }
}
window.resetActionListFilter = resetActionListFilter;

// =====================
// DRILLDOWN
// =====================
async function openDrilldown(catType, val1) {
    try {
        const res = await fetch('/api/drilldown', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category_type: catType, filter_value: val1 })
        });
        const data = await res.json();

        document.getElementById('modal-title').innerText = `${val1} (${data.count} PIDs)`;
        const tbody = document.getElementById('modal-table-body');
        tbody.innerHTML = '';

        data.pids.forEach(p => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong class="cursor-pointer text-blue" onclick="quickLookupPID('${p.pid}')">${p.pid}</strong></td>
                <td><span class="tag tag-${p.classification.replace(/\s+/g, '')}">${p.classification}</span></td>
                <td>${p.reason_cluster}</td>
                <td>${p.qc_person_id}</td>
                <td>${p.fail_event_count || 1}</td>
            `;
            tbody.appendChild(tr);
        });

        document.getElementById('drilldown-modal').classList.remove('hidden');
    } catch (e) {
        console.error("Drilldown error:", e);
    }
}

// =====================
// NAVIGATION
// =====================
function setupMainTabs() {
    const tabs = [
        { btn: 'tab-btn-analytics', view: 'analytics-view' },
        { btn: 'tab-btn-explorer', view: 'explorer-view' },
        { btn: 'tab-btn-impact', view: 'impact-view', action: () => fetchImpact() }
    ];
    tabs.forEach(t => {
        document.getElementById(t.btn).addEventListener('click', () => {
            tabs.forEach(o => {
                document.getElementById(o.btn).classList.toggle('active', o === t);
                document.getElementById(o.view).classList.toggle('hidden', o !== t);
            });
            if (t.action) t.action();
        });
    });
    document.getElementById('impact-search').addEventListener('input', () => renderImpactTable());
    document.getElementById('impact-status').addEventListener('change', () => renderImpactTable());
    document.getElementById('btn-impact-save').addEventListener('click', saveImpactSettings);
    document.getElementById('btn-impact-check').addEventListener('click', checkPidInvoice);
    document.getElementById('impact-check-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') checkPidInvoice(); });
}

function setupExplorerSubtabs() {
    const subtabs = [
        { btn: 'subtab-master', panel: 'exp-panel-master', action: refreshMaster },
        { btn: 'subtab-pid', panel: 'exp-panel-pid' },
        { btn: 'subtab-classifications', panel: 'exp-panel-classifications', action: fetchExplorerClassifications },
        { btn: 'subtab-clusters', panel: 'exp-panel-clusters', action: fetchExplorerClusters },
        { btn: 'subtab-fails', panel: 'exp-panel-fails', action: fetchExplorerFails }
    ];

    subtabs.forEach(tab => {
        const btnEl = document.getElementById(tab.btn);
        const panelEl = document.getElementById(tab.panel);
        if (!btnEl || !panelEl) return;
        btnEl.addEventListener('click', () => {
            subtabs.forEach(t => {
                const b = document.getElementById(t.btn);
                const p = document.getElementById(t.panel);
                if (b) b.classList.remove('active');
                if (p) p.classList.add('hidden');
            });
            btnEl.classList.add('active');
            panelEl.classList.remove('hidden');
            if (tab.action) tab.action();
        });
    });
}

function setupExplorerControls() {
    // PID Lookup
    const pidInput = document.getElementById('exp-pid-input');
    const pidBtn = document.getElementById('exp-pid-btn');
    if (pidBtn && pidInput) {
        const execPid = () => { const q = pidInput.value.trim(); if (q) fetchPIDHistory(q); };
        pidBtn.addEventListener('click', execPid);
        pidInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') execPid(); });
    }

    // Classifications
    bindExplorerTableControls('exp-class', expClassState, fetchExplorerClassifications, [], 'exp-class-status-filter', 'status');
    // Fails
    bindExplorerTableControls('exp-fails', expFailsState, fetchExplorerFails, [], 'exp-fails-period-filter', 'period');
    // Master database
    bindExplorerTableControls('exp-master', expMasterState, fetchExplorerMaster, [], 'exp-master-type', 'type');
    document.getElementById('exp-master-from').addEventListener('change', (e) => { expMasterState.date_from = e.target.value; expMasterState.page = 1; fetchExplorerMaster(); });
    document.getElementById('exp-master-to').addEventListener('change', (e) => { expMasterState.date_to = e.target.value; expMasterState.page = 1; fetchExplorerMaster(); });
    document.getElementById('btn-master-export').addEventListener('click', () => {
        const p = expMasterState;
        window.location = `/api/explorer/master/export?search=${encodeURIComponent(p.search)}&type=${p.type}&date_from=${p.date_from}&date_to=${p.date_to}&sort_order=asc`;
    });
}

function bindExplorerTableControls(prefix, stateObj, fetchFn, sortableCols = [], filterElId = null, filterProp = null) {
    const searchEl = document.getElementById(`${prefix}-search`);
    const limitEl = document.getElementById(`${prefix}-limit`);
    const prevBtn = document.getElementById(`${prefix}-prev`);
    const nextBtn = document.getElementById(`${prefix}-next`);

    if (searchEl) {
        searchEl.addEventListener('input', (e) => { stateObj.search = e.target.value; stateObj.page = 1; fetchFn(); });
    }
    if (limitEl) {
        limitEl.addEventListener('change', (e) => { stateObj.limit = parseInt(e.target.value); stateObj.page = 1; fetchFn(); });
    }
    if (filterElId && filterProp) {
        document.getElementById(filterElId).addEventListener('change', (e) => { stateObj[filterProp] = e.target.value; stateObj.page = 1; fetchFn(); });
    }
    if (prevBtn) {
        prevBtn.addEventListener('click', () => { if (stateObj.page > 1) { stateObj.page--; fetchFn(); } });
    }
    if (nextBtn) {
        nextBtn.addEventListener('click', () => { stateObj.page++; fetchFn(); });
    }

    // Header Sorting
    const parentPanel = document.getElementById(`${prefix.replace('-', '-panel-').replace('exp-', 'exp-panel-')}`);
    // Simpler approach: query all sortable headers under this prefix's panel
    document.querySelectorAll(`#exp-panel-${prefix.replace('exp-', '')} th.sortable, #${prefix}-table th.sortable`).forEach(th => {
        th.addEventListener('click', () => {
            const col = th.getAttribute('data-sort');
            if (stateObj.sort_by === col) {
                stateObj.sort_order = (stateObj.sort_order === "asc") ? "desc" : "asc";
            } else {
                stateObj.sort_by = col;
                stateObj.sort_order = "asc";
            }
            fetchFn();
        });
    });
}

// =====================
// EXPLORER: PID LOOKUP
// =====================
let currentLookupPID = null;

async function fetchPIDHistory(pid) {
    try {
        const cleanPid = String(pid).trim();
        currentLookupPID = cleanPid;
        const res = await fetch(`/api/explorer/pid/${encodeURIComponent(cleanPid)}`);
        if (!res.ok) throw new Error("PID lookup failed");
        const data = await res.json();

        document.getElementById('pid-history-container').classList.remove('hidden');

        document.getElementById('pid-summary-id').innerText = `PID: #${data.pid}`;
        document.getElementById('pid-summary-invoice').innerText = data.primary_invoice || 'N/A';
        document.getElementById('pid-summary-machine').innerText = data.primary_machine || 'N/A';
        document.getElementById('pid-fails-count').innerText = data.fails_count;
        document.getElementById('pid-corr-count').innerText = data.corrections_count;
        document.getElementById('pid-primary-reason').innerText = data.primary_reason_cluster || 'N/A';
        document.getElementById('pid-summary-tech').innerText = data.latest_tech || 'N/A';

        const badge = document.getElementById('pid-status-badge');
        badge.innerText = data.classification;
        badge.className = `badge tag-${data.classification.replace(/\s+/g, '')}`;

        const btnFocus = document.getElementById('btn-pid-add-correction');
        if (btnFocus) btnFocus.onclick = () => focusMainLogForm(data.pid);

        // Fails table
        const failsTbody = document.getElementById('pid-fails-tbody');
        failsTbody.innerHTML = '';
        if (data.fails_history && data.fails_history.length > 0) {
            data.fails_history.forEach(f => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${f.period}</strong></td>
                    <td>${f.QC_created_date}</td>
                    <td>${f.invoice || f.vendor_invoice_number || 'N/A'}</td>
                    <td>${f.qc_person_id}</td>
                    <td>${f.reason_raw}</td>
                    <td><small>${f.shift_bucket || 'N/A'}</small></td>
                `;
                failsTbody.appendChild(tr);
            });
        } else {
            failsTbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No QC failures for this PID</td></tr>`;
        }

        // Corrections table
        const corrTbody = document.getElementById('pid-corr-tbody');
        corrTbody.innerHTML = '';
        if (data.corrections_history && data.corrections_history.length > 0) {
            data.corrections_history.forEach(c => {
                const tr = document.createElement('tr');
                const b = c.dims_before || {};
                const a = c.dims_after || {};
                const fmt = (v) => (v !== null && v !== undefined && !isNaN(v)) ? v : '-';
                const beforeStr = `A:${fmt(b.A)} B:${fmt(b.B)} CR:${fmt(b.CIRC_R)} CL:${fmt(b.CIRC_L)}`;
                const afterStr = `A1:${fmt(a.A1)} B1:${fmt(a.B1)} CR1:${fmt(a.CIRC_R1)} CL1:${fmt(a.CIRC_L1)}`;
                const sourceTag = c.is_manual ? `<span class="tag-manual">Manual</span>` : `<small>${c.sheet}</small>`;

                let actionHtml = '-';
                if (c.is_manual) {
                    actionHtml = `<button class="btn-action-sm btn-danger-sm" onclick="handleDeleteManualCorrection('${c.id}', '${data.pid}')">Del</button>`;
                }

                tr.innerHTML = `
                    <td>${c.timestamp}</td>
                    <td>${sourceTag}</td>
                    <td>${c.issue_raw}</td>
                    <td><small>${beforeStr}</small></td>
                    <td><small>${afterStr}</small></td>
                    <td>${escHtml(c.done_by) || '-'}</td>
                    <td>${actionHtml}</td>
                `;
                corrTbody.appendChild(tr);
            });
        } else {
            corrTbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">No corrections logged. Click "+ Log Correction".</td></tr>`;
        }
    } catch (e) {
        alert(`Error looking up PID ${pid}: ${e.message}`);
    }
}

// =====================
// EXPLORER: CLASSIFICATIONS
// =====================
async function fetchExplorerClassifications() {
    const p = expClassState;
    const url = `/api/explorer/classifications?page=${p.page}&limit=${p.limit}&search=${encodeURIComponent(p.search)}&sort_by=${p.sort_by}&sort_order=${p.sort_order}&status=${p.status}`;
    try {
        const res = await fetch(url);
        const data = await res.json();

        document.getElementById('exp-class-page-info').innerText = `Page ${data.page}/${data.total_pages} (${data.total_rows} PIDs)`;
        document.getElementById('exp-class-page-num').innerText = data.page;

        const tbody = document.getElementById('exp-class-tbody');
        tbody.innerHTML = '';
        data.data.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong class="cursor-pointer text-blue" onclick="quickLookupPID('${r.pid}')">${r.pid}</strong></td>
                <td><span class="tag tag-${r.classification.replace(/\s+/g, '')}">${r.classification}</span></td>
                <td>${r.reason_cluster || '-'}</td>
                <td>${r.qc_person_id || '-'}</td>
                <td>${r.fail_event_count || 1}</td>
                <td>${r.first_fail_timestamp || '-'}</td>
                <td><button class="btn-expand-row" onclick="quickLookupPID('${r.pid}')">→ View</button></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Fetch classifications error:", e);
    }
}

// =====================
// EXPLORER: CLUSTERS
// =====================
async function fetchExplorerClusters() {
    try {
        const res = await fetch('/api/explorer/clusters');
        const clusters = await res.json();

        const container = document.getElementById('clusters-accordion-container');
        container.innerHTML = '';

        clusters.forEach(c => {
            const card = document.createElement('div');
            card.className = 'glass-card cluster-card';
            const meiTag = c.is_mei_attributable ? `<span class="tag-mei">MEI Machine</span>` : '';

            let membersHtml = '';
            c.members.forEach(m => {
                membersHtml += `<div class="member-item"><span>${m.raw_string}</span><span class="member-count">${m.count}</span></div>`;
            });

            card.innerHTML = `
                <div class="cluster-title-row"><h4>${c.cluster_representative}</h4>${meiTag}</div>
                <p class="history-subtext">Total: <strong>${c.total_count}</strong> | Merged: ${c.members.length}</p>
                <div class="cluster-members-list">${membersHtml}</div>
            `;
            container.appendChild(card);
        });
    } catch (e) {
        console.error("Fetch clusters error:", e);
    }
}

// =====================
// EXPLORER: RAW FAILS
// =====================
async function fetchExplorerFails() {
    const p = expFailsState;
    const url = `/api/explorer/fails?page=${p.page}&limit=${p.limit}&search=${encodeURIComponent(p.search)}&sort_by=${p.sort_by}&sort_order=${p.sort_order}&period=${p.period}`;
    try {
        const res = await fetch(url);
        const data = await res.json();

        document.getElementById('exp-fails-page-info').innerText = `Page ${data.page}/${data.total_pages} (${data.total_rows} rows)`;
        document.getElementById('exp-fails-page-num').innerText = data.page;

        const tbody = document.getElementById('exp-fails-tbody');
        tbody.innerHTML = '';
        data.data.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong class="cursor-pointer text-blue" onclick="quickLookupPID('${r.pid}')">${r.pid}</strong></td>
                <td>${r.period}</td>
                <td>${r.QC_created_date}</td>
                <td>${r.reason_raw}</td>
                <td>${r.qc_person_id}</td>
                <td>${r.vendor_invoice_number}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Fetch fails error:", e);
    }
}

// =====================
// EXPLORER: CORRECTIONS
// =====================
const escHtml = (v) => String(v ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

// Editable dimension cell group for manual entries (A/B/CR/CL or A1/B1/CR1/CL1)
function dimInputs(entryId, group, vals) {
    const v = (x) => (x !== null && x !== undefined && !isNaN(x)) ? x : '';
    const fields = group === 'before'
        ? [['a','A',vals.A],['b','B',vals.B],['circ_r','CR',vals.CIRC_R],['circ_l','CL',vals.CIRC_L]]
        : [['a1','A1',vals.A1],['b1','B1',vals.B1],['circ_r1','CR1',vals.CIRC_R1],['circ_l1','CL1',vals.CIRC_L1]];
    return `<div class="dim-edit-grid">` + fields.map(([key, label, val]) =>
        `<label class="dim-edit"><span>${label}</span><input type="number" step="0.01" class="dim-edit-input" data-entry="${escHtml(entryId)}" data-key="${key}" value="${v(val)}" /></label>`
    ).join('') + `</div>`;
}

async function saveDimsRow(entryId, btn) {
    const inputs = document.querySelectorAll(`.dim-edit-input[data-entry="${CSS.escape(entryId)}"]`);
    const body = {};
    for (const inp of inputs) {
        const raw = inp.value.trim();
        if (raw === '') { body[inp.dataset.key] = null; continue; }
        const n = parseFloat(raw);
        if (isNaN(n)) { alert(`Invalid number in ${inp.dataset.key}`); return; }
        body[inp.dataset.key] = n;
    }
    btn.disabled = true; const old = btn.innerText; btn.innerText = 'Saving...';
    try {
        const res = await fetch(`/api/manual_corrections/${encodeURIComponent(entryId)}/dims`, {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
        });
        if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Save failed'); }
        btn.innerText = 'Saved ✓';
        setTimeout(() => { btn.disabled = false; btn.innerText = old; }, 1200);
    } catch (e) {
        btn.disabled = false; btn.innerText = old;
        alert(`Error: ${e.message}`);
    }
}

async function fetchExplorerCorrections() {
    const p = expCorrState;
    const url = `/api/explorer/corrections?page=${p.page}&limit=${p.limit}&search=${encodeURIComponent(p.search)}&sort_by=${p.sort_by}&sort_order=${p.sort_order}`;
    try {
        const res = await fetch(url);
        const data = await res.json();

        document.getElementById('exp-corr-page-info').innerText = `Page ${data.page}/${data.total_pages} (${data.total_rows} entries)`;
        document.getElementById('exp-corr-page-num').innerText = data.page;

        const tbody = document.getElementById('exp-corr-tbody');
        tbody.innerHTML = '';
        data.data.forEach(r => {
            const tr = document.createElement('tr');
            const b = r.dims_before || {};
            const a = r.dims_after || {};
            const fmt = (v) => (v !== null && v !== undefined && !isNaN(v)) ? v : '-';
            const normBadge = r.issue_normalized ? `<span class="tag-mei">${escHtml(r.issue_normalized)}</span>` : '<span class="text-muted">excluded</span>';
            const editable = r.is_manual && r.id;
            const beforeCell = editable ? dimInputs(r.id, 'before', b)
                : `<small>A:${fmt(b.A)} B:${fmt(b.B)} CR:${fmt(b.CIRC_R)} CL:${fmt(b.CIRC_L)}</small>`;
            const afterCell = editable ? dimInputs(r.id, 'after', a)
                : `<small>A1:${fmt(a.A1)} B1:${fmt(a.B1)} CR1:${fmt(a.CIRC_R1)} CL1:${fmt(a.CIRC_L1)}</small>`;
            const actionCell = editable
                ? `<button class="btn btn-sm btn-primary" onclick="saveDimsRow('${escHtml(r.id)}', this)">Save</button>`
                : `<span class="text-muted" title="Imported from the correction workbook; edit it there">-</span>`;

            tr.innerHTML = `
                <td><strong class="cursor-pointer text-blue" onclick="quickLookupPID('${escHtml(r.pid)}')">${escHtml(r.pid_invoice || r.pid)}</strong></td>
                <td>${escHtml(r.timestamp)}</td>
                <td><small>${escHtml(r.sheet)}</small></td>
                <td>${escHtml(r.issue_raw)}</td>
                <td>${normBadge}</td>
                <td>${beforeCell}</td>
                <td>${afterCell}</td>
                <td>${escHtml(r.done_by) || '-'}</td>
                <td>${actionCell}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Fetch corrections error:", e);
    }
}

// =====================
// EXPLORER: MASTER DATABASE (all QC fails + all corrections, first entry -> last)
// =====================
function refreshMaster() { fetchMasterSummary(); fetchExplorerMaster(); }

async function fetchMasterSummary() {
    try {
        const s = await (await fetch('/api/explorer/master/summary')).json();
        const card = (title, value, desc, cls = '') =>
            `<div class="glass-card kpi-card"><div class="kpi-title">${title}</div><div class="kpi-value ${cls}">${escHtml(value ?? '-')}</div><div class="kpi-desc">${escHtml(desc || '')}</div></div>`;
        document.getElementById('master-summary').innerHTML =
            card('First entry', s.first_entry, 'Earliest record in the database', 'text-blue') +
            card('Last entry', s.last_entry, 'Most recent record', 'text-blue') +
            card('Total records', Number(s.total_records).toLocaleString(), `${Number(s.fails).toLocaleString()} QC fails + ${Number(s.corrections).toLocaleString()} corrections`) +
            card('QC fails', `${s.first_fail || '-'} → ${s.last_fail || '-'}`, 'Date span of QC fail data', 'text-red') +
            card('Corrections', `${s.first_correction || '-'} → ${s.last_correction || '-'}`, 'Date span of correction entries', 'text-green') +
            card('Last updated', s.last_updated || '-', 'Archive / manual log file modified');

        const w = document.getElementById('master-warnings');
        if (s.warnings && s.warnings.length) {
            w.innerHTML = s.warnings.map(x => `<div class="master-warning-item">⚠ ${escHtml(x)}</div>`).join('');
            w.classList.remove('hidden');
        } else {
            w.classList.add('hidden');
        }

        document.getElementById('master-sources-count').textContent = `(${(s.sources || []).length})`;
        document.getElementById('master-sources-tbody').innerHTML = (s.sources || []).map(x => `
            <tr><td>${escHtml(x.source_label)}</td><td>${escHtml(x.loaded_as)}</td><td>${x.rows_in_file}</td>
            <td>${x.rows_added}</td><td>${escHtml(x.first_date)}</td><td>${escHtml(x.last_date)}</td><td>${escHtml(x.ingested_at)}</td></tr>`).join('')
            || '<tr><td colspan="7" class="text-center text-muted">No sources recorded yet</td></tr>';
    } catch (e) {
        console.error('Master summary error:', e);
    }
}

async function fetchExplorerMaster() {
    const p = expMasterState;
    const url = `/api/explorer/master?page=${p.page}&limit=${p.limit}&search=${encodeURIComponent(p.search)}&type=${p.type}&date_from=${p.date_from}&date_to=${p.date_to}&sort_order=${p.sort_order}`;
    try {
        const data = await (await fetch(url)).json();
        document.getElementById('exp-master-page-info').textContent = `Page ${data.page}/${data.total_pages} (${data.total_rows.toLocaleString()} records)`;
        document.getElementById('exp-master-page-num').textContent = data.page;
        const tbody = document.getElementById('exp-master-tbody');
        tbody.innerHTML = data.data.map(r => `
            <tr>
                <td><span class="${r.type === 'QC Fail' ? 'tag-fail' : 'tag-corr'}">${escHtml(r.type)}</span></td>
                <td>${escHtml(r.date)}</td>
                <td><strong class="cursor-pointer text-blue" onclick="quickLookupPID('${escHtml(r.pid)}')">${escHtml(r.pid_invoice)}</strong></td>
                <td>${escHtml(r.reason)}</td>
                <td>${escHtml(r.who)}</td>
                <td><small>${escHtml(r.detail)}</small></td>
                <td><small>${escHtml(r.source)}</small></td>
            </tr>`).join('') || '<tr><td colspan="7" class="text-center text-muted">No records match</td></tr>';
    } catch (e) {
        console.error('Fetch master error:', e);
    }
}

// =====================
// CORRECTION IMPACT
// =====================
let impactData = null;
const nv = (v) => (v === null || v === undefined || (typeof v === 'number' && isNaN(v))) ? '-' : v;
const rateTxt = (o) => (o && o.rate !== null && o.rate !== undefined) ? `${o.rate}% <small>(${o.fails}/${o.qc_done})</small>` : '<span class="text-muted">-</span>';
const fdate = (d) => d ? new Date(d + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : '-';

async function fetchImpact() {
    try {
        const res = await fetch('/api/impact');
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Failed');
        impactData = await res.json();
        renderImpact();
    } catch (e) {
        document.getElementById('impact-cards').innerHTML = `<div class="master-warning-item">Could not load impact: ${escHtml(e.message)}</div>`;
    }
}

function renderImpact() {
    const d = impactData, s = d.summary, c = s.counts;
    const judged = c['Fixed'] + c['Improved'] + c['Still failing'];
    const pct = (n) => judged ? ` (${Math.round(n / judged * 100)}% of judged)` : '';
    const card = (t, v, desc, cls = '') => `<div class="glass-card kpi-card"><div class="kpi-title">${t}</div><div class="kpi-value ${cls}">${v}</div><div class="kpi-desc">${desc}</div></div>`;
    document.getElementById('impact-cards').innerHTML =
        card('Corrections', s.total - c['No correction done'], `with dimensions logged · ${c['No correction done']} flagged "no correction"`) +
        card('Fixed', c['Fixed'], 'No MEI shape fail since the correction' + pct(c['Fixed']), 'text-green') +
        card('Improved', c['Improved'], 'Fail rate at least halved' + pct(c['Improved']), 'text-blue') +
        card('Still failing', c['Still failing'], 'Failing at a similar rate' + pct(c['Still failing']), 'text-red') +
        card('Not tested yet', c['Not tested yet'], `Fewer than ${d.settings.min_volume} lenses QC'd since the correction`) +
        card('Needs a correction', d.pending.count, `PID.Invoices with ${d.settings.fail_threshold}+ fails and no correction`, 'text-red');

    const warn = [...(d.row_cap_notes || [])];
    const cov = d.coverage || {};
    const covTxt = Object.entries(cov).map(([k, v]) => `${k}: ${v.qc_done.toLocaleString()} lenses QC'd, cut ${fdate(v.cut_from)} - ${fdate(v.cut_to)} (most between ${fdate(v.bulk_from)} and ${fdate(v.bulk_to)})`).join(' &nbsp;|&nbsp; ');
    const w = document.getElementById('impact-warnings');
    if (warn.length) { w.innerHTML = warn.map(x => `<div class="master-warning-item">⚠ ${escHtml(x)}</div>`).join(''); w.classList.remove('hidden'); } else { w.classList.add('hidden'); }
    const ob = d.observed || {};
    document.getElementById('impact-coverage').innerHTML = `<strong>QC exports cover lenses QC'd ${fdate(ob.from)} - ${fdate(ob.to)}.</strong> A correction is judged only on lenses cut after its date and not before ${fdate(ob.from)}, because lenses cut earlier are only partly in the exports.<br><strong>All QC'd lenses by cut date:</strong> ${covTxt}`;
    renderFindings(d);

    const p = s.pooled;
    document.getElementById('impact-pooled').innerHTML =
        `<tr><td>Before correction <small>(sheet stats, ${p.before_n} corrections)</small></td><td>${p.before.fails}</td><td>${p.before.qc_done}</td><td><strong>${nv(p.before.rate)}%</strong></td></tr>` +
        `<tr><td>After, Period A QC data</td><td>${p.after_a.fails}</td><td>${p.after_a.qc_done}</td><td><strong>${nv(p.after_a.rate)}%</strong></td></tr>` +
        `<tr><td>After, Period B QC data</td><td>${p.after_b.fails}</td><td>${p.after_b.qc_done}</td><td><strong>${nv(p.after_b.rate)}%</strong></td></tr>`;

    document.getElementById('impact-windows').innerHTML = d.windows.map(x => `<tr><td>${escHtml(x.sheet)}${x.overridden ? ' <span class="tag-corr">edited</span>' : ''}</td>
        <td><input type="date" class="select-input" data-norm="${escHtml(x.norm)}" data-k="start" value="${x.start}" /></td>
        <td><input type="date" class="select-input" data-norm="${escHtml(x.norm)}" data-k="end" value="${x.end}" /></td></tr>`).join('');
    document.getElementById('impact-min-volume').value = d.settings.min_volume;
    document.getElementById('impact-threshold').value = d.settings.fail_threshold;

    document.getElementById('impact-pending-sub').innerText = `${d.pending.count} PID.Invoices; showing the ${d.pending.rows.length} with the most failures.`;
    document.getElementById('impact-pending').innerHTML = d.pending.rows.map(r => `<tr>
        <td><strong class="cursor-pointer text-blue" onclick="quickLookupPID('${escHtml(r.key)}')">${escHtml(r.key)}</strong></td>
        <td>${r.fails_a}</td><td>${r.fails_b}</td><td>${nv(r.rate)}%</td>
        <td><small>${r.in_lists.map(l => escHtml(l.list) + ': ' + escHtml(l.status)).join(', ') || '-'}</small></td></tr>`).join('') || '<tr><td colspan="5" class="text-center text-muted">None</td></tr>';

    document.getElementById('impact-dims').innerHTML = Object.entries(s.dim_stats).map(([k, v]) =>
        `<tr><td>${escHtml(k)}</td><td>${v.n}</td><td>${nv(v.mean_shift)}</td><td>${nv(v.mean_abs_shift)}</td></tr>`).join('');
    const grp = (label, arr) => arr.map(g => `<tr><td>${label}: ${escHtml(g.name)}</td><td>${g.n}</td><td>${g.fixed}</td><td>${g.improved}</td><td>${g.still_failing}</td><td>${nv(g.avg_deviation_pct)}</td></tr>`).join('');
    document.getElementById('impact-groups').innerHTML = grp('Issue', s.by_issue) + grp('Person', s.by_person);

    document.getElementById('impact-lists-count').innerText = `(${d.list_checks.length})`;
    document.getElementById('impact-lists').innerHTML = d.list_checks.map(l => `<tr><td>${escHtml(l.list)}</td><td>${l.keys}</td><td>${l.marked_done}</td><td>${l.pending}</td><td>${l.other_status}</td>
        <td>${l.corrected_then_failing_again.map(x => `${escHtml(x.from_sheet.trim())}: <strong>${x.count}</strong> of ${l.corrected_sheet_sizes[x.from_sheet]}`).join('<br>') || '-'}</td>
        <td>${Object.entries(l.repeat_from_earlier_lists).map(([k, v]) => `${escHtml(k)}: <strong>${v}</strong>`).join('<br>') || '-'}</td></tr>`).join('');
    renderImpactTable();
}

function refreshImpactIfOpen() {
    impactData = null;
    const v = document.getElementById('impact-view');
    if (v && !v.classList.contains('hidden')) fetchImpact();
}

function renderFindings(d) {
    const s = d.summary, c = s.counts, p = s.pooled, out = [];
    const judged = c['Fixed'] + c['Improved'] + c['Still failing'];
    const pc = (n, t) => t ? Math.round(n / t * 100) + '%' : '-';
    out.push(`<strong>${c['Fixed']} of ${judged}</strong> judged corrections are fixed (${pc(c['Fixed'], judged)}); ${c['Improved']} improved and ${c['Still failing']} still failing. ${c['Not tested yet']} cannot be judged yet (fewer than ${d.settings.min_volume} lenses QC'd since the correction).`);
    if (p.before.rate !== null && p.after_a.rate !== null) {
        out.push(`Fail rate on the corrected PID.Invoices: <strong>${p.before.rate}%</strong> before, <strong>${p.after_a.rate}%</strong> in Period A (${p.after_a.fails} of ${p.after_a.qc_done}), <strong>${nv(p.after_b.rate)}%</strong> in Period B (${p.after_b.fails} of ${p.after_b.qc_done}).`);
    }
    const dims = Object.entries(s.dim_stats).filter(([, v]) => v.mean_abs_shift !== null).sort((a, b) => b[1].mean_abs_shift - a[1].mean_abs_shift);
    if (dims.length) out.push(`Biggest dimension change: <strong>${escHtml(dims[0][0])}</strong> (average ${dims[0][1].mean_shift} mm, average size of change ${dims[0][1].mean_abs_shift} mm over ${dims[0][1].n} corrections).`);
    s.by_issue.filter(g => g.fixed + g.improved + g.still_failing >= 3).forEach(g => {
        const j = g.fixed + g.improved + g.still_failing;
        out.push(`${escHtml(g.name)} corrections: ${g.fixed} of ${j} judged are fixed, ${g.improved} improved, ${g.still_failing} still failing (average deviation ${nv(g.avg_deviation_pct)}%).`);
    });
    const ppl = s.by_person.filter(g => g.n >= 3 && g.name !== '-' && g.name !== 'QC Lead').map(g => `${escHtml(g.name)} ${g.fixed + g.improved} of ${g.fixed + g.improved + g.still_failing} fixed or improved`);
    if (ppl.length) out.push(`By person (judged corrections): ${ppl.join('; ')}.`);
    const still = d.entries.filter(e => e.status === 'Still failing').map(e => escHtml(e.key));
    if (still.length) out.push(`<strong>Re-correct first:</strong> ${still.join(', ')}.`);
    if (d.pending.count) {
        const top = d.pending.rows.slice(0, 3);
        out.push(`<strong>${d.pending.count}</strong> PID.Invoices have ${d.settings.fail_threshold}+ fails and no correction. Worst: ${top.map(r => `${escHtml(r.key)} (${r.fails_a + r.fails_b} fails)`).join(', ')}.`);
    }
    document.getElementById('impact-findings').innerHTML = out.map(x => `<li>${x}</li>`).join('');
}

function renderImpactTable() {
    if (!impactData) return;
    const q = document.getElementById('impact-search').value.toLowerCase().trim();
    const st = document.getElementById('impact-status').value;
    const dim = (x) => (x.before === null && x.after === null) ? '-' : `${nv(x.before)} → ${nv(x.after)}${x.delta !== null ? ` <small>(${x.delta > 0 ? '+' : ''}${x.delta})</small>` : ''}`;
    const rows = impactData.entries.filter(e => (st === 'all' || e.status === st) &&
        (!q || `${e.key} ${e.person} ${e.issue} ${e.sheet} ${e.remark}`.toLowerCase().includes(q)));
    document.getElementById('impact-count').innerText = `${rows.length} of ${impactData.entries.length}`;
    document.getElementById('impact-tbody').innerHTML = rows.map(e => `<tr>
        <td><strong class="cursor-pointer text-blue" onclick="quickLookupPID('${escHtml(e.key)}')">${escHtml(e.key)}</strong>${e.remark ? `<br><small class="text-muted">${escHtml(e.remark)}</small>` : ''}</td>
        <td><small>${escHtml((e.sheet || '').trim())}<br>${fdate(e.window_end)}</small></td>
        <td>${escHtml(e.issue)}</td><td>${escHtml(e.person) || '-'}</td><td>${nv(e.deviation_pct)}</td>
        <td>${dim(e.dims['A'])}</td><td>${dim(e.dims['B'])}</td><td>${dim(e.dims['CIRC R'])}</td><td>${dim(e.dims['CIRC L'])}</td>
        <td>${e.before.rate !== null ? `${e.before.rate}% <small>(${nv(e.before.fails)}/${nv(e.before.qc_done)})</small>` : '-'}</td>
        <td>${rateTxt(e.after_a)}</td><td>${rateTxt(e.after_b)}</td>
        <td><span class="tag-status tag-status-${e.status.replace(/ /g, '-')}">${escHtml(e.status)}</span></td></tr>`).join('')
        || '<tr><td colspan="13" class="text-center text-muted">No corrections match</td></tr>';
}

async function saveImpactSettings() {
    const msg = document.getElementById('impact-save-msg'), btn = document.getElementById('btn-impact-save');
    const wins = {};
    document.querySelectorAll('#impact-windows input[data-norm]').forEach(i => {
        wins[i.dataset.norm] = wins[i.dataset.norm] || {};
        wins[i.dataset.norm][i.dataset.k] = i.value;
    });
    btn.disabled = true; msg.innerText = 'Recalculating... this takes 20-30 seconds';
    try {
        const res = await fetch('/api/impact/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sheet_windows: wins, min_volume: parseInt(document.getElementById('impact-min-volume').value), fail_threshold: parseInt(document.getElementById('impact-threshold').value) }) });
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Save failed');
        impactData = await res.json(); renderImpact(); msg.innerText = 'Saved ✓';
        fetchMetrics();
    } catch (e) { msg.innerText = `Error: ${e.message}`; }
    btn.disabled = false;
}

async function checkPidInvoice() {
    const q = document.getElementById('impact-check-input').value.trim();
    const out = document.getElementById('impact-check-result');
    if (!q) return;
    out.innerHTML = '<span class="text-muted">Checking...</span>';
    try {
        const data = await (await fetch(`/api/impact/check?key=${encodeURIComponent(q)}`)).json();
        if (!data.results.length) { out.innerHTML = '<div class="master-warning-item">No QC data found for that PID.Invoice in the loaded exports.</div>'; return; }
        out.innerHTML = data.results.map(r => `<div class="impact-check-card">
            <strong>${escHtml(r.key)}</strong> ${r.in_qc_data ? '' : '<span class="text-muted">(not in the loaded QC exports)</span>'}
            <div>Period A: ${r.periods['Period A'].fails} fails of ${r.periods['Period A'].qc_done} QC'd (${nv(r.periods['Period A'].rate)}%) &nbsp;|&nbsp; Period B: ${r.periods['Period B'].fails} fails of ${r.periods['Period B'].qc_done} QC'd (${nv(r.periods['Period B'].rate)}%)</div>
            <div>${r.corrections.length ? r.corrections.map(c => `Corrected in <strong>${escHtml((c.sheet || '').trim())}</strong> (${fdate(c.date)}) by ${escHtml(c.person) || '-'}: ` +
                Object.entries(c.dims).map(([k, v]) => `${escHtml(k)} ${nv(v[0])}→${nv(v[1])}`).join(', ') + (c.remark ? ` · <em>${escHtml(c.remark)}</em>` : '')).join('<br>') : '<span class="text-muted">No correction on record</span>'}</div>
            <div>${r.lists.length ? r.lists.map(l => `On list <strong>${escHtml(l.list)}</strong>: ${nv(l.fails)} fails of ${nv(l.qc_done)} · status ${escHtml(l.status) || 'pending'}`).join('<br>') : '<span class="text-muted">Not on your failing lists</span>'}</div>
            <a class="cursor-pointer text-blue" onclick="quickLookupPID('${escHtml(r.key)}')">Open full history</a></div>`).join('');
    } catch (e) { out.innerHTML = `<div class="master-warning-item">Error: ${escHtml(e.message)}</div>`; }
}

// =============================================================================
// RECENT SHAPE CORRECTIONS LOG & UNIFIED LOGGING (Display when logging, like E2)
// =============================================================================
function setupRecentCorrectionsLog() {
    const btnRefresh = document.getElementById('btn-refresh-recent-log');
    if (btnRefresh) {
        btnRefresh.addEventListener('click', () => loadRecentCorrections());
    }

    const btnExport = document.getElementById('btn-export-log-card');
    if (btnExport) {
        btnExport.addEventListener('click', () => {
            const from = document.getElementById('sc-date-from') ? document.getElementById('sc-date-from').value : '';
            const to   = document.getElementById('sc-date-to') ? document.getElementById('sc-date-to').value : '';
            let url = '/api/shape/export/corrections_log';
            const params = [];
            if (from) params.push(`date_from=${from}`);
            if (to)   params.push(`date_to=${to}`);
            if (params.length) url += '?' + params.join('&');
            window.location = url;
        });
    }
}

async function loadRecentCorrections() {
    const tbody = document.getElementById('sc-recent-tbody');
    const badge = document.getElementById('sc-recent-count');
    if (!tbody) return;

    try {
        const res = await fetch('/api/shape/manual_corrections');
        if (!res.ok) throw new Error('Failed to load corrections');
        const list = await res.json();

        // Sort descending by timestamp
        list.sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''));

        if (badge) badge.textContent = `${list.length} entries`;
        renderRecentCorrections(list);
    } catch (e) {
        console.error('Failed to load recent corrections:', e);
        if (tbody) tbody.innerHTML = `<tr><td colspan="11" class="text-center text-muted" style="padding:16px;">Failed to load log: ${escHtml(e.message)}</td></tr>`;
    }
}

function renderRecentCorrections(list) {
    const tbody = document.getElementById('sc-recent-tbody');
    if (!tbody) return;

    if (!list || list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="11" class="text-center text-muted" style="padding: 20px;">No shape corrections logged yet. Enter a PID above to log one!</td></tr>`;
        return;
    }

    const formatDim = (d) => (d != null ? d : '--');

    tbody.innerHTML = list.map(entry => {
        const type = entry.correction_type || (entry.issue_raw && entry.issue_raw.toLowerCase().includes('trac') ? 'Traced' : 'Manual');
        const typeClass = type.toLowerCase() === 'manual' ? 'manual' : 'traced';

        const b = entry.dims_before || {};
        const a = entry.dims_after || {};

        const a_val = entry.a != null ? entry.a : b.A;
        const b_val = entry.b != null ? entry.b : b.B;
        const cr_val = entry.circ_r != null ? entry.circ_r : b.CIRC_R;
        const cl_val = entry.circ_l != null ? entry.circ_l : b.CIRC_L;

        const a1_val = entry.a1 != null ? entry.a1 : a.A1;
        const b1_val = entry.b1 != null ? entry.b1 : a.B1;
        const cr1_val = entry.circ_r1 != null ? entry.circ_r1 : a.CIRC_R1;
        const cl1_val = entry.circ_l1 != null ? entry.circ_l1 : a.CIRC_L1;

        const beforeStr = [a_val, b_val, cr_val, cl_val].some(x => x != null)
            ? `${formatDim(a_val)} / ${formatDim(b_val)} / ${formatDim(cr_val)} / ${formatDim(cl_val)}`
            : '--';

        const afterStr = [a1_val, b1_val, cr1_val, cl1_val].some(x => x != null)
            ? `${formatDim(a1_val)} / ${formatDim(b1_val)} / ${formatDim(cr1_val)} / ${formatDim(cl1_val)}`
            : '--';

        const devStr = entry.percentage_dev != null ? `${entry.percentage_dev}%` : '--';
        const tsStr = entry.timestamp ? entry.timestamp.slice(0, 19) : '--';
        const pidDisplay = entry.pid_invoice || entry.pid || '--';

        return `
            <tr>
                <td style="white-space: nowrap; font-size: 0.78rem; color: var(--text-muted);">${escHtml(tsStr)}</td>
                <td><strong class="text-blue cursor-pointer" onclick="quickLookupPID('${escHtml(entry.pid || '')}')">${escHtml(pidDisplay)}</strong></td>
                <td><span class="badge-corr-type ${typeClass}">${escHtml(type)}</span></td>
                <td>${escHtml(entry.issue_raw || 'Shape Correction')}</td>
                <td>${escHtml(entry.done_by || '--')}</td>
                <td>${escHtml(entry.shift_ic || '--')}</td>
                <td style="font-family: monospace; font-size: 0.76rem;">${escHtml(beforeStr)}</td>
                <td style="font-family: monospace; font-size: 0.76rem; color: #38bdf8;">${escHtml(afterStr)}</td>
                <td>${escHtml(devStr)}</td>
                <td style="max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escHtml(entry.notes || '')}">${escHtml(entry.notes || '--')}</td>
                <td style="text-align: center;">
                    <button type="button" class="btn-delete-row" onclick="deleteRecentCorrection('${escHtml(entry.id)}', '${escHtml(entry.pid)}')" title="Delete Entry">
                        🗑️
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

async function deleteRecentCorrection(entryId, pid) {
    if (!entryId || !confirm(`Delete correction record for PID #${pid}?`)) return;
    try {
        const res = await fetch(`/api/shape/manual_corrections/${encodeURIComponent(entryId)}`, { method: 'DELETE' });
        if (!res.ok) throw new Error("Delete failed");
        await loadRecentCorrections();
        await fetchMetrics();
        if (currentLookupPID) fetchPIDHistory(currentLookupPID);
        showLogFeedback('✓ Correction removed.', 'success');
    } catch (e) {
        alert(`Error deleting correction: ${e.message}`);
    }
}

function focusMainLogForm(pid) {
    // Switch to main analytics dashboard where the focal log strip is
    const btnTab = document.getElementById('tab-btn-analytics');
    if (btnTab) btnTab.click();

    const inputPid = document.getElementById('sc-log-pid');
    if (inputPid && pid) {
        inputPid.value = pid;
    }

    const logStrip = document.getElementById('sc-log-strip');
    if (logStrip) {
        logStrip.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    if (inputPid) {
        setTimeout(() => inputPid.focus(), 300);
    }
}

function quickLookupPID(pid) {
    document.getElementById('tab-btn-explorer').click();
    document.getElementById('subtab-pid').click();
    document.getElementById('exp-pid-input').value = pid;
    fetchPIDHistory(pid);
}
