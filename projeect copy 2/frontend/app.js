let globalData = null;

// Explorer state management
const expClassState = { page: 1, limit: 50, search: "", sort_by: "pid", sort_order: "asc", status: "all" };
const expFailsState = { page: 1, limit: 50, search: "", sort_by: "QC_created_date", sort_order: "desc", period: "all" };
const expMasterState = { page: 1, limit: 50, search: "", sort_by: "date", sort_order: "desc", type: "all", date_from: "", date_to: "" };
const expCorrState = { page: 1, limit: 50, search: "", sort_by: "timestamp", sort_order: "desc" };

document.addEventListener('DOMContentLoaded', () => {
    checkStatus();
    setupDropzones();
    setupMainTabs();
    setupExplorerSubtabs();
    setupExplorerControls();
    setupManualCorrectionModal();
    setupHeroSearch();

    document.getElementById('btn-close-modal').addEventListener('click', () => {
        document.getElementById('drilldown-modal').classList.add('hidden');
    });
});

// =====================
// HERO SEARCH (top bar)
// =====================
function setupHeroSearch() {
    const input = document.getElementById('hero-pid-search');
    const btn = document.getElementById('hero-pid-search-btn');
    const logBtn = document.getElementById('btn-log-correction-top');

    const doSearch = () => {
        const q = input.value.trim();
        if (q) {
            // Switch to explorer view, PID tab
            document.getElementById('tab-btn-explorer').click();
            document.getElementById('subtab-pid').click();
            document.getElementById('exp-pid-input').value = q;
            fetchPIDHistory(q);
        }
    };

    btn.addEventListener('click', doSearch);
    input.addEventListener('keypress', (e) => { if (e.key === 'Enter') doSearch(); });
    logBtn.addEventListener('click', () => openManualCorrectionModal());
}

// =====================
// STATUS & DATA LOADING
// =====================
async function checkStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        if (data.uploaded) {
            updateLabels(data);
            fetchMetrics();
        }
    } catch (e) {
        console.error("Status check failed:", e);
    }
}

