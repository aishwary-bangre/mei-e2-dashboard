let globalData = null;

// Explorer state management
const expClassState = { page: 1, limit: 50, search: "", sort_by: "pid", sort_order: "asc", status: "all" };
const expFailsState = { page: 1, limit: 50, search: "", sort_by: "QC_created_date", sort_order: "desc", period: "all" };
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
    try {
        const res = await fetch('/api/metrics');
        if (!res.ok) throw new Error("Error fetching metrics");
        const data = await res.json();
        globalData = data;

        renderKPIs(data.summary);
        renderParetoChart(data.pareto);
        renderMachineTable(data.machine_table);
        renderHeatmap(data.heatmap_machine_issue);
        renderCorrectionEffectiveness(data.correction_effectiveness, data.summary);
        renderShiftDriftChart(data.shift_drift);
    } catch (e) {
        console.error("Fetch metrics error:", e);
    }
}

function renderKPIs(s) {
    document.getElementById('kpi-fail-rate').innerText = `${s.mei_fail_rate}%`;
    document.getElementById('kpi-machine-failures').innerText = s.total_mei_fail_events.toLocaleString();
    document.getElementById('kpi-recurred').innerText = s.recurred.toLocaleString();
    document.getElementById('kpi-pending').innerText = s.pending.toLocaleString();
}

function renderParetoChart(pareto) {
    if (!pareto || pareto.length === 0) return;
    const reasons = pareto.map(p => p.reason);
    const counts = pareto.map(p => p.count);
    const cumPcts = pareto.map(p => p.cumulative_pct);

    const traceBar = {
        x: reasons, y: counts, name: 'Fail Events', type: 'bar',
        marker: { color: ['#00b0ff', '#7c4dff', '#e040fb', '#ffee58', '#ff1744', '#00e676'].slice(0, reasons.length) }
    };
    const traceLine = {
        x: reasons, y: cumPcts, name: 'Cumulative %', type: 'scatter',
        mode: 'lines+markers', yaxis: 'y2',
        line: { color: '#ffee58', width: 3 }, marker: { size: 7, color: '#ffee58' }
    };
    const layout = {
        font: { family: 'Inter', color: '#8b949e', size: 11 },
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
        margin: { l: 50, r: 50, t: 20, b: 80 },
        showlegend: true,
        legend: { orientation: 'h', y: 1.15, font: { color: '#f0f2f5' } },
        xaxis: { tickangle: -15, gridcolor: 'rgba(255,255,255,0.05)' },
        yaxis: { title: 'Failure Events', gridcolor: 'rgba(255,255,255,0.05)' },
        yaxis2: { title: 'Cumulative %', overlaying: 'y', side: 'right', range: [0, 105], showgrid: false }
    };
    Plotly.newPlot('chart-pareto', [traceBar, traceLine], layout, { responsive: true });

    document.getElementById('chart-pareto').on('plotly_click', (d) => {
        if (d.points && d.points[0]) openDrilldown('pareto', d.points[0].x);
    });
}

function renderMachineTable(machines) {
    const tbody = document.getElementById('machine-table-body');
    tbody.innerHTML = '';
    if (!machines || machines.length === 0) return;

    machines.forEach(m => {
        const tr = document.createElement('tr');
        tr.className = 'machine-row';
        tr.style.cursor = 'pointer';
        const failRateClass = m.fail_rate > 5 ? 'text-red' : m.fail_rate > 2 ? 'text-yellow' : 'text-green';
        const recurredClass = m.recurred > 0 ? 'text-red' : 'text-green';
        tr.innerHTML = `
            <td><strong class="text-blue">${m.machine}</strong></td>
            <td><strong>${m.failures}</strong></td>
            <td><span class="${failRateClass}">${m.fail_rate}%</span></td>
            <td>${m.top_issue}</td>
            <td><span class="${recurredClass}">${m.recurred}</span></td>
        `;
        tr.addEventListener('click', () => openDrilldown('machine', m.machine));
        tbody.appendChild(tr);
    });
}

