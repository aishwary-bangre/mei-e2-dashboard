// MEI E2 Analytics & Escalation Logging Client Logic

let activeTab = 'tab1';
let chartDonut = null;
let chartBar = null;
let chartPie = null;
let chartHourlyTrend = null;
let rawHourlyData = null;
let currentLookupData = null;
let cachedDropdownOptions = {};
let activeModalFieldId = null;

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    autoSelectCurrentShift();
    initScanner();
    loadDropdownOptions();
    checkImportMeta();
    loadEscalations();
    loadAnalytics();
    checkHealth();

    const savedTab = localStorage.getItem('mei_active_tab') || 'tab1';
    switchTab(savedTab);

    // Auto-update shift selector every minute and health every 10s
    setInterval(autoSelectCurrentShift, 60000);
    setInterval(checkHealth, 10000);
});

async function checkHealth() {
    try {
        const res = await fetch('/api/health');
        const data = await res.json();
        const dbPill = document.getElementById('lblDbStatus');
        const cardBadge = document.getElementById('lblQueryLatency');

        if (data.status === 'online') {
            if (dbPill) {
                dbPill.className = 'stat-pill badge-online';
                dbPill.innerHTML = '🟢 MySQL Connected';
            }
            if (cardBadge && cardBadge.textContent.includes('Offline')) {
                cardBadge.className = 'badge-status badge-ok';
                cardBadge.textContent = '🟢 Live SQL Active';
            }
        } else {
            if (dbPill) {
                dbPill.className = 'stat-pill badge-offline';
                dbPill.innerHTML = '🔴 Port 13306 Offline';
            }
            if (cardBadge && !cardBadge.textContent.includes('Fetched') && !cardBadge.textContent.includes('Cached')) {
                cardBadge.className = 'badge-status badge-ng';
                cardBadge.textContent = '🔌 Terminal Tunnel Offline';
            }
        }
    } catch (e) {}
}

function autoSelectCurrentShift() {
    const sel = document.getElementById('selShift');
    if (!sel) return;
    const hour = new Date().getHours();
    let currentShift = 'Shift A';
    if (hour >= 7 && hour < 15) {
        currentShift = 'Shift A';
    } else if (hour >= 15 && hour < 23) {
        currentShift = 'Shift B';
    } else {
        currentShift = 'Shift C';
    }
    sel.value = currentShift;
}

// -----------------------------------------------------------------------------
// 0. LIGHT / DARK THEME TOGGLE
// -----------------------------------------------------------------------------
function initTheme() {
    const savedTheme = localStorage.getItem('mei_theme') || 'dark';
    const btn = document.getElementById('btnThemeToggle');
    if (savedTheme === 'light') {
        document.body.classList.add('light-theme');
        if (btn) btn.innerHTML = '☀️';
    } else {
        document.body.classList.remove('light-theme');
        if (btn) btn.innerHTML = '🌙';
    }
}

function toggleTheme() {
    const isLight = document.body.classList.toggle('light-theme');
    const btn = document.getElementById('btnThemeToggle');
    if (isLight) {
        if (btn) btn.innerHTML = '☀️';
        localStorage.setItem('mei_theme', 'light');
    } else {
        if (btn) btn.innerHTML = '🌙';
        localStorage.setItem('mei_theme', 'dark');
    }
}

async function promptSetAdaptivePassword() {
    const pwd = prompt("Enter Adaptive Session Password (from terminal output):");
    if (pwd && pwd.trim()) {
        try {
            const res = await fetch('/api/config/password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: pwd.trim() })
            });
            const data = await res.json();
            if (data.success) {
                const dbPill = document.getElementById('lblDbStatus');
                if (dbPill) {
                    dbPill.className = 'stat-pill badge-online';
                    dbPill.innerHTML = '🟢 MySQL Connected';
                }
                const trayVal = document.getElementById('txtScanTray')?.value?.trim().toUpperCase();
                if (trayVal) {
                    triggerLookup(trayVal);
                }
            } else {
                alert("Failed to update password: " + (data.error || "Unknown error"));
            }
        } catch (e) {
            alert("Error updating password: " + e);
        }
    }
}

// -----------------------------------------------------------------------------
// 1. TAB SWITCHING LOGIC
// -----------------------------------------------------------------------------
function switchTab(tabId) {
    activeTab = tabId;
    localStorage.setItem('mei_active_tab', tabId);
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

    if (tabId === 'tab1') {
        document.getElementById('btnTab1').classList.add('active');
        document.getElementById('tab1').classList.add('active');
        document.getElementById('txtScanTray').focus();
    } else {
        document.getElementById('btnTab2').classList.add('active');
        document.getElementById('tab2').classList.add('active');
        loadAnalytics();
    }
}

// -----------------------------------------------------------------------------
// 2. DYNAMIC DROPDOWN OPTIONS MANAGEMENT (CRUD)
// -----------------------------------------------------------------------------
async function loadDropdownOptions() {
    try {
        const res = await fetch('/api/options');
        const data = await res.json();
        if (data.success) {
            cachedDropdownOptions = data.options;
            renderAllDropdownSelects();
        }
    } catch (err) {
        console.error('Failed to load dropdown options:', err);
    }
}

function renderAllDropdownSelects() {
    renderSelectElement('selShiftIc', cachedDropdownOptions.shift_ic || [], false);
    renderSelectElement('selOperator', cachedDropdownOptions.operator || [], false);
    renderSelectElement('selFailCategory', cachedDropdownOptions.fail_category || [], false);
    renderSelectElement('selStatus', cachedDropdownOptions.status || [], false);
    renderSelectElement('selIssue', cachedDropdownOptions.issue || [], true);

    onFailCategoryChange();
}

let tsInstances = {}; // Track TomSelect instances

