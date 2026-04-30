let dcIntentHorizon = window.APP_CONFIG.intentHorizon;
let dcResilStatus = window.APP_CONFIG.resilStatus;
let dcOffRoutine = false;

function dcSetOffRoutine(isOff) {
    dcOffRoutine = isOff;
    renderDcColors();
}

function renderDcColors() {
    const routineContainer = document.getElementById('dcRoutineColors');
    if (routineContainer) {
        const statuses = [
            { isOff: true, color: '#ffebee', border: '#d32f2f', label: 'Off' },
            { isOff: false, color: '#e8f5e9', border: '#2e7d32', label: 'On' }
        ];
        routineContainer.innerHTML = statuses.map(s => {
            const isActive = dcOffRoutine === s.isOff;
            const style = `background: ${s.color}; border: ${isActive ? '1.5px solid #1a1a1a' : '1px solid ' + s.border}; 
                           width: 24px; height: 24px; cursor: pointer; border-radius: 4px; transition: transform 0.1s;
                           ${isActive ? 'transform: scale(1.15);' : 'opacity: 0.5;'}`;
            return `<button type="button" onclick="dcSetOffRoutine(${s.isOff})" style="${style}" title="${s.label} Routine"></button>`;
        }).join('');
    }

    const intentContainer = document.getElementById('dcIntentColors');
    if (intentContainer) {
        intentContainer.innerHTML = CAL_HORIZONS.slice(0, 4).map(h => {
            const isActive = dcIntentHorizon === h.id;
            const style = `background: ${h.color}; border: ${isActive ? '1.5px solid #1a1a1a' : '1px solid #ddd'}; 
                           width: 20px; height: 20px; cursor: pointer; border-radius: 4px; ${isActive ? 'transform: scale(1.1);' : 'opacity: 0.6;'}`;
            return `<button type="button" class="cal-h-btn" style="${style}" onclick="dcSetIntent('${h.id}')"></button>`;
        }).join('');
    }

    const resilContainer = document.getElementById('dcResilColors');
    if (resilContainer) {
        resilContainer.innerHTML = RESILIENCE_STATUSES.map(s => {
            const isActive = dcResilStatus === s.id;
            const style = `background: ${s.color}; border: ${isActive ? '1.5px solid #1a1a1a' : '1px solid #ddd'}; 
                           width: 20px; height: 20px; cursor: pointer; border-radius: 4px; ${isActive ? 'transform: scale(1.1);' : 'opacity: 0.6;'}`;
            return `<button type="button" class="cal-h-btn" style="${style}" onclick="dcSetResil('${s.id}')"></button>`;
        }).join('');
    }
}

function dcSetIntent(id) { dcIntentHorizon = id; renderDcColors(); }
function dcSetResil(id) { dcResilStatus = id; renderDcColors(); }

const IS_AUTH = window.APP_CONFIG.isAuth;

function toggleMobileMenu() {
    document.getElementById('actionButtons').classList.toggle('show');
}

function hideMobileMenu() {
    const menu = document.getElementById('actionButtons');
    if (menu) menu.classList.remove('show');
}

document.addEventListener('click', function (event) {
    const menu = document.getElementById('actionButtons');
    const btn = document.querySelector('.mobile-menu-btn');
    if (menu && menu.classList.contains('show') && !menu.contains(event.target) && !btn.contains(event.target)) {
        menu.classList.remove('show');
    }
});

function submitAuth() {
    const pwd = document.getElementById('authPassword').value;
    fetch('/api/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: pwd })
    }).then(r => r.json()).then(d => {
        if (d.success) location.reload();
        else document.getElementById('loginError').style.display = 'block';
    });
}

async function loadAggregateData() {
    const year = new Date().getFullYear();
    try {
        const response = await fetch(`/api/aggregate/${year}`);
        const json = await response.json();
        if (json.success) {
            renderAggregateView(json.data, year);
            window.aggregateDataLoaded = true;
        }
    } catch (e) {
        console.error("Loading aggregate data error", e);
    }
}