function updateLabels(data) {
    if (data.week_past_label) document.getElementById('lbl-past-period').innerText = data.week_past_label;
    if (data.week_this_label) document.getElementById('lbl-this-period').innerText = data.week_this_label;

    const banner = document.getElementById('row-cap-warning-banner');
    if (data.row_cap_notes && data.row_cap_notes.length) {
        banner.querySelector('.warning-text').innerHTML = `<strong>Warning:</strong> ${data.row_cap_notes.map(escHtml).join(' ')} Re-export in smaller date ranges to get complete numbers.`;
    }
    if (data.row_cap_warning) {
        banner.classList.remove('hidden');
    } else {
        banner.classList.add('hidden');
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

    zone.addEventListener('click', () => input.click());
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
    const formData = new FormData();
    formData.append('file', file);
    try {
        const res = await fetch(apiUrl, { method: 'POST', body: formData });
        if (!res.ok) {
            let errorMsg = "Upload failed";
            try { const errJson = await res.json(); if (errJson.detail) errorMsg = errJson.detail; } catch (_) {}
            throw new Error(errorMsg);
        }
        const data = await res.json();
        labelEl.innerText = `Loaded: ${file.name}`;
        updateLabels(data);
        fetchMetrics();
    } catch (e) {
        alert(e.message);
        labelEl.innerText = "Upload failed. Try again.";
    }
}

// =====================
// METRICS FETCH & RENDER
// =====================
async function fetchMetrics() {
    try { await fetchMetricsCore(); } finally { refreshImpactIfOpen(); }
}

async function fetchMetricsCore() {
    try {
        const res = await fetch('/api/metrics');
        if (!res.ok) throw new Error("Error fetching metrics");
        const data = await res.json();
        globalData = data;

        renderKPIs(data.summary);
        renderParetoChart(data.pareto);
        renderShiftDriftChart(data.shift_drift);
        renderCorrectionEffectiveness(data.correction_effectiveness, data.summary);
        renderActionList(data.action_list);
    } catch (e) {
        console.error("Fetch metrics error:", e);
    }
}

const PLOT_BASE = {
    font: { family: 'Inter', color: '#8b949e', size: 11 },
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    margin: { l: 45, r: 15, t: 10, b: 70 },
    legend: { orientation: 'h', y: -0.25, font: { color: '#f0f2f5', size: 11 } },
    yaxis: { gridcolor: 'rgba(255,255,255,0.08)', zeroline: false },
    barmode: 'group'
};
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

function renderParetoChart(pareto) {
    const x = pareto.map(p => p.reason);
    const bar = (name, key, color) => ({ x, y: pareto.map(p => p[key]), name, type: 'bar', marker: { color },
        text: pareto.map(p => p[key]), textposition: 'outside', textfont: { color: '#f0f2f5' } });
    Plotly.newPlot('chart-pareto', [bar('Period A', 'a', COLOR_A), bar('Period B', 'b', COLOR_B)],
        { ...PLOT_BASE, yaxis: { ...PLOT_BASE.yaxis, title: 'Failed lenses' } }, { responsive: true, displayModeBar: false });
}

function renderShiftDriftChart(shift) {
    const x = shift.map(s => s.shift.replace(/ Shift/, '').replace(/ \(.*\)/, '') + (s.shift.includes('(') ? '<br>' + s.shift.match(/\((.*)\)/)[1] : ''));
    const bar = (name, rk, ek, qk, color) => ({
        x, y: shift.map(s => s[rk]), name, type: 'bar', marker: { color },
        text: shift.map(s => s[rk] + '%'), textposition: 'outside', textfont: { color: '#f0f2f5' },
        customdata: shift.map(s => [s[ek], s[qk]]), hovertemplate: '%{y}%  (%{customdata[0]} fails of %{customdata[1]} QC\'d)<extra>' + name + '</extra>'
    });
    Plotly.newPlot('chart-shift-drift', [bar('Period A', 'rate_a', 'events_a', 'qc_a', COLOR_A), bar('Period B', 'rate_b', 'events_b', 'qc_b', COLOR_B)],
        { ...PLOT_BASE, yaxis: { ...PLOT_BASE.yaxis, title: 'Fail rate %' } }, { responsive: true, displayModeBar: false });
}

function renderCorrectionEffectiveness(eff, summary) {
    const trace = {
        labels: ['Corrected', 'Recurred', 'Pending', 'Unlogged'],
        values: [eff.corrected, eff.recurred, eff.pending, eff.corrected_unlogged],
        type: 'pie', hole: 0.55, marker: { colors: ['#00e676', '#ff1744', '#ffeb3b', '#e040fb'] },
        textinfo: 'label+value', textfont: { color: '#f0f2f5', size: 12 }, hoverinfo: 'label+percent+value'
    };
    Plotly.newPlot('chart-correction-eff', [trace], {
        font: PLOT_BASE.font, paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
        margin: { l: 20, r: 20, t: 10, b: 10 }, showlegend: true,
        legend: { orientation: 'h', y: -0.1, font: { color: '#f0f2f5', size: 10 } },
        annotations: [{ text: `${summary.weekly_correction_pct}%<br>Fixed`, showarrow: false, font: { size: 18, color: '#00e676', family: 'Outfit' } }]
    }, { responsive: true, displayModeBar: false });
}

function renderActionList(list) {
    document.getElementById('action-table-body').innerHTML = (list || []).map(c => `
        <tr>
            <td><strong class="cursor-pointer text-blue" onclick="quickLookupPID('${escHtml(c.pid)}')">${escHtml(c.pid)}</strong></td>
            <td><span class="tag tag-${escHtml(c.classification)}">${escHtml(c.classification)}</span></td>
            <td>${c.fail_event_count}</td><td>${c.fail_events_b}</td>
            <td>${escHtml(c.reason_cluster)}</td>
            <td>${c.correction_timestamp && c.correction_timestamp !== 'N/A' ? escHtml(c.correction_timestamp) : '-'}</td>
            <td>${escHtml(c.done_by) || '-'}</td>
        </tr>`).join('') || '<tr><td colspan="7" class="text-center text-muted">No Recurred or Pending PIDs</td></tr>';
}

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
    document.getElementById('btn-impact-log').addEventListener('click', () => openManualCorrectionModal());
    document.getElementById('btn-impact-check').addEventListener('click', checkPidInvoice);
    document.getElementById('impact-check-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') checkPidInvoice(); });
}

function setupExplorerSubtabs() {
    const subtabs = [
        { btn: 'subtab-master', panel: 'exp-panel-master', action: refreshMaster },
        { btn: 'subtab-pid', panel: 'exp-panel-pid' },
        { btn: 'subtab-classifications', panel: 'exp-panel-classifications', action: fetchExplorerClassifications },
        { btn: 'subtab-clusters', panel: 'exp-panel-clusters', action: fetchExplorerClusters },
        { btn: 'subtab-fails', panel: 'exp-panel-fails', action: fetchExplorerFails },
        { btn: 'subtab-corrections', panel: 'exp-panel-corrections', action: fetchExplorerCorrections }
    ];

    subtabs.forEach(tab => {
        document.getElementById(tab.btn).addEventListener('click', () => {
            subtabs.forEach(t => {
                document.getElementById(t.btn).classList.remove('active');
                document.getElementById(t.panel).classList.add('hidden');
            });
            document.getElementById(tab.btn).classList.add('active');
            document.getElementById(tab.panel).classList.remove('hidden');
            if (tab.action) tab.action();
        });
    });
}