function renderHeatmap(heatData) {
    if (!heatData || !heatData.x || heatData.x.length === 0) return;

    const trace = {
        x: heatData.x, y: heatData.y, z: heatData.z,
        type: 'heatmap', colorscale: [
            [0, '#0a0b12'], [0.25, '#1a237e'], [0.5, '#7c4dff'], [0.75, '#e040fb'], [1, '#ff1744']
        ],
        showscale: true,
        colorbar: { title: 'Count', titlefont: { color: '#8b949e' }, tickfont: { color: '#8b949e' } }
    };
    const layout = {
        font: { family: 'Inter', color: '#8b949e', size: 11 },
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
        margin: { l: 200, r: 40, t: 20, b: 80 },
        xaxis: { tickangle: -30 }, yaxis: {}
    };
    Plotly.newPlot('chart-heatmap', [trace], layout, { responsive: true });
}

function renderCorrectionEffectiveness(eff, summary) {
    const labels = ['Corrected', 'Recurred', 'Pending', 'Unlogged'];
    const values = [eff.corrected, eff.recurred, eff.pending, eff.corrected_unlogged];
    const colors = ['#00e676', '#ff1744', '#ffeb3b', '#e040fb'];

    const trace = {
        labels: labels, values: values, type: 'pie', hole: 0.55,
        marker: { colors: colors },
        textinfo: 'label+value', textfont: { color: '#f0f2f5', size: 12 },
        hoverinfo: 'label+percent+value'
    };
    const layout = {
        font: { family: 'Inter', color: '#8b949e', size: 11 },
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
        margin: { l: 20, r: 20, t: 20, b: 20 },
        showlegend: true,
        legend: { orientation: 'h', y: -0.1, font: { color: '#f0f2f5', size: 10 } },
        annotations: [{
            text: `${summary.weekly_correction_pct}%<br>Fixed`, showarrow: false,
            font: { size: 18, color: '#00e676', family: 'Outfit' }
        }]
    };
    Plotly.newPlot('chart-correction-eff', [trace], layout, { responsive: true });
}

function renderShiftDriftChart(shiftData) {
    if (!shiftData || shiftData.length === 0) return;
    const shifts = shiftData.map(s => s.shift.split(' ')[0]);
    const totalFails = shiftData.map(s => s.total_fails);

    const trace = {
        x: shifts, y: totalFails, type: 'bar',
        marker: { color: ['#00b0ff', '#7c4dff', '#e040fb', '#ffee58'] }
    };
    const layout = {
        font: { family: 'Inter', color: '#8b949e', size: 11 },
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
        margin: { l: 50, r: 20, t: 20, b: 40 },
        yaxis: { title: 'Fail Events', gridcolor: 'rgba(255,255,255,0.05)' },
        xaxis: { title: 'Shift' }
    };
    Plotly.newPlot('chart-shift-drift', [trace], layout, { responsive: true });
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
    const btnAnalytics = document.getElementById('tab-btn-analytics');
    const btnExplorer = document.getElementById('tab-btn-explorer');
    const viewAnalytics = document.getElementById('analytics-view');
    const viewExplorer = document.getElementById('explorer-view');

    btnAnalytics.addEventListener('click', () => {
        btnAnalytics.classList.add('active');
        btnExplorer.classList.remove('active');
        viewAnalytics.classList.remove('hidden');
        viewExplorer.classList.add('hidden');
    });

    btnExplorer.addEventListener('click', () => {
        btnExplorer.classList.add('active');
        btnAnalytics.classList.remove('active');
        viewExplorer.classList.remove('hidden');
        viewAnalytics.classList.add('hidden');
    });
}

function setupExplorerSubtabs() {
    const subtabs = [
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
                    <td>${c.done_by}</td>
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
                <td>${escHtml(r.done_by)}</td>
                <td>${actionCell}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Fetch corrections error:", e);
    }
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