function setupTooltips() {
    let tooltip = document.getElementById('global-tooltip');
    if (!tooltip) {
        tooltip = document.createElement('div');
        tooltip.id = 'global-tooltip';
        tooltip.className = 'global-tooltip';
        document.body.appendChild(tooltip);
    }

    document.addEventListener('mouseover', function (e) {
        if (e.target.classList.contains('heat-cell') && !e.target.classList.contains('heat-out')) {
            const info = e.target.getAttribute('data-info');
            if (info) {
                tooltip.innerText = info;
                const rect = e.target.getBoundingClientRect();

                tooltip.style.left = rect.left + (rect.width / 2) + 'px';
                tooltip.style.top = rect.top + 'px';

                tooltip.classList.add('visible');
            }
        }
    });

    document.addEventListener('mouseout', function (e) {
        if (e.target.classList.contains('heat-cell')) {
            tooltip.classList.remove('visible');
        }
    });

    window.addEventListener('scroll', () => tooltip.classList.remove('visible'), true);
}

document.addEventListener('DOMContentLoaded', setupTooltips);

function renderAggregateView(data, year) {
    const container = document.getElementById('aggregateContainer');
    container.innerHTML = '';

    const cats = ['WORK', 'QUESTS', 'SELF CARE', 'INTENTIONALITY'];

    const startDate = new Date(year, 0, 1);

    const dayOfWeek = startDate.getDay();
    const offset = (dayOfWeek === 0) ? 6 : dayOfWeek - 1;
    startDate.setDate(startDate.getDate() - offset);

    const dates = [];
    for (let i = 0; i < 53 * 7; i++) {
        const d = new Date(startDate);
        d.setDate(d.getDate() + i);
        if (d.getFullYear() > year && i > 365 && d.getDay() === 1) break;
        dates.push(d);
    }

    const CAL_HORIZONS_AGG = [
        { id: "survival", label: "Survival", color: "#888" },
        { id: "2wk", label: "2 wk", color: "#7dd3fc" },
        { id: "1yr", label: "1 yr", color: "#3b82f6" },
        { id: "5yr", label: "5 yr", color: "#d946ef" },
        { id: "10yr", label: "10+ yr", color: "#f59e0b" }
    ];

    cats.forEach(catName => {
        const isIntent = catName === 'INTENTIONALITY';
        const catKey = catName.toLowerCase();
        const catData = data[catKey] || {};

        let maxHits = 0;
        if (!isIntent) {
            Object.values(catData).forEach(v => { if (v > maxHits) maxHits = v; });
        }

        const wrapper = document.createElement('div');
        wrapper.className = 'heat-container';
        wrapper.innerHTML = `<div class="heat-title">${catName}</div>`;

        const gridWrap = document.createElement('div');
        gridWrap.className = 'heat-wrapper';

        gridWrap.innerHTML += `<div class="heat-dow">
            <div>Mon</div><div>Tue</div><div>Wed</div><div>Thu</div><div>Fri</div><div>Sat</div><div>Sun</div>
        </div>`;

        const grid = document.createElement('div');
        grid.className = 'heat-grid';

        const monthLabels = [];
        const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

        dates.forEach((d, index) => {
            if (d.getDate() === 1 && d.getFullYear() === year) {
                const colIndex = Math.floor(index / 7);
                monthLabels.push({ name: monthNames[d.getMonth()], col: colIndex });
            }

            const dateStr = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
            let isOut = d.getFullYear() !== year;

            const cell = document.createElement('div');
            cell.className = `heat-cell ${isOut ? 'heat-out' : ''}`;

            if (!isOut) {
                const niceDate = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

                if (isIntent) {
                    const dayData = catData[dateStr];
                    if (dayData) {
                        if (dayData.plan) {
                            cell.style.background = '#fafafa';
                            cell.style.border = '1px dashed #999';
                            cell.setAttribute('data-info', `Plan on ${niceDate}`);
                        } else {
                            const hObj = CAL_HORIZONS_AGG.find(h => h.id === dayData.horizon);
                            if (hObj) {
                                cell.style.background = hObj.color;
                                cell.setAttribute('data-info', `${hObj.label} on ${niceDate}`);
                            }
                        }
                    } else {
                        cell.classList.add('heat-0');
                    }
                }
                else {
                    const hits = catData[dateStr] || 0;
                    let level = 0;
                    if (hits > 0) {
                        if (maxHits <= 4) level = hits;
                        else level = Math.ceil((hits / maxHits) * 4);
                        if (level > 4) level = 4;
                    }
                    cell.classList.add(`heat-${level}`);

                    const taskWord = hits === 1 ? 'task' : 'tasks';
                    cell.setAttribute('data-info', `${hits} ${taskWord} on ${niceDate}`);
                }
            }
            grid.appendChild(cell);
        });

        const monthsDiv = document.createElement('div');
        monthsDiv.className = 'heat-months';
        monthLabels.forEach(ml => {
            const span = document.createElement('span');
            span.className = 'heat-month-label';
            span.innerText = ml.name;
            span.style.left = `${ml.col * 16}px`;
            monthsDiv.appendChild(span);
        });

        const mainRight = document.createElement('div');
        mainRight.appendChild(monthsDiv);
        mainRight.appendChild(grid);

        gridWrap.appendChild(mainRight);
        wrapper.appendChild(gridWrap);
        container.appendChild(wrapper);
    });
}