function renderSelectElement(selectId, optionsList, useTomSelect = true) {
    const el = document.getElementById(selectId);
    if (!el) return;

    if (useTomSelect) {
        if (tsInstances[selectId]) {
            const ts = tsInstances[selectId];
            const curVal = ts.getValue();
            ts.clearOptions();
            optionsList.forEach(opt => {
                ts.addOption({value: opt, text: opt});
            });
            if (curVal) ts.setValue(curVal);
            ts.refreshOptions(false);
        } else {
            const curVal = el.value;
            el.innerHTML = '';
            
            const defaultPlaceholder = document.createElement('option');
            defaultPlaceholder.value = '';
            defaultPlaceholder.textContent = 'Search & Select...';
            el.appendChild(defaultPlaceholder);

            optionsList.forEach(opt => {
                const optionEl = document.createElement('option');
                optionEl.value = opt;
                optionEl.textContent = opt;
                if (opt === curVal) optionEl.selected = true;
                el.appendChild(optionEl);
            });
            
            const ts = new TomSelect('#' + selectId, {
                create: false,
                sortField: { field: "text", direction: "asc" },
                dropdownParent: 'body',
                maxOptions: null
            });

            const positionAbove = () => {
                if (!ts.isOpen) return;
                const control = ts.control;
                const dropdown = ts.dropdown;
                if (!control || !dropdown) return;
                const rect = control.getBoundingClientRect();
                const dropdownHeight = dropdown.offsetHeight || 400;
                dropdown.style.position = 'absolute';
                dropdown.style.left = rect.left + window.scrollX + 'px';
                dropdown.style.width = rect.width + 'px';
                dropdown.style.top = Math.max(10, rect.top + window.scrollY - dropdownHeight - 4) + 'px';
                dropdown.style.bottom = 'auto';
                dropdown.style.borderRadius = '8px 8px 0 0';
                dropdown.style.boxShadow = '0 -12px 36px rgba(0, 0, 0, 0.85)';
            };

            ts.on('dropdown_open', () => {
                positionAbove();
                requestAnimationFrame(positionAbove);
                setTimeout(positionAbove, 20);
            });

            ts.on('type', () => {
                setTimeout(positionAbove, 10);
            });

            tsInstances[selectId] = ts;
        }
    } else {
        const curVal = el.value;
        el.innerHTML = '';

        optionsList.forEach((opt, idx) => {
            const optionEl = document.createElement('option');
            optionEl.value = opt;
            optionEl.textContent = opt;
            optionEl.style.backgroundColor = '#111827';
            optionEl.style.color = '#F9FAFB';
            if (curVal && optionsList.includes(curVal)) {
                if (opt === curVal) optionEl.selected = true;
            } else {
                if (idx === 0) optionEl.selected = true;
            }
            el.appendChild(optionEl);
        });
    }
}

function openOptionsModal(fieldId, fieldLabel) {
    activeModalFieldId = fieldId;
    document.getElementById('modalTitle').textContent = `⚙️ Manage Options: ${fieldLabel}`;
    document.getElementById('modalOptions').classList.add('active');
    document.getElementById('txtNewOption').value = '';
    renderModalOptionsList();
}

function closeOptionsModal() {
    document.getElementById('modalOptions').classList.remove('active');
    activeModalFieldId = null;
}

function renderModalOptionsList() {
    if (!activeModalFieldId) return;

    const container = document.getElementById('optionsList');
    container.innerHTML = '';

    const list = cachedDropdownOptions[activeModalFieldId] || [];

    if (list.length === 0) {
        container.innerHTML = '<div style="color: var(--text-muted); text-align: center;">No options found. Add one above!</div>';
        return;
    }

    list.forEach(opt => {
        const row = document.createElement('div');
        row.className = 'option-row-item';

        row.innerHTML = `
            <div class="option-name-text">${opt}</div>
            <div class="option-actions-group" style="display: flex; gap: 6px; align-items: center;">
                <button type="button" class="btn-action-icon" onclick="editOptionPrompt('${opt}')" title="Edit text">✏️</button>
                <button type="button" class="btn-action-icon btn-action-delete" onclick="deleteOptionConfirm('${opt}')" title="Delete option">🗑️</button>
            </div>
        `;
        container.appendChild(row);
    });
}

async function addNewOption() {
    if (!activeModalFieldId) return;
    const txtInput = document.getElementById('txtNewOption');
    const val = txtInput.value.trim();

    if (!val) {
        alert('Please enter an option name.');
        return;
    }

    try {
        const res = await fetch(`/api/options/${activeModalFieldId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ option: val })
        });
        const data = await res.json();

        if (data.success) {
            cachedDropdownOptions[activeModalFieldId] = data.options;
            txtInput.value = '';
            renderModalOptionsList();
            renderAllDropdownSelects();
        } else {
            alert(data.error || 'Failed to add option');
        }
    } catch (err) {
        console.error('Error adding option:', err);
    }
}

async function editOptionPrompt(oldOpt) {
    if (!activeModalFieldId) return;
    const newOpt = prompt(`Edit option name for '${oldOpt}':`, oldOpt);

    if (newOpt === null || !newOpt.trim() || newOpt.trim().toUpperCase() === oldOpt) {
        return;
    }

    try {
        const res = await fetch(`/api/options/${activeModalFieldId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_option: oldOpt, new_option: newOpt.trim() })
        });
        const data = await res.json();

        if (data.success) {
            cachedDropdownOptions[activeModalFieldId] = data.options;
            renderModalOptionsList();
            renderAllDropdownSelects();
        } else {
            alert(data.error || 'Failed to edit option');
        }
    } catch (err) {
        console.error('Error editing option:', err);
    }
}

async function deleteOptionConfirm(optToDelete) {
    if (!activeModalFieldId) return;

    try {
        const res = await fetch(`/api/options/${activeModalFieldId}/${encodeURIComponent(optToDelete)}`, {
            method: 'DELETE'
        });
        const data = await res.json();

        if (data.success) {
            cachedDropdownOptions[activeModalFieldId] = data.options;
            renderModalOptionsList();
            renderAllDropdownSelects();
        } else {
            alert(data.error || 'Failed to delete option');
        }
    } catch (err) {
        console.error('Error deleting option:', err);
    }
}

