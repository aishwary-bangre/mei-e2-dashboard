import os

# To revert we can just use sed or python replace based on what I changed

# frontend/index.html
with open('frontend/index.html', 'r') as f:
    html = f.read()

# restore modal
start = html.find('    <div class="modal-overlay hidden" id="manual-correction-modal">')
end = html.find('    <!-- Drilldown Modal -->')

original_modal = """    <div class="modal-overlay hidden" id="manual-correction-modal">
        <div class="glass-card modal-card modal-lg">
            <div class="modal-header">
                <div>
                    <h3 id="manual-modal-title">Log Physical Shape Correction</h3>
                    <p class="modal-subtitle">Save correction entry to update analysis live</p>
                </div>
                <button class="btn-close" id="btn-close-manual-modal">✕</button>
            </div>
            <form id="form-manual-correction" class="modal-form">
                <input type="hidden" id="manual-entry-id" />
                <div class="form-row">
                    <div class="form-group">
                        <label for="manual-pid">PID.Invoice <span class="req">*</span></label>
                        <input type="text" id="manual-pid" required placeholder="e.g. 219754.INV123" class="form-input" />
                    </div>
                    <div class="form-group">
                        <label for="manual-done-by">Technician</label>
                        <input type="text" id="manual-done-by" placeholder="e.g. QC Lead" class="form-input" />
                    </div>
                    <div class="form-group">
                        <label for="manual-timestamp">Date</label>
                        <input type="datetime-local" id="manual-timestamp" class="form-input" />
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group span-2">
                        <label for="manual-issue-select">Correction Reason</label>
                        <select id="manual-issue-select" class="form-input">
                            <option value="Wrong shape cut by machine">Wrong shape cut by machine</option>
                            <option value="SMALL SIZE CUT BY MACHINE">SMALL SIZE CUT BY MACHINE</option>
                            <option value="Lens Big Size issue">Lens Big Size issue</option>
                            <option value="Lens slip by machine">Lens slip by machine</option>
                            <option value="__custom__">-- Custom --</option>
                        </select>
                        <input type="text" id="manual-issue-custom" placeholder="Custom reason..." class="form-input hidden mt-2" />
                    </div>
                    <div class="form-group">
                        <label for="manual-percentage-dev">% Deviation</label>
                        <input type="number" step="0.01" id="manual-percentage-dev" placeholder="-1.25" class="form-input" />
                    </div>
                </div>
                <div class="form-section-title"><span>Dimensions (mm)</span></div>
                <div class="form-row-dimensions">
                    <div class="dim-column">
                        <h4>Before</h4>
                        <div class="dim-inputs-grid">
                            <div class="form-group"><label>A</label><input type="number" step="0.01" id="manual-dim-a" class="form-input" /></div>
                            <div class="form-group"><label>B</label><input type="number" step="0.01" id="manual-dim-b" class="form-input" /></div>
                            <div class="form-group"><label>CIRC R</label><input type="number" step="0.01" id="manual-dim-circ-r" class="form-input" /></div>
                            <div class="form-group"><label>CIRC L</label><input type="number" step="0.01" id="manual-dim-circ-l" class="form-input" /></div>
                        </div>
                    </div>
                    <div class="dim-arrow">➔</div>
                    <div class="dim-column">
                        <h4>After</h4>
                        <div class="dim-inputs-grid">
                            <div class="form-group"><label>A1</label><input type="number" step="0.01" id="manual-dim-a1" class="form-input" /></div>
                            <div class="form-group"><label>B1</label><input type="number" step="0.01" id="manual-dim-b1" class="form-input" /></div>
                            <div class="form-group"><label>CIRC R1</label><input type="number" step="0.01" id="manual-dim-circ-r1" class="form-input" /></div>
                            <div class="form-group"><label>CIRC L1</label><input type="number" step="0.01" id="manual-dim-circ-l1" class="form-input" /></div>
                        </div>
                    </div>
                </div>
                <div class="form-group mt-3">
                    <label for="manual-notes">Notes</label>
                    <input type="text" id="manual-notes" placeholder="Calibration remarks..." class="form-input" />
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" id="btn-cancel-manual-modal">Cancel</button>
                    <button type="submit" class="btn btn-primary" id="btn-submit-manual-correction">Save &amp; Recalculate</button>
                </div>
            </form>
        </div>
    </div>
"""

with open('frontend/index.html', 'w') as f:
    f.write(html[:start] + original_modal + html[end:])


# frontend/app.js
with open('frontend/app.js', 'r') as f:
    app_js = f.read()

app_js_start = app_js.find('// MANUAL CORRECTION MODAL')
app_js_end = app_js.find('async function handleDeleteManualCorrection')

original_app_js = """// MANUAL CORRECTION MODAL
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
"""

with open('frontend/app.js', 'w') as f:
    f.write(app_js[:app_js_start] + original_app_js + app_js[app_js_end:])