function setSortMode(mode) {
    if ((mode === 'calendar' || mode === 'aggregate') && !IS_AUTH) {
        showModalWindow('loginModal');
        return;
    }

    localStorage.setItem('habitSortMode', mode);

    document.querySelectorAll('.sort-tgl').forEach(b => {
        b.classList.toggle('active', b.dataset.mode === mode);
    });

    const isMobile = window.innerWidth <= 768;

    document.querySelectorAll('.grid-wrapper').forEach(w => {
        w.style.setProperty('display', 'none', 'important');
    });

    if (mode === 'calendar') {
        const calView = document.getElementById('calendarView');
        if (calView) {
            calView.style.display = 'block';
            if (!window.calDataLoaded) { loadCalData(); window.calDataLoaded = true; }
        }
    } else if (mode === 'aggregate') {
        const aggView = document.getElementById('aggregateView');
        if (aggView) {
            aggView.style.display = 'block';
            if (!window.aggregateDataLoaded) { loadAggregateData(); }
        }
    } else {
        document.querySelectorAll('.grid-wrapper').forEach(w => {
            if (w.id === 'calendarView' || w.id === 'aggregateView') return;
            w.style.display = (isMobile && w.classList.contains('mobile-only')) || (!isMobile && w.classList.contains('desktop-only')) ? 'block' : 'none';
        });

        const typeHeaders = document.querySelectorAll('.type-header');
        const labels = document.querySelectorAll('.habit-label');
        const cells = document.querySelectorAll('.habit-cell');

        const typeMap = { 'work': 10000, 'scaffolding': 20000, 'family': 30000, 'quests': 35000, 'self care': 40000 };

        typeHeaders.forEach(h => { h.style.display = 'flex'; h.style.order = typeMap[h.dataset.cat] || 90000; });
        labels.forEach(l => { l.style.order = (typeMap[l.dataset.cat] || 90000) + parseInt(l.dataset.idx); });
        cells.forEach(c => { c.style.order = (typeMap[c.dataset.cat] || 90000) + parseInt(c.dataset.idx); });
    }
}

function toggleEditMode() {
    document.body.classList.toggle('edit-mode');
    const isOn = document.body.classList.contains('edit-mode');

    localStorage.setItem('habitEditMode', isOn);

    document.querySelectorAll('.edit-toggle-btn').forEach(btn => {
        btn.classList.toggle('on', isOn);
    });
}

function logoutAuth() {
    fetch('/api/logout', { method: 'POST' }).then(() => location.reload());
}
function showModalWindow(id) { document.getElementById(id).classList.add('active'); }
function hideModalWindow(id) { document.getElementById(id).classList.remove('active'); }