// -----------------------------------------------------------------------------
// 3. DYNAMIC FAILED ITEM BARCODE ENTRY BOX GENERATION
// -----------------------------------------------------------------------------
function onFailCategoryChange() {
    const category = document.getElementById('selFailCategory').value;
    const container = document.getElementById('failedBarcodesContainer');
    if (!container) return;
    container.innerHTML = '';

    let html = '';
    const rightVal = currentLookupData ? (currentLookupData.right_lens_barcode || '') : '';
    const leftVal = currentLookupData ? (currentLookupData.left_lens_barcode || '') : '';
    const frameVal = currentLookupData ? (currentLookupData.frame_pid || '') : '';

    if (category === 'LEFT LENS') {
        html = `
            <div class="form-group" style="margin-bottom: 0;">
                <label for="txtFailedLeftBarcode" style="color:#FF7660;">⚠️ FAILED LEFT LENS BARCODE</label>
                <input type="text" id="txtFailedLeftBarcode" class="input-control" value="${leftVal}" placeholder="Scan/Enter Left Lens Barcode">
            </div>
        `;
    } else if (category === 'RIGHT LENS') {
        html = `
            <div class="form-group" style="margin-bottom: 0;">
                <label for="txtFailedRightBarcode" style="color:#FF7660;">⚠️ FAILED RIGHT LENS BARCODE</label>
                <input type="text" id="txtFailedRightBarcode" class="input-control" value="${rightVal}" placeholder="Scan/Enter Right Lens Barcode">
            </div>
        `;
    } else if (category === 'BOTH LENS') {
        html = `
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 0;">
                <div class="form-group" style="margin-bottom: 0;">
                    <label for="txtFailedRightBarcode" style="color:#FF7660;">⚠️ RECEIVED RIGHT LENS BARCODE</label>
                    <input type="text" id="txtFailedRightBarcode" class="input-control" value="${rightVal}" placeholder="Scan Right Barcode">
                </div>
                <div class="form-group" style="margin-bottom: 0;">
                    <label for="txtFailedLeftBarcode" style="color:#FF7660;">⚠️ RECEIVED LEFT LENS BARCODE</label>
                    <input type="text" id="txtFailedLeftBarcode" class="input-control" value="${leftVal}" placeholder="Scan Left Barcode">
                </div>
            </div>
        `;
    } else if (category === 'ALL ITEMS') {
        html = `
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 0;">
                <div class="form-group" style="margin-bottom: 0;">
                    <label for="txtFailedFramePid" style="color:#FF7660;">⚠️ FRAME PID</label>
                    <input type="text" id="txtFailedFramePid" class="input-control" value="${frameVal}" placeholder="Frame PID">
                </div>
                <div class="form-group" style="margin-bottom: 0;">
                    <label for="txtFailedRightBarcode" style="color:#FF7660;">⚠️ RIGHT BARCODE</label>
                    <input type="text" id="txtFailedRightBarcode" class="input-control" value="${rightVal}" placeholder="Right Barcode">
                </div>
                <div class="form-group" style="margin-bottom: 0;">
                    <label for="txtFailedLeftBarcode" style="color:#FF7660;">⚠️ LEFT BARCODE</label>
                    <input type="text" id="txtFailedLeftBarcode" class="input-control" value="${leftVal}" placeholder="Left Barcode">
                </div>
            </div>
        `;
    }

    container.innerHTML = html;
}

function syncHeaderControls() {
    // Header controls sync automatically
}

// -----------------------------------------------------------------------------
// 4. BARCODE SCANNER & LIVE SQL LOOKUP (< 10ms)
// -----------------------------------------------------------------------------
function initScanner() {
    const scanInput = document.getElementById('txtScanTray');
    const form = document.getElementById('frmEscalation');
    let timer = null;

    // Pressing ENTER inside Scan input triggers SQL lookup + form submit if ready
    scanInput.addEventListener('keydown', async (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const trayId = scanInput.value.trim();
            if (!trayId) return;

            if (!currentLookupData || currentLookupData.tray_id !== trayId) {
                await triggerLookup(trayId);
            } else {
                submitEscalation(e);
            }
        }
    });

    scanInput.addEventListener('input', () => {
        const warningElem = document.getElementById('lblTrayWarning');
        if (warningElem) warningElem.style.display = 'none';
        scanInput.style.borderColor = '';
        scanInput.style.boxShadow = '';

        clearTimeout(timer);
        timer = setTimeout(() => {
            const val = scanInput.value.trim();
            if (val.length >= 7) {
                triggerLookup(val);
            }
        }, 60);
    });

    // Submitting form on ENTER key anywhere in the form
    form.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && e.target.tagName === 'INPUT') {
            e.preventDefault();
            submitEscalation(e);
        }
    });
}

let currentFetchingTray = null;

async function triggerLookup(trayId) {
    if (!trayId) return;
    if (currentFetchingTray === trayId) return;
    currentFetchingTray = trayId;

    const lblLatency = document.getElementById('lblQueryLatency');
    lblLatency.textContent = 'Fetching SQL...';
    lblLatency.className = 'badge-status badge-asrs';

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 12000);

    try {
        const res = await fetch(`/api/lookup/${encodeURIComponent(trayId)}`, { signal: controller.signal });
        clearTimeout(timeoutId);
        const data = await res.json();

        if (data.success) {
            currentLookupData = data;
            const setElemText = (id, val) => {
                const el = document.getElementById(id);
                if (el) el.textContent = val || '--';
            };

            setElemText('valFittingId', data.fitting_id);
            setElemText('valOrderId', data.order_id);
            
            const jitVal = data.is_jit || 'NO';
            const jitEl = document.getElementById('valIsJit');
            if (jitEl) {
                jitEl.textContent = jitVal;
                jitEl.style.color = (jitVal === 'AUTO' || jitVal === 'MANUAL') ? 'var(--green-accent)' : 'var(--text-muted)';
            }

            setElemText('valProcessingType', data.processing_type || '--');
            setElemText('valFramePid', data.frame_pid);
            setElemText('valFrameBarcode', data.frame_barcode);
            setElemText('valRightLensPid', data.right_lens_pid);
            setElemText('valRightLensBarcode', data.right_lens_barcode);
            setElemText('valLeftLensPid', data.left_lens_pid);
            setElemText('valLeftLensBarcode', data.left_lens_barcode);
            setElemText('valLensIndex', data.lens_index ? `${data.lens_index}${data.lens_name ? ' (' + data.lens_name + ')' : ''}` : '--');

            // Populate RIGHT LENS POWERS
            const r = data.right_lens || {};
            setElemText('valRightSph', r.sph);
            setElemText('valRightCyl', r.cyl);
            setElemText('valRightAxis', r.axis);
            setElemText('valRightAddn', r.addn);

            // Populate LEFT LENS POWERS
            const l = data.left_lens || {};
            setElemText('valLeftSph', l.sph);
            setElemText('valLeftCyl', l.cyl);
            setElemText('valLeftAxis', l.axis);
            setElemText('valLeftAddn', l.addn);

            if (data.cached) {
                lblLatency.textContent = '⚡ Cached (< 1ms)';
            } else {
                lblLatency.textContent = `🟢 SQL Fetched (${data.elapsed_ms || 15} ms)`;
            }
            lblLatency.className = 'badge-status badge-ok';

            // Refresh Dynamic Failed Barcode Prefill
            onFailCategoryChange();
        } else {
            const errText = data.error || 'Tray Not Found';
            if (errText.includes('password missing') || errText.includes('invalid or expired') || errText.includes('1045')) {
                lblLatency.textContent = '🔑 Password Needed';
                lblLatency.className = 'badge-status badge-ng';
                promptSetAdaptivePassword();
            } else if (errText.includes('not found')) {
                lblLatency.textContent = '❌ Tray Not Found';
                lblLatency.className = 'badge-status badge-ng';
            } else if (errText.includes('10061') || errText.includes('closed') || errText.includes('refused')) {
                lblLatency.textContent = '🔌 Terminal Tunnel Offline';
                lblLatency.className = 'badge-status badge-ng';
            } else {
                lblLatency.textContent = '❌ Connection Error';
                lblLatency.className = 'badge-status badge-ng';
            }
            clearDbCard();
        }
    } catch (err) {
        clearTimeout(timeoutId);
        if (err.name === 'AbortError') {
            lblLatency.textContent = '⏱️ Query Timeout';
        } else {
            lblLatency.textContent = '❌ Fetch Error';
        }
        lblLatency.className = 'badge-status badge-ng';
        clearDbCard();
    } finally {
        if (currentFetchingTray === trayId) {
            currentFetchingTray = null;
        }
    }
}