function setupExplorerControls() {
    // PID Lookup
    const pidInput = document.getElementById('exp-pid-input');
    const pidBtn = document.getElementById('exp-pid-btn');
    const execPid = () => { const q = pidInput.value.trim(); if (q) fetchPIDHistory(q); };
    pidBtn.addEventListener('click', execPid);
    pidInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') execPid(); });

    // Classifications
    bindExplorerTableControls('exp-class', expClassState, fetchExplorerClassifications, [], 'exp-class-status-filter', 'status');
    // Fails
    bindExplorerTableControls('exp-fails', expFailsState, fetchExplorerFails, [], 'exp-fails-period-filter', 'period');
    // Corrections
    bindExplorerTableControls('exp-corr', expCorrState, fetchExplorerCorrections);
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

        document.getElementById('btn-pid-add-correction').onclick = () => openManualCorrectionModal(data.pid);

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

// =====================
// MANUAL CORRECTION MODAL
// =====================
function setupManualCorrectionModal() {
    const modal = document.getElementById('manual-correction-modal');
    const btnOpen = document.getElementById('btn-open-manual-corr-modal');
    const btnClose = document.getElementById('btn-close-manual-modal');
    const btnCancel = document.getElementById('btn-cancel-manual-modal');
    const form = document.getElementById('form-manual-correction');
    const issueSelect = document.getElementById('manual-issue-select');
    const issueCustom = document.getElementById('manual-issue-custom');

    if (btnOpen) btnOpen.addEventListener('click', () => openManualCorrectionModal());
    if (btnClose) btnClose.addEventListener('click', () => modal.classList.add('hidden'));
    if (btnCancel) btnCancel.addEventListener('click', () => modal.classList.add('hidden'));

    if (issueSelect) {
        issueSelect.addEventListener('change', (e) => {
            if (e.target.value === '__custom__') {
                issueCustom.classList.remove('hidden');
            } else {
                issueCustom.classList.add('hidden');
            }
        });
    }

    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            await saveManualCorrectionForm();
        });
    }
}

function openManualCorrectionModal(pid = '', existingEntry = null) {
    const modal = document.getElementById('manual-correction-modal');
    document.getElementById('manual-entry-id').value = existingEntry ? existingEntry.id : '';
    
    // Fill in values if existing entry
    let p_val = existingEntry ? (existingEntry.pid_invoice || existingEntry.pid) : pid;
    document.getElementById('manual-pid').value = p_val || '';
    
    document.getElementById('manual-done-by').value = existingEntry ? existingEntry.done_by : 'QC Lead';
    
    const now = new Date();
    document.getElementById('manual-timestamp').value = existingEntry && existingEntry.timestamp 
        ? existingEntry.timestamp.slice(0, 16) 
        : new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
        
    document.getElementById('manual-issue-select').value = existingEntry ? existingEntry.issue_raw : 'Wrong shape cut by machine';
    document.getElementById('manual-issue-custom').classList.add('hidden');
    document.getElementById('manual-issue-custom').value = '';
    
    document.getElementById('manual-percentage-dev').value = existingEntry ? existingEntry.percentage_dev : '';
    
    document.getElementById('manual-dim-a').value = existingEntry && existingEntry.dims_before ? existingEntry.dims_before.A : '';
    document.getElementById('manual-dim-b').value = existingEntry && existingEntry.dims_before ? existingEntry.dims_before.B : '';
    document.getElementById('manual-dim-circ-r').value = existingEntry && existingEntry.dims_before ? existingEntry.dims_before.CIRC_R : '';
    document.getElementById('manual-dim-circ-l').value = existingEntry && existingEntry.dims_before ? existingEntry.dims_before.CIRC_L : '';
    
    document.getElementById('manual-dim-a1').value = existingEntry && existingEntry.dims_after ? existingEntry.dims_after.A1 : '';
    document.getElementById('manual-dim-b1').value = existingEntry && existingEntry.dims_after ? existingEntry.dims_after.B1 : '';
    document.getElementById('manual-dim-circ-r1').value = existingEntry && existingEntry.dims_after ? existingEntry.dims_after.CIRC_R1 : '';
    document.getElementById('manual-dim-circ-l1').value = existingEntry && existingEntry.dims_after ? existingEntry.dims_after.CIRC_L1 : '';
    
    document.getElementById('manual-notes').value = existingEntry ? existingEntry.notes : '';
    document.getElementById('manual-before-qc').value = existingEntry && existingEntry.before_qc_done != null ? existingEntry.before_qc_done : '';
    document.getElementById('manual-before-fails').value = existingEntry && existingEntry.before_fails != null ? existingEntry.before_fails : '';
    modal.classList.remove('hidden');
}