function deleteThread(id, name) {
    if (confirm("Archive: " + name + "?")) {
        fetch('/api/delete_thread', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: id }) }).then(() => location.reload());
    }
}
function moveThread(id, direction) {
    fetch('/api/move_thread', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: id, direction: direction })
    }).then(() => location.reload());
}

let currentCat = '';

function submitNewThread() {
    const mode = document.getElementById('newThreadCadenceMode').value;
    const parentId = document.getElementById('newThreadParent').value;
    let cadenceValue = 'daily';

    if (mode === 'specific') {
        const checked = document.querySelectorAll('#newThreadDays input:checked');
        if (checked.length > 0) {
            cadenceValue = Array.from(checked).map(cb => cb.value).join(',');
        } else {
            alert("Please select days."); return;
        }
    }

    const payload = {
        name: document.getElementById('newThreadName').value,
        category: currentCat,
        redacted: document.getElementById('newThreadRedacted').value,
        sub_category: document.getElementById('newThreadSubCat').value,
        type: document.getElementById('newThreadType').value,
        cadence: cadenceValue,
        parent_id: parentId ? parseInt(parentId) : null,
        time_of_day: 'unspecified'
    };

    fetch('/api/add_thread', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    }).then(r => r.json()).then(d => { if (d.success) location.reload(); });
}

function openEditModal(id, name, redacted, subCat, type, cadence, time, parentId, hasChildren) {
    const labelEl = document.querySelector(`.habit-label[data-cat]:has(button[onclick*="'${id}'"])`);
    const cat = labelEl ? labelEl.dataset.cat : '';

    const select = document.getElementById('editThreadParent');
    const options = select.querySelectorAll('option');
    if (hasChildren) {
        select.disabled = true;
        select.title = "This habit already has derivative habits, so it cannot become a derivative itself.";
    } else {
        select.disabled = false;
        select.title = "";
    }

    options.forEach(opt => {
        const optCat = opt.getAttribute('data-cat');
        if ((optCat === 'all' || optCat === cat) && opt.value != id) {
            opt.style.display = 'block';
        } else {
            opt.style.display = 'none';
        }
    });

    document.getElementById('editThreadId').value = id;
    document.getElementById('editThreadName').value = name || '';
    document.getElementById('editThreadRedacted').value = redacted || '';
    document.getElementById('editThreadSubCat').value = subCat || '';
    document.getElementById('editThreadType').value = type || 'perpetual';

    select.value = parentId || "";

    setCadenceValue('edit', cadence);
    toggleCadenceMode('edit');

    document.getElementById('editThreadTime').value = time || 'unspecified';

    showModalWindow('editThreadModal');
}

function submitEditThread() {
    const parentIdVal = document.getElementById('editThreadParent').value;
    const currentId = document.getElementById('editThreadId').value;

    const finalParentId = (parentIdVal == currentId) ? null : (parentIdVal ? parseInt(parentIdVal) : null);

    const payload = {
        id: currentId,
        name: document.getElementById('editThreadName').value,
        redacted: document.getElementById('editThreadRedacted').value,
        sub_category: document.getElementById('editThreadSubCat').value,
        type: document.getElementById('editThreadType').value,
        cadence: getCadenceValue('edit'),
        parent_id: finalParentId,
        time_of_day: document.getElementById('editThreadTime').value
    };

    fetch('/api/edit_thread', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    }).then(r => r.json()).then(d => {
        if (d.success) location.reload();
        else alert(d.error);
    });
}

function openContextModalFromHeader() {
    showModalWindow('contextModal');
}

let currentContextDate = '';

function openContextModalFromHeader() {
    const chicagoTimeStr = new Date().toLocaleString("en-US", { timeZone: "America/Chicago" });
    const today = new Date(chicagoTimeStr);
    const dateStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    openContextModalForDate(dateStr);
}