function clearDbCard() {
    currentLookupData = null;
    document.getElementById('valFittingId').textContent = '--';
    document.getElementById('valOrderId').textContent = '--';
    
    const jitEl = document.getElementById('valIsJit');
    if (jitEl) {
        jitEl.textContent = '--';
        jitEl.style.color = 'var(--text-muted)';
    }
    const processingEl = document.getElementById('valProcessingType');
    if (processingEl) {
        processingEl.textContent = '--';
    }

    document.getElementById('valFramePid').textContent = '--';
    document.getElementById('valRightLensPid').textContent = '--';
    document.getElementById('valRightLensBarcode').textContent = '--';
    document.getElementById('valLeftLensPid').textContent = '--';
    document.getElementById('valLeftLensBarcode').textContent = '--';
    document.getElementById('valLensIndex').textContent = '--';

    document.getElementById('valRightSph').textContent = '--';
    document.getElementById('valRightCyl').textContent = '--';
    document.getElementById('valRightAxis').textContent = '--';
    document.getElementById('valRightAddn').textContent = '--';

    document.getElementById('valLeftSph').textContent = '--';
    document.getElementById('valLeftCyl').textContent = '--';
    document.getElementById('valLeftAxis').textContent = '--';
    document.getElementById('valLeftAddn').textContent = '--';

    onFailCategoryChange();
}

// -----------------------------------------------------------------------------
// 5. ESCALATION FORM SUBMISSION
// -----------------------------------------------------------------------------
async function submitEscalation(e) {
    if (e) e.preventDefault();

    const scanElem = document.getElementById('txtScanTray');
    const warningElem = document.getElementById('lblTrayWarning');
    const trayId = scanElem ? scanElem.value.trim().toUpperCase() : '';

    if (!trayId) {
        if (warningElem) warningElem.style.display = 'block';
        if (scanElem) {
            scanElem.style.borderColor = '#FF4B2B';
            scanElem.style.boxShadow = '0 0 15px rgba(255, 75, 43, 0.5)';
            scanElem.focus();
        }
        return;
    } else {
        if (warningElem) warningElem.style.display = 'none';
        if (scanElem) {
            scanElem.style.borderColor = '';
            scanElem.style.boxShadow = '';
        }
    }

    // NOTE: Lookup already auto-fires when user types 7-char tray ID. Do NOT re-run here.

    const category = document.getElementById('selFailCategory')?.value || 'LEFT LENS';
    
    // Read Received Barcodes from dynamic inputs
    let rightBarcode = currentLookupData ? currentLookupData.right_lens_barcode : '';
    let leftBarcode = currentLookupData ? currentLookupData.left_lens_barcode : '';
    let framePid = currentLookupData ? currentLookupData.frame_pid : '';

    const elRight = document.getElementById('txtFailedRightBarcode');
    const elLeft = document.getElementById('txtFailedLeftBarcode');
    const elFrame = document.getElementById('txtFailedFramePid');

    if (elRight && elRight.value) rightBarcode = elRight.value.trim();
    if (elLeft && elLeft.value) leftBarcode = elLeft.value.trim();
    if (elFrame && elFrame.value) framePid = elFrame.value.trim();

    let selectedIssue = document.getElementById('selIssue')?.value || 'OTHER';
    if (selectedIssue === 'OTHER') {
        const customTxt = document.getElementById('txtOtherIssue')?.value?.trim();
        if (customTxt) {
            selectedIssue = `OTHER: ${customTxt}`;
        }
    }

    const payload = {
        tray_id: trayId,
        fitting_id: currentLookupData ? currentLookupData.fitting_id : '',
        order_id: currentLookupData ? currentLookupData.order_id : '',
        is_jit: currentLookupData ? currentLookupData.is_jit : 'NO',
        processing_type: currentLookupData ? currentLookupData.processing_type : '--',
        frame_pid: framePid,
        right_lens_barcode: rightBarcode,
        left_lens_barcode: leftBarcode,
        lens_index: currentLookupData ? currentLookupData.lens_index : '',
        sph: currentLookupData ? currentLookupData.sph : '',
        cyl: currentLookupData ? currentLookupData.cyl : '',
        axis: currentLookupData ? currentLookupData.axis : '',
        addn: currentLookupData ? currentLookupData.addn : '',
        shift: document.getElementById('selShift')?.value || 'Shift A',
        shift_ic: document.getElementById('selShiftIc')?.value || '',
        operator: document.getElementById('selOperator')?.value || '',
        fail_category: category,
        issue: selectedIssue,
        status: document.getElementById('selStatus')?.value || 'NG',
        machine: document.getElementById('txtMachine')?.value || ''
    };

    try {
        const res = await fetch('/api/escalations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (data.success) {
            document.getElementById('txtScanTray').value = '';
            const txtMachine = document.getElementById('txtMachine');
            if (txtMachine) txtMachine.value = '';
            const otherTxtInput = document.getElementById('txtOtherIssue');
            if (otherTxtInput) otherTxtInput.value = '';
            onIssueChange();
            clearDbCard();

            // Clear date and search filters so newly logged entry shows at top of table immediately
            const elStart1 = document.getElementById('dtFilterStart');
            const elEnd1 = document.getElementById('dtFilterEnd');
            const elSearch = document.getElementById('txtSearchTable');
            if (elStart1) elStart1.value = '';
            if (elEnd1) elEnd1.value = '';
            if (elSearch) elSearch.value = '';

            document.getElementById('txtScanTray').focus();
            await loadEscalations();
            await loadAnalytics();
        } else {
            alert(`❌ Error logging entry: ${data.error || 'Unknown error'}`);
        }
    } catch (err) {
        console.error('Submit Error:', err);
        alert(`❌ Network error logging entry: ${err.message}`);
    }
}