async function saveManualCorrectionForm() {
    const pid = document.getElementById('manual-pid').value.trim();
    const doneBy = document.getElementById('manual-done-by').value.trim() || 'QC Lead';
    const ts = document.getElementById('manual-timestamp').value;
    const issueSelect = document.getElementById('manual-issue-select').value;
    const issueCustom = document.getElementById('manual-issue-custom').value.trim();
    const issueRaw = (issueSelect === '__custom__') ? (issueCustom || 'Manual Shape Correction') : issueSelect;

    const payload = {
        id: document.getElementById('manual-entry-id').value || null,
        pid: pid,
        pid_invoice: pid,
        done_by: doneBy,
        timestamp: ts ? ts.replace('T', ' ') + ':00' : null,
        issue_raw: issueRaw,
        percentage_dev: !isNaN(parseFloat(document.getElementById('manual-percentage-dev').value)) ? parseFloat(document.getElementById('manual-percentage-dev').value) : null,
        a: !isNaN(parseFloat(document.getElementById('manual-dim-a').value)) ? parseFloat(document.getElementById('manual-dim-a').value) : null,
        b: !isNaN(parseFloat(document.getElementById('manual-dim-b').value)) ? parseFloat(document.getElementById('manual-dim-b').value) : null,
        circ_r: !isNaN(parseFloat(document.getElementById('manual-dim-circ-r').value)) ? parseFloat(document.getElementById('manual-dim-circ-r').value) : null,
        circ_l: !isNaN(parseFloat(document.getElementById('manual-dim-circ-l').value)) ? parseFloat(document.getElementById('manual-dim-circ-l').value) : null,
        a1: !isNaN(parseFloat(document.getElementById('manual-dim-a1').value)) ? parseFloat(document.getElementById('manual-dim-a1').value) : null,
        b1: !isNaN(parseFloat(document.getElementById('manual-dim-b1').value)) ? parseFloat(document.getElementById('manual-dim-b1').value) : null,
        circ_r1: !isNaN(parseFloat(document.getElementById('manual-dim-circ-r1').value)) ? parseFloat(document.getElementById('manual-dim-circ-r1').value) : null,
        circ_l1: !isNaN(parseFloat(document.getElementById('manual-dim-circ-l1').value)) ? parseFloat(document.getElementById('manual-dim-circ-l1').value) : null,
        before_qc_done: !isNaN(parseFloat(document.getElementById('manual-before-qc').value)) ? parseFloat(document.getElementById('manual-before-qc').value) : null,
        before_fails: !isNaN(parseFloat(document.getElementById('manual-before-fails').value)) ? parseFloat(document.getElementById('manual-before-fails').value) : null,
        notes: document.getElementById('manual-notes').value.trim()
    };

    try {
        const res = await fetch('/api/manual_corrections', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error("Failed to save");

        document.getElementById('manual-correction-modal').classList.add('hidden');
        await fetchMetrics();
        if (currentLookupPID && currentLookupPID === pid) fetchPIDHistory(pid);
        alert(`✓ Correction saved for PID #${pid}. Dashboard updated.`);
    } catch (e) {
        alert(`Error: ${e.message}`);
    }
}
async function handleDeleteManualCorrection(entryId, pid) {
    if (!entryId || !confirm(`Delete correction for PID #${pid}?`)) return;
    try {
        const res = await fetch(`/api/manual_corrections/${encodeURIComponent(entryId)}`, { method: 'DELETE' });
        if (!res.ok) throw new Error("Delete failed");
        await fetchMetrics();
        if (currentLookupPID) fetchPIDHistory(currentLookupPID);
        alert(`✓ Correction removed.`);
    } catch (e) {
        alert(`Error: ${e.message}`);
    }
}

function quickLookupPID(pid) {
    document.getElementById('tab-btn-explorer').click();
    document.getElementById('subtab-pid').click();
    document.getElementById('exp-pid-input').value = pid;
    fetchPIDHistory(pid);
}