async function openContextModalForDate(dateStr) {
    currentContextDate = dateStr;

    try {
        const resp = await fetch('/api/get_day_info', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date: dateStr })
        });
        const data = await resp.json();

        if (data.success) {
            dcOffRoutine = data.off;
            document.getElementById('ctxOffReason').value = data.off_reason;

            document.getElementById('bh_hydroxizine').checked = data.bh_hydroxizine;
            document.getElementById('bh_ritalin').checked = data.bh_ritalin;
            document.getElementById('bh_modafinil').checked = data.bh_modafinil;
            document.getElementById('bh_caffeine').checked = data.bh_caffeine;
            document.getElementById('bh_alcohol').checked = data.bh_alcohol;
            document.getElementById('bh_thc').checked = data.bh_thc;

            dcIntentHorizon = data.intent_horizon || 'survival';
            document.getElementById('dcIntentHeader').value = data.intent_header;
            document.getElementById('dcIntentNotes').value = data.intent_notes;

            dcResilStatus = data.resil_status || 'baseline';
            document.getElementById('dcResilHeader').value = data.resil_header;
            document.getElementById('dcResilNotes').value = data.resil_notes;

            renderDcColors();

            document.querySelector('#contextModal .modal-title').innerText = `Day Context: ${dateStr}`;

            showModalWindow('contextModal');
        }
    } catch (e) {
        console.error("Error loading day context", e);
    }
}

function saveContext() {
    const payload = {
        date: currentContextDate,
        off_routine: dcOffRoutine,
        off_reason: document.getElementById('ctxOffReason').value,
        bh_hydroxizine: document.getElementById('bh_hydroxizine').checked,
        bh_ritalin: document.getElementById('bh_ritalin').checked,
        bh_modafinil: document.getElementById('bh_modafinil').checked,
        bh_caffeine: document.getElementById('bh_caffeine').checked,
        bh_alcohol: document.getElementById('bh_alcohol').checked,
        bh_thc: document.getElementById('bh_thc').checked,
        intent_horizon: dcIntentHorizon,
        intent_header: document.getElementById('dcIntentHeader').value,
        intent_notes: document.getElementById('dcIntentNotes').value,
        resil_status: dcResilStatus,
        resil_header: document.getElementById('dcResilHeader').value,
        resil_notes: document.getElementById('dcResilNotes').value
    };

    fetch('/api/update_day_context', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
    }).then(() => location.reload());
}

let activeCell = null;
function handleCellClick(el) {
    if (!IS_AUTH) { showModalWindow('loginModal'); return; }
    const status = el.getAttribute('data-status');
    const next = (status === 'empty') ? 'hit' : 'empty';

    const currentNote = el.getAttribute('data-reason') || "";
    updateSquare(el, next, currentNote);
}

function updateSquare(el, status, reason) {
    el.setAttribute('data-status', status);

    if (reason && reason.trim() !== "") {
        el.setAttribute('data-reason', reason);
    } else {
        el.removeAttribute('data-reason');
    }

    let newClass = 'habit-cell ';
    if (status === 'hit') newClass += 'completed ';
    if (status === 'miss') newClass += 'miss ';
    if (el.classList.contains('is-today')) newClass += 'is-today ';
    if (el.classList.contains('off-routine')) newClass += 'off-routine ';
    if (el.classList.contains('past-week')) newClass += 'past-week ';

    el.className = newClass;

    updateRowVisuals(el.getAttribute('data-id'), el.getAttribute('data-week'), el.getAttribute('data-cadence'));

    fetch('/api/toggle_status', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: el.getAttribute('data-id'), date: el.getAttribute('data-date'), status: status, miss_reason: reason })
    });
}

function updateRowVisuals(threadId, weekIndex, cadence) {
    let target = 0;
    if (cadence === 'weekly') target = 1;
    if (cadence === '3x_week') target = 3;

    if (target > 0) {
        const cells = document.querySelectorAll(`.habit-cell[data-id="${threadId}"][data-week="${weekIndex}"]`);
        let hits = 0;
        cells.forEach(c => { if (c.getAttribute('data-status') === 'hit') hits++; });

        cells.forEach(c => {
            const status = c.getAttribute('data-status');
            if (status !== 'hit' && status !== 'miss') {
                if (hits >= target) c.classList.add('fulfilled');
                else c.classList.remove('fulfilled');
            } else {
                c.classList.remove('fulfilled');
            }
        });
    }
}