function onIssueChange() {
    const selVal = document.getElementById('selIssue')?.value;
    const container = document.getElementById('otherIssueContainer');
    if (container) {
        if (selVal === 'OTHER') {
            container.style.display = 'block';
            const txt = document.getElementById('txtOtherIssue');
            if (txt) txt.focus();
        } else {
            container.style.display = 'none';
        }
    }
}

// -----------------------------------------------------------------------------
// 6. LOAD ESCALATION TABLE RECORDS & DATE-TIME FILTERING
// -----------------------------------------------------------------------------
async function loadEscalations() {
    const start = document.getElementById('dtFilterStart')?.value || '';
    const end = document.getElementById('dtFilterEnd')?.value || '';
    const search = document.getElementById('txtSearchTable')?.value || '';

    const params = new URLSearchParams();
    if (start) params.append('start_time', start);
    if (end) params.append('end_time', end);
    if (search) params.append('search', search);

    try {
        const res = await fetch(`/api/escalations?${params.toString()}`, { cache: 'no-store' });
        const data = await res.json();

        if (data.success) {
            renderTable(data.data);
        }
    } catch (err) {
        console.error('Load Table Error:', err);
    }
}

function openPicker(id) {
    const el = document.getElementById(id);
    if (!el) return;
    try {
        if (typeof el.showPicker === 'function') {
            el.showPicker();
        } else {
            el.focus();
            el.click();
        }
    } catch (err) {
        try {
            el.focus();
            el.click();
        } catch (e) {}
    }
}

function applyDateTimeFilter() {
    loadEscalations();
}

function resetDateTimeFilter() {
    const startEl = document.getElementById('dtFilterStart');
    const endEl = document.getElementById('dtFilterEnd');
    const searchEl = document.getElementById('txtSearchTable');
    if (startEl) startEl.value = '';
    if (endEl) endEl.value = '';
    if (searchEl) searchEl.value = '';
    loadEscalations();
}

async function checkImportMeta() {
    try {
        const res = await fetch('/api/import_meta', { cache: 'no-store' });
        const data = await res.json();
        const banner2 = document.getElementById('bannerAnalyticsImportInfo');
        if (data.success && data.meta) {
            if (banner2) {
                banner2.style.display = 'flex';
                document.getElementById('lblAnalyticsImportFilename').textContent = `Imported File: ${data.meta.filename}`;
                document.getElementById('lblAnalyticsImportDetails').textContent = `Uploaded: ${data.meta.imported_at} | ${data.meta.imported_count} records imported (${data.meta.total_count} total merged in system)`;
            }

            // Auto-populate Date & Time inputs for Analytics Tab
            if (data.meta.min_date && data.meta.max_date) {
                const elStart2 = document.getElementById('analyticsStart');
                const elEnd2 = document.getElementById('analyticsEnd');
                if (elStart2 && !elStart2.value) elStart2.value = data.meta.min_date;
                if (elEnd2 && !elEnd2.value) elEnd2.value = data.meta.max_date;
            }
        } else {
            if (banner2) banner2.style.display = 'none';
        }
    } catch (err) {
        console.error('Import Meta Error:', err);
    }
}

function resetAnalyticsDateFilter() {
    const elStart = document.getElementById('analyticsStart');
    const elEnd = document.getElementById('analyticsEnd');
    if (elStart) elStart.value = '';
    if (elEnd) elEnd.value = '';
    loadAnalytics();
}