function handleRightClick(e, el) {
    e.preventDefault();
    if (!IS_AUTH) { showModalWindow('loginModal'); return; }
    activeCell = el;

    const currentNote = el.getAttribute('data-reason') || "";
    document.getElementById('standaloneSquareNote').value = currentNote;

    showModalWindow('squareNoteModal');
}

function saveSquareNote() {
    if (activeCell) {
        const newNote = document.getElementById('standaloneSquareNote').value;
        const currentStatus = activeCell.getAttribute('data-status');
        updateSquare(activeCell, currentStatus, newNote);
    }
    hideModalWindow('squareNoteModal');
}

function addTaskAPI() {
    const input = document.getElementById('taskInput');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    fetch('/api/update_day_context', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ comments: text })
    }).then(() => location.reload());
}

document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
        const gridWrapper = document.querySelector('.grid-wrapper.desktop-only');
        if (gridWrapper) {
            gridWrapper.scrollLeft = gridWrapper.scrollWidth;
        }
    }, 50);

    if (localStorage.getItem('habitEditMode') === 'true') {
        document.body.classList.add('edit-mode');
        document.querySelectorAll('.edit-toggle-btn').forEach(btn => {
            btn.classList.add('on');
        });
    }

    const savedSortMode = localStorage.getItem('habitSortMode');
    if (savedSortMode) {
        if ((savedSortMode === 'calendar' && !IS_AUTH) || savedSortMode === 'time') {
            setSortMode('type');
        } else {
            setSortMode(savedSortMode);
        }
    }
    const taskInput = document.getElementById('taskInput');
    if (taskInput) {
        taskInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                addTaskAPI();
            }
        });
    }
});

function toggleMobileView() {
    document.body.classList.toggle('show-log-view');

    const btn = document.getElementById('mobileViewToggleBtn');
    if (document.body.classList.contains('show-log-view')) {
        btn.innerHTML = '📊 Tracker';
    } else {
        btn.innerHTML = '📝 Log';
    }
}

function deleteLog(btn) {
    if (!confirm("Delete this entry?")) return;

    const date = btn.getAttribute('data-date');
    const time = btn.getAttribute('data-time');
    const text = btn.getAttribute('data-text');

    fetch('/api/delete_log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date: date, time: time, text: text })
    }).then(r => r.json()).then(d => {
        if (d.success) {
            location.reload();
        } else {
            alert("Error: " + d.error);
        }
    });
}

let currentWeekId = '';

async function openWeekContextModal(weekId) {
    currentWeekId = weekId;

    try {
        const resp = await fetch('/api/get_week_info', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ week_id: weekId })
        });
        const data = await resp.json();

        if (data.success) {
            document.getElementById('wcHeader').value = data.header || '';
            document.getElementById('wcNotes').value = data.notes || '';
            document.getElementById('weekModalTitle').innerText = `Week Context: ${weekId}`;

            showModalWindow('weekContextModal');
        }
    } catch (e) {
        console.error("Error loading week context", e);
    }
}

function saveWeekContext() {
    const payload = {
        week_id: currentWeekId,
        header: document.getElementById('wcHeader').value,
        notes: document.getElementById('wcNotes').value
    };

    fetch('/api/update_week_context', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
    }).then(() => location.reload());
}

function toggleCadenceMode(prefix) {
    const mode = document.getElementById(prefix + 'ThreadCadenceMode').value;
    const daysDiv = document.getElementById(prefix + 'ThreadDays');
    if (daysDiv) {
        daysDiv.style.display = (mode === 'specific') ? 'flex' : 'none';
    }
}

function getCadenceValue(prefix) {
    const mode = document.getElementById(prefix + 'ThreadCadenceMode').value;
    if (mode === 'daily') return 'daily';
    const checkboxes = document.querySelectorAll('#' + prefix + 'ThreadDays input:checked');
    return Array.from(checkboxes).map(cb => cb.value).join(',');
}

function setCadenceValue(prefix, val) {
    const modeSelect = document.getElementById(prefix + 'ThreadCadenceMode');
    const daysDiv = document.getElementById(prefix + 'ThreadDays');
    const checkboxes = daysDiv.querySelectorAll('input');

    checkboxes.forEach(cb => cb.checked = false);

    if (!val || val === 'daily' || !val.includes(',')) {
        modeSelect.value = 'daily';
        daysDiv.style.display = 'none';
    } else {
        modeSelect.value = 'specific';
        daysDiv.style.display = 'flex';
        val.split(',').forEach(d => {
            const cb = daysDiv.querySelector(`input[value="${d}"]`);
            if (cb) cb.checked = true;
        });
    }
}

function openAddModal(cat) {
    currentCat = cat;
    document.getElementById('catNameDisplay').innerText = cat;

    const select = document.getElementById('newThreadParent');
    const options = select.querySelectorAll('option');

    select.value = "";

    options.forEach(opt => {
        const optCat = opt.getAttribute('data-cat');
        if (optCat === 'all' || optCat === cat) {
            opt.style.display = 'block';
        } else {
            opt.style.display = 'none';
        }
    });

    document.getElementById('newThreadName').value = '';
    showModalWindow('addThreadModal');
}

let focusModeActive = false;

function toggleFocusMode() {
    focusModeActive = !focusModeActive;
    const btn = document.getElementById('focusBtn');

    btn.classList.toggle('black', focusModeActive);

    const chicagoTimeStr = new Date().toLocaleString("en-US", { timeZone: "America/Chicago" });
    const today = new Date(chicagoTimeStr);
    const todayStr = today.getFullYear() + '-' + String(today.getMonth() + 1).padStart(2, '0') + '-' + String(today.getDate()).padStart(2, '0');

    const habitIndices = [...new Set(Array.from(document.querySelectorAll('.habit-label')).map(l => l.dataset.idx))];

    habitIndices.forEach(idx => {
        const label = document.querySelector(`.habit-label[data-idx="${idx}"]`);
        const cells = document.querySelectorAll(`.habit-cell[data-idx="${idx}"]`);

        const todayCell = document.querySelector(`.habit-cell[data-idx="${idx}"][data-date="${todayStr}"]`);

        if (focusModeActive) {
            if (todayCell && todayCell.classList.contains('padding')) {
                label.style.display = 'none';
                cells.forEach(c => c.style.display = 'none');
            }
        } else {
            label.style.display = 'flex';
            cells.forEach(c => c.style.display = 'block');
        }
    });
}

function toggleQuickEdit() {
    document.body.classList.toggle('show-quick-edit');
    const isActive = document.body.classList.contains('show-quick-edit');
    localStorage.setItem('quickEditMode', isActive);
}

function quickEditSave(threadId, fieldChanged) {
    const panel = document.querySelector(`.qe-panel[data-id="${threadId}"]`);
    if (!panel) return;

    const parentId = panel.querySelector('.qe-parent').value;
    const checkboxes = panel.querySelectorAll('.qe-cadence input:checked');

    let cadence = 'daily';
    if (checkboxes.length > 0 && checkboxes.length < 7) {
        cadence = Array.from(checkboxes).map(cb => cb.value).join(',');
    } else if (checkboxes.length === 0) {
        cadence = 'none';
    }

    const payload = {
        id: threadId,
        name: panel.dataset.name,
        redacted: panel.dataset.redacted,
        sub_category: panel.dataset.subcat,
        type: panel.dataset.type,
        cadence: cadence,
        parent_id: parentId ? parseInt(parentId) : null,
        time_of_day: panel.dataset.time
    };

    fetch('/api/edit_thread', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    }).then(r => r.json()).then(d => {
        if (d.success) {
            if (fieldChanged === 'parent') {
                location.reload();
            }
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    if (localStorage.getItem('quickEditMode') === 'true') {
        document.body.classList.add('show-quick-edit');
    }
});