async function clearImportedData() {
    try {
        const banner2 = document.getElementById('bannerAnalyticsImportInfo');
        if (banner2) banner2.style.display = 'none';

        const res = await fetch('/api/import_meta', { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            const elStart1 = document.getElementById('dtFilterStart');
            const elEnd1 = document.getElementById('dtFilterEnd');
            const elStart2 = document.getElementById('analyticsStart');
            const elEnd2 = document.getElementById('analyticsEnd');
            if (elStart1) elStart1.value = '';
            if (elEnd1) elEnd1.value = '';
            if (elStart2) elStart2.value = '';
            if (elEnd2) elEnd2.value = '';
            await checkImportMeta();
            await loadEscalations();
            await loadAnalytics();
        }
    } catch (err) {
        console.error('Error clearing imported data:', err);
    }
}

async function uploadImportExcel(inputElem) {
    if (!inputElem || !inputElem.files || inputElem.files.length === 0) return;
    const file = inputElem.files[0];
    const formData = new FormData();
    formData.append('file', file);

    const btn1 = document.getElementById('btnImportBtn1');
    const btn2 = document.getElementById('btnImportBtn2');

    if (btn1) { btn1.innerHTML = '⏳ Importing & Analyzing...'; btn1.disabled = true; }
    if (btn2) { btn2.innerHTML = '⏳ Importing & Analyzing...'; btn2.disabled = true; }

    try {
        const res = await fetch('/api/import_escalations', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            // Auto-fill date range pickers ONLY for Analytics Tab
            if (data.min_date && data.max_date) {
                const elStart2 = document.getElementById('analyticsStart');
                const elEnd2 = document.getElementById('analyticsEnd');
                if (elStart2) elStart2.value = data.min_date;
                if (elEnd2) elEnd2.value = data.max_date;
            }

            checkImportMeta();
            loadEscalations();
            loadAnalytics();
        } else {
            console.error('Import error:', data.error);
        }
    } catch (err) {
        console.error('Network error importing file:', err);
    } finally {
        if (btn1) { btn1.innerHTML = '📂 IMPORT EXCEL FOR ANALYTICS'; btn1.disabled = false; }
        if (btn2) { btn2.innerHTML = '📂 IMPORT EXCEL FOR ANALYTICS'; btn2.disabled = false; }
        inputElem.value = '';
    }
}

function triggerExport(format) {
    const start = document.getElementById('dtFilterStart')?.value || '';
    const end = document.getElementById('dtFilterEnd')?.value || '';
    const search = document.getElementById('txtSearchTable')?.value || '';

    const params = new URLSearchParams();
    if (start) params.append('start_time', start);
    if (end) params.append('end_time', end);
    if (search) params.append('search', search);

    window.location.href = `/api/export/${format}?${params.toString()}`;
}

function renderTable(records) {
    const tbody = document.getElementById('tblEscalationsBody');
    tbody.innerHTML = '';

    if (!records || records.length === 0) {
        tbody.innerHTML = '<tr><td colspan="11" style="text-align:center; color: var(--text-muted);">No escalation records found.</td></tr>';
        return;
    }

    // Limit table rendering to top 500 records using DocumentFragment for < 5ms render speed
    const displayRecords = records.slice(0, 500);
    const fragment = document.createDocumentFragment();

    displayRecords.forEach(r => {
        const tr = document.createElement('tr');
        
        let statusBadge = '<span class="badge-status badge-ng">NG</span>';
        const st = (r.status || '').toString().toUpperCase();
        if (st === 'OK') statusBadge = '<span class="badge-status badge-ok">OK</span>';
        else if (st.includes('LAB')) statusBadge = '<span class="badge-status badge-ok" style="background: rgba(59, 130, 246, 0.2); color: #60A5FA; border-color: rgba(59, 130, 246, 0.4);">LAB</span>';
        else if (st.includes('NON JIT')) statusBadge = '<span class="badge-status badge-ok" style="background: rgba(20, 184, 166, 0.2); color: #2DD4BF; border-color: rgba(20, 184, 166, 0.4);">NON-JIT ASRS</span>';
        else if (st.includes('JIT ASRS')) statusBadge = '<span class="badge-status badge-asrs">JIT ASRS</span>';
        else if (st.includes('STOCKING')) statusBadge = '<span class="badge-status badge-ok" style="background: rgba(56, 189, 248, 0.2); color: #38BDF8; border-color: rgba(56, 189, 248, 0.4);">STOCKING</span>';

        const jitVal = (r.is_jit || 'NO').toString().trim().toUpperCase();
        let jitBadge;
        if (jitVal === 'AUTO' || jitVal === 'YES' || jitVal === 'JIT') {
            jitBadge = `<span class="badge-status badge-ok" style="padding: 2px 6px; font-size: 0.75rem;">AUTO</span>`;
        } else if (jitVal === 'MANUAL') {
            jitBadge = `<span class="badge-status badge-ok" style="padding: 2px 6px; font-size: 0.75rem; background: rgba(168,85,247,0.2); color: #a855f7; border-color: rgba(168,85,247,0.4);">MANUAL</span>`;
        } else if (jitVal === 'NON JIT' || jitVal === 'NON-JIT' || jitVal === 'NO') {
            jitBadge = `<span style="color: var(--text-muted);">NO</span>`;
        } else {
            jitBadge = `<span style="color: var(--text-muted);">${jitVal}</span>`;
        }

        tr.innerHTML = `
            <td>${r.entry_date} ${r.entry_time}</td>
            <td><strong>${r.shift}</strong></td>
            <td>${r.operator}</td>
            <td><strong style="color: var(--cyan-accent);">${r.tray_id}</strong></td>
            <td>${r.fitting_id || '--'}</td>
            <td>${jitBadge}</td>
            <td><strong style="color: var(--amber-accent);">${r.processing_type || '--'}</strong></td>
            <td>${r.lens_index || '--'}</td>
            <td>${r.fail_category}</td>
            <td>${r.issue}</td>
            <td>${statusBadge}</td>
        `;
        fragment.appendChild(tr);
    });

    tbody.appendChild(fragment);
}

function filterTable() {
    loadEscalations();
}

let rawShiftOperatorsData = {};
let allOperatorsData = [];

// Chart State Cache (Bar View default for all charts)
const analyticsChartState = {
    issues: { mode: 'bar', data: [], instance: null, canvasId: 'chartTopIssuesCombined', keyField: 'issue' },
    operators: { mode: 'bar', data: [], instance: null, canvasId: 'chartOperatorsCombined', keyField: 'operator' },
    pids: { mode: 'bar', data: [], instance: null, canvasId: 'chartPidsCombined', keyField: 'pid' },
    shifts: { mode: 'bar', data: [], instance: null, canvasId: 'chartShiftsCombined', keyField: 'shift' }
};

async function loadAnalytics() {
    try {
        const elStart = document.getElementById('analyticsStart');
        const elEnd = document.getElementById('analyticsEnd');
        const start = elStart?.value || '';
        const end = elEnd?.value || '';

        const params = new URLSearchParams();
        if (start) params.append('start_time', start);
        if (end) params.append('end_time', end);

        const res = await fetch(`/api/analytics?${params.toString()}`, { cache: 'no-store' });
        const data = await res.json();

        if (!data.success) return;

        // Auto-fill Analytics Date & Time range controls with min_date and max_date if inputs are blank
        if (data.min_date && data.max_date) {
            if (elStart && !elStart.value) elStart.value = data.min_date;
            if (elEnd && !elEnd.value) elEnd.value = data.max_date;
        }

        // Update Scorecards
        document.getElementById('kpiTotal').textContent = data.summary.total;
        document.getElementById('kpiNgRate').textContent = `${data.summary.ng_rate}%`;

        // Dynamically update total escalations title based on date range (Multi-day vs Single day)
        const lblTotalTitle = document.getElementById('lblKpiTotalTitle');
        if (lblTotalTitle) {
            const curStart = elStart?.value || data.min_date || '';
            const curEnd = elEnd?.value || data.max_date || '';
            const startDate = curStart.split('T')[0];
            const endDate = curEnd.split('T')[0];
            if (startDate && endDate && startDate !== endDate) {
                lblTotalTitle.textContent = 'Total Escalations';
            } else {
                lblTotalTitle.textContent = 'Total Escalations Today';
            }
        }
        
        const topIssue = data.top_issues.length > 0 ? data.top_issues[0].issue : '--';
        document.getElementById('kpiTopDefect').textContent = topIssue;
        document.getElementById('kpiShiftVolume').textContent = data.summary.active_shift_volume ?? data.summary.total;
        
        const lblActiveShift = document.getElementById('lblActiveShiftName');
        if (lblActiveShift && data.summary.active_shift) {
            lblActiveShift.textContent = `(${data.summary.active_shift})`;
        }

        // Cache Shift-Wise Operator Data
        rawShiftOperatorsData = data.shift_operators || {};
        allOperatorsData = data.top_operators || [];
        rawHourlyData = data.hourly_data || { all: [], shifts: {}, operators: {} };

        // Apply Shift Filter for Operator Card if selected
        const selShift = document.getElementById('selOperatorShiftFilter')?.value || 'ALL';
        let opData = allOperatorsData;
        if (selShift !== 'ALL' && rawShiftOperatorsData[selShift]) {
            opData = rawShiftOperatorsData[selShift];
        }

        // Render Top 7 Defect Causes Chart
        renderGenericChart('issues', data.top_issues, 'issue');

        // Render Operator Failure Volume Chart
        renderGenericChart('operators', opData, 'operator');

        // Render Maximum Failed PIDs Chart (using .all for the new dictionary structure)
        renderGenericChart('pids', data.top_pids.all || [], 'pid');

        // Render Shift-Wise Failures Chart
        renderGenericChart('shifts', data.shift_counts, 'shift');

        // Render Hourly Trend Chart
        populateHourlyOperators();
        updateHourlyChart();

    } catch (err) {
        console.error('Analytics Error:', err);
    }
}

function filterOperatorShift(selectedShift) {
    let filteredData = allOperatorsData;
    if (selectedShift !== 'ALL' && rawShiftOperatorsData[selectedShift]) {
        filteredData = rawShiftOperatorsData[selectedShift];
    }
    renderGenericChart('operators', filteredData, 'operator');
}

function populateHourlyOperators() {
    const sel = document.getElementById('selHourlyOperator');
    if (!sel || !rawHourlyData) return;
    const currentVal = sel.value;
    sel.innerHTML = '<option value="ALL">All Operators</option>';
    const ops = Object.keys(rawHourlyData.operators || {}).sort();
    ops.forEach(op => {
        const opt = document.createElement('option');
        opt.value = op;
        opt.textContent = op;
        sel.appendChild(opt);
    });
    if (ops.includes(currentVal)) sel.value = currentVal;
}

function updateHourlyChart() {
    const ctx = document.getElementById('chartHourlyTrend')?.getContext('2d');
    if (!ctx || !rawHourlyData) return;

    const selShift = document.getElementById('selHourlyShift')?.value || 'ALL';
    const selOp = document.getElementById('selHourlyOperator')?.value || 'ALL';

    let dataArray = [];
    if (selOp !== 'ALL' && rawHourlyData.operators[selOp]) {
        dataArray = rawHourlyData.operators[selOp];
    } else if (selShift !== 'ALL' && rawHourlyData.shifts[selShift]) {
        dataArray = rawHourlyData.shifts[selShift];
    } else {
        dataArray = rawHourlyData.all || [];
    }

    const labels = Array.from({length: 24}, (_, i) => `${i.toString().padStart(2, '0')}:00`);

    const lblSub = document.getElementById('lblHourlySubtitle');
    if (lblSub) {
        lblSub.textContent = ``;
    }

    if (chartHourlyTrend) chartHourlyTrend.destroy();

    const isLight = document.body.classList.contains('light-theme');
    const colorLine = isLight ? '#0284C7' : '#00f2fe';
    
    // Create gradient fill
    const gradient = ctx.createLinearGradient(0, 0, 0, 320);
    gradient.addColorStop(0, isLight ? 'rgba(2, 132, 199, 0.4)' : 'rgba(0, 242, 254, 0.4)');
    gradient.addColorStop(1, isLight ? 'rgba(2, 132, 199, 0.0)' : 'rgba(0, 242, 254, 0.0)');

    const colorText = isLight ? '#64748B' : '#94A3B8';
    const colorGrid = isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)';

    // Custom plugin for line glow
    const shadowPlugin = {
        id: 'lineShadow',
        beforeDatasetDraw: (chart, args) => {
            const c_ctx = chart.ctx;
            c_ctx.save();
            c_ctx.shadowColor = colorLine;
            c_ctx.shadowBlur = 10;
            c_ctx.shadowOffsetX = 0;
            c_ctx.shadowOffsetY = 0;
        },
        afterDatasetDraw: (chart) => {
            chart.ctx.restore();
        }
    };

    chartHourlyTrend = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Failures',
                data: dataArray,
                borderColor: colorLine,
                backgroundColor: gradient,
                borderWidth: 2,
                pointBackgroundColor: isLight ? '#FFF' : '#0B0F19',
                pointBorderColor: colorLine,
                pointBorderWidth: 2,
                pointRadius: 3,
                pointHoverRadius: 5,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, grid: { color: colorGrid, drawBorder: false }, ticks: { color: colorText, stepSize: 2 } },
                x: { grid: { display: false }, ticks: { color: colorText, maxRotation: 45, minRotation: 45, font: { size: 10 } } }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: isLight ? 'rgba(255,255,255,0.95)' : 'rgba(15,23,42,0.95)',
                    titleColor: colorLine,
                    bodyColor: isLight ? '#0F172A' : '#FFF',
                    borderColor: isLight ? '#E2E8F0' : 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    padding: 10,
                    displayColors: false,
                    callbacks: {
                        label: function(context) {
                            const val = context.parsed.y;
                            if (val === 0) return 'Failures: 0';
                            
                            const totalDay = context.dataset.data.reduce((a, b) => a + b, 0);
                            const perc = totalDay > 0 ? ((val / totalDay) * 100).toFixed(1) : 0;
                            
                            let lines = [`Failures: ${val} (${perc}% of total)`];
                            
                            const selOp = document.getElementById('selHourlyOperator')?.value || 'ALL';
                            if (selOp === 'ALL' && rawHourlyData && rawHourlyData.operators) {
                                lines.push('');
                                lines.push('Operator Breakdown:');
                                
                                let opStats = [];
                                for (const op in rawHourlyData.operators) {
                                    const opCount = rawHourlyData.operators[op][context.dataIndex];
                                    if (opCount > 0) {
                                        opStats.push({ name: op, count: opCount });
                                    }
                                }
                                
                                opStats.sort((a, b) => b.count - a.count);
                                
                                const topOps = opStats.slice(0, 3);
                                topOps.forEach(op => {
                                    lines.push(`  • ${op.name}: ${op.count}`);
                                });
                                
                                if (opStats.length > 3) {
                                    const othersCount = opStats.slice(3).reduce((sum, op) => sum + op.count, 0);
                                    lines.push(`  • OTHERS: ${othersCount}`);
                                }
                            }
                            return lines;
                        }
                    }
                }
            }
        },
        plugins: [shadowPlugin]
    });
}

function renderGenericChart(chartKey, rawData, keyField) {
    const config = analyticsChartState[chartKey];
    if (!config) return;

    if (rawData) config.data = rawData;
    if (keyField) config.keyField = keyField;

    const ctx = document.getElementById(config.canvasId)?.getContext('2d');
    if (!ctx) return;

    if (config.instance) config.instance.destroy();

    const labels = config.data.map(i => i[config.keyField] || 'UNASSIGNED');
    const counts = config.data.map(i => i.count || 0);
    const colors = [
        '#FF4B2B', '#00F2FE', '#FFB703', '#38EF7D',
        '#A855F7', '#EC4899', '#3B82F6'
    ];

    if (config.mode === 'doughnut') {
        config.instance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: counts,
                    backgroundColor: colors.slice(0, counts.length),
                    borderWidth: 1.5,
                    borderColor: '#1E293B'
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { position: 'bottom', labels: { color: '#94A3B8', boxWidth: 12 } },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const idx = context.dataIndex;
                                const label = context.label || '';
                                const val = context.parsed || 0;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const pct = total > 0 ? ((val / total) * 100).toFixed(1) + '%' : '0%';
                                let extra = '';
                                if (chartKey === 'pids' && config.data[idx] && config.data[idx].top_cause) {
                                    extra = ` | Cause: ${config.data[idx].top_cause}`;
                                }
                                return `${label}: ${val} (${pct})${extra}`;
                            }
                        }
                    }
                }
            }
        });
    } else {
        config.instance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Failures',
                    data: counts,
                    backgroundColor: colors.slice(0, counts.length),
                    borderRadius: 6
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const idx = context.dataIndex;
                                const val = context.parsed.x || 0;
                                const total = counts.reduce((a, b) => a + b, 0);
                                const pct = total > 0 ? ((val / total) * 100).toFixed(1) + '%' : '0%';
                                let extra = '';
                                if (chartKey === 'pids' && config.data[idx] && config.data[idx].top_cause) {
                                    extra = ` | Cause: ${config.data[idx].top_cause}`;
                                }
                                return `Failures: ${val} (${pct})${extra}`;
                            }
                        }
                    }
                },
                scales: {
                    x: { ticks: { color: '#94A3B8' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                    y: { ticks: { color: '#94A3B8' }, grid: { display: false } }
                }
            }
        });
    }
}

function switchChartType(chartKey, mode) {
    const config = analyticsChartState[chartKey];
    if (!config) return;

    config.mode = mode;

    let prefix = 'Issues';
    if (chartKey === 'operators') prefix = 'Op';
    if (chartKey === 'pids') prefix = 'Pid';
    if (chartKey === 'shifts') prefix = 'Shift';

    const btnDonut = document.getElementById(`btnToggle${prefix}Donut`);
    const btnBar = document.getElementById(`btnToggle${prefix}Bar`);
    if (btnDonut) btnDonut.classList.toggle('active', mode === 'doughnut');
    if (btnBar) btnBar.classList.toggle('active', mode === 'bar');

    renderGenericChart(chartKey);
}

function renderDonutChart(categories) {
    const ctx = document.getElementById('chartFailureScope').getContext('2d');
    
    if (chartDonut) chartDonut.destroy();

    chartDonut = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: Object.keys(categories),
            datasets: [{
                data: Object.values(categories),
                backgroundColor: ['#FF4B2B', '#00F2FE', '#FFB703', '#38EF7D'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'bottom', labels: { color: '#94A3B8' } }
            }
        }
    });
}

function renderBarChart(topIssues) {
    const ctx = document.getElementById('chartTopIssues').getContext('2d');
    
    if (chartBar) chartBar.destroy();

    const labels = topIssues.map(i => i.issue);
    const counts = topIssues.map(i => i.count);

    chartBar = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Defect Count',
                data: counts,
                backgroundColor: 'rgba(0, 242, 254, 0.7)',
                borderColor: '#00F2FE',
                borderWidth: 1,
                borderRadius: 6
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: { ticks: { color: '#94A3B8' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                y: { ticks: { color: '#94A3B8' }, grid: { display: false } }
            }
        }
    });
}

// -----------------------------------------------------------------------------
// 8. ADAPTIVE TERMINAL PASSWORD VERIFICATION & SYNC
// -----------------------------------------------------------------------------
function promptSetAdaptivePassword() {
    const modal = document.getElementById('modalPassword');
    const txt = document.getElementById('txtAdaptivePassword');
    const msg = document.getElementById('pwdStatusMsg');
    if (!modal || !txt) return;

    txt.value = '';
    if (msg) {
        msg.textContent = '';
        msg.style.color = 'var(--text-muted)';
    }
    modal.classList.add('active');
    setTimeout(() => txt.focus(), 100);
}

function closePasswordModal() {
    const modal = document.getElementById('modalPassword');
    if (modal) modal.classList.remove('active');
}

async function submitAdaptivePassword() {
    const txt = document.getElementById('txtAdaptivePassword');
    const msg = document.getElementById('pwdStatusMsg');
    const pwd = txt ? txt.value.trim() : '';

    if (!pwd) {
        if (msg) {
            msg.textContent = '⚠️ Please enter a password.';
            msg.style.color = 'var(--amber-accent)';
        }
        return;
    }

    if (msg) {
        msg.textContent = '⏳ Testing password against port 13306...';
        msg.style.color = 'var(--cyan-accent)';
    }

    try {
        const res = await fetch('/api/config/password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: pwd })
        });
        const data = await res.json();

        if (data.success) {
            if (msg) {
                msg.textContent = '✅ Connected! Password verified successfully.';
                msg.style.color = 'var(--green-accent)';
            }
            const badge = document.getElementById('lblDbStatus');
            if (badge) {
                badge.textContent = '🟢 MySQL Connected';
                badge.className = 'stat-pill badge-online';
            }
            setTimeout(() => {
                closePasswordModal();
                const scanInput = document.getElementById('txtScanTray');
                if (scanInput) {
                    scanInput.value = scanInput.value.toUpperCase();
                }
                if (scanInput && scanInput.value.trim()) {
                    triggerLookup(scanInput.value.trim());
                }
            }, 800);
        } else {
            if (msg) {
                msg.textContent = data.error || '❌ Incorrect Password! Check your terminal output and try again.';
                msg.style.color = 'var(--red-accent)';
            }
            txt.focus();
            txt.select();
        }
    } catch (err) {
        if (msg) {
            msg.textContent = '❌ Failed to reach server. Ensure app.py is running.';
            msg.style.color = 'var(--red-accent)';
        }
    }
}
