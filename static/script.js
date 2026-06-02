const API_URL = window.location.origin;
let currentPage = 1;
let expenseModal = new bootstrap.Modal(document.getElementById('expenseModal'));
let salaryModal = new bootstrap.Modal(document.getElementById('salaryModal'));
let categoryModal = new bootstrap.Modal(document.getElementById('categoryModal'));
let importModal = new bootstrap.Modal(document.getElementById('importModal'));

const LIMIT = 50;
let allItems = [];
let allCategories = [];
let currentMonthFilter = '';
let chartInstance = null;
let searchTimeout = null;
let selectedImportFile = null;

/* ── Bootstrap Theme Initializer ── */
document.addEventListener('DOMContentLoaded', async () => {
    initTheme();
    await loadCurrentUser();
    refreshAll();
    setupDragAndDrop();

    // Heartbeat logic for keeping server alive and triggering background auto-syncs
    setInterval(async () => {
        try {
            const res = await fetch(`${API_URL}/heartbeat`, { method: 'POST', keepalive: true, credentials: 'include' });
            if (res.ok) {
                const data = await res.json();
                updateDatabaseStatus(data.database);
            }
        } catch (e) {
            updateDatabaseStatus("offline");
        }
    }, 30000);
});

/* ── Dark / Light Theme System ── */
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
    
    // Dynamically re-render charts to adapt label colors and borders to the theme
    renderCharts();
}

function updateThemeIcon(theme) {
    const icon = document.getElementById('themeIcon');
    if (!icon) return;
    if (theme === 'dark') {
        icon.className = 'bi bi-moon-stars-fill';
        icon.style.color = '#fbbf24'; // Warm amber moon
    } else {
        icon.className = 'bi bi-sun-fill';
        icon.style.color = '#f59e0b'; // Amber sun
    }
}

/* Update visual database online/offline badges */
function updateDatabaseStatus(status) {
    const badge = document.getElementById('dbStatusBadge');
    const badgeMobile = document.getElementById('dbStatusBadgeMobile');
    
    [badge, badgeMobile].forEach(el => {
        if (!el) return;
        if (status === 'online') {
            el.className = 'sync-badge sync-online';
            el.textContent = 'Online';
        } else {
            el.className = 'sync-badge sync-offline';
            el.textContent = 'Offline (Local)';
        }
    });
}

/* ── Wrapped Authenticated Fetch ── */
async function authFetch(url, opts = {}) {
    opts.credentials = 'include';
    const res = await fetch(url, opts);
    if (res.status === 401) {
        window.location.href = '/login';
        return res;
    }
    return res;
}

/* Load current user profile details into navbar */
async function loadCurrentUser() {
    try {
        const res = await authFetch(`${API_URL}/auth/me`);
        if (!res.ok) return;
        const data = await res.json();
        const avatar = document.getElementById('userAvatar');
        const name = document.getElementById('userName');
        const adminL = document.getElementById('adminLink');
        
        if (avatar) avatar.textContent = (data.username || '?')[0].toUpperCase();
        if (name) name.textContent = data.username || 'User';
        if (adminL && data.role === 'admin') adminL.style.display = '';
    } catch (e) {
        console.error('Authentication load failure:', e);
    }
}

async function doLogout() {
    localStorage.removeItem('autoLoginActive');
    await fetch(`${API_URL}/auth/logout`, { method: 'POST', credentials: 'include' });
    window.location.href = '/login';
}

async function refreshAll() {
    showLoading(true);
    await Promise.all([
        loadCategories(),
        loadStats(),
        loadExpenses(1, true),
        renderCharts()
    ]);
    showLoading(false);
}

// Categories Management
async function loadCategories() {
    try {
        const res = await authFetch(`${API_URL}/categories`);
        allCategories = await res.json();
        updateCategorySelect();
    } catch (e) {
        console.error('Failed to load categories:', e);
    }
}

function updateCategorySelect() {
    const sel = document.getElementById('itemCategory');
    if (!sel) return;

    const currentVal = sel.value;
    let html = '';
    allCategories.forEach(c => {
        html += `<option value="${c.name}">${c.name}</option>`;
    });
    sel.innerHTML = html;

    if (currentVal && allCategories.find(c => c.name === currentVal)) {
        sel.value = currentVal;
    }
}

function openCategoryModal() {
    renderCategoryList();
    categoryModal.show();
}

function renderCategoryList() {
    const list = document.getElementById('categoryList');
    if (!list) return;
    list.innerHTML = allCategories.map(c => `
        <div class="category-list-item d-flex justify-content-between align-items-center py-2 border-bottom">
            <span>${c.name}</span>
            <button class="btn btn-sm btn-outline-danger border-0" onclick="deleteCategory('${c.id}')">
                <i class="bi bi-trash"></i>
            </button>
        </div>
    `).join('');
}

async function addCategory() {
    const input = document.getElementById('newCatName');
    const name = input.value.trim();
    if (!name) return;

    try {
        const res = await authFetch(`${API_URL}/categories`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (res.ok) {
            input.value = '';
            await loadCategories();
            renderCategoryList();
            showToast('Category created successfully', 'success');
        } else {
            const d = await res.json();
            showToast(d.error || 'Failed to create category', 'danger');
        }
    } catch (e) {
        console.error(e);
    }
}

async function deleteCategory(id) {
    if (!confirm('Are you sure you want to delete this category?')) return;
    try {
        const res = await authFetch(`${API_URL}/categories/${id}`, { method: 'DELETE' });
        if (res.ok) {
            await loadCategories();
            renderCategoryList();
            showToast('Category deleted', 'success');
        } else {
            const d = await res.json();
            showToast(d.error || 'Could not delete category', 'danger');
        }
    } catch (e) {
        console.error(e);
        showToast('Error deleting category', 'danger');
    }
}

// Balance and Filtering Stats
async function loadStats() {
    try {
        const url = currentMonthFilter
            ? `${API_URL}/dashboard-stats?month=${encodeURIComponent(currentMonthFilter)}`
            : `${API_URL}/dashboard-stats`;

        const res = await authFetch(url);
        const data = await res.json();

        updateStat('prevBal', data.previous_balance);
        updateStat('salaryAmount', data.salary);
        updateStat('expensesAmount', data.current_expenses);
        updateStat('remainingBal', data.remaining_balance);
        
        updateDatabaseStatus(data.database);

        const remEl = document.getElementById('remainingBal');
        if (remEl) {
            if (data.remaining_balance < 0) {
                remEl.className = 'stat-value fw-bold text-danger';
            } else {
                remEl.className = 'stat-value fw-bold text-success';
            }
        }

        updateFilterDropdown(data.available_months, data.current_filter);
        currentMonthFilter = data.current_filter;

    } catch (e) {
        console.error('Stats query failure:', e);
    }
}

function updateStat(id, val) {
    const el = document.getElementById(id);
    if (!el) return;
    const num = val || 0;
    if (num < 0) {
        el.textContent = '-\u20B9' + Math.abs(num).toLocaleString('en-IN');
    } else {
        el.textContent = '\u20B9' + num.toLocaleString('en-IN');
    }
}

function updateFilterDropdown(months, activeMonth) {
    const select = document.getElementById('monthFilter');
    if (!select) return;

    let html = '';
    months.forEach(m => {
        html += `<option value="${m}" ${m === activeMonth ? 'selected' : ''}>${m}</option>`;
    });
    if (!months.includes(activeMonth) && activeMonth) {
        html = `<option value="${activeMonth}" selected>${activeMonth}</option>` + html;
    }
    select.innerHTML = html;
    select.value = activeMonth || '';
}

// Expenses Data Loader
async function loadExpenses(page, reset = false) {
    try {
        let url = `${API_URL}/expenses?page=${page}&limit=${LIMIT}`;
        if (currentMonthFilter) {
            url += `&month=${encodeURIComponent(currentMonthFilter)}`;
        }

        const searchVal = document.getElementById('searchInput').value;
        if (searchVal) {
            url += `&search=${encodeURIComponent(searchVal)}`;
        }

        const res = await authFetch(url);
        const data = await res.json();

        if (reset) {
            allItems = [];
            document.getElementById('expenseList').innerHTML = '';
        }

        allItems = allItems.concat(data.items);
        renderTable(data.items, data.total, reset);

        const btn = document.getElementById('loadMoreBtn');
        const info = document.getElementById('pageInfo');
        if (data.has_next) {
            btn.style.display = 'inline-block';
            currentPage = data.page;
        } else {
            btn.style.display = 'none';
        }
        info.textContent = `Showing ${allItems.length} of ${data.total}`;

    } catch (error) {
        console.error(error);
    }
}

function getCategoryBadgeClass(category) {
    const cat = (category || '').toLowerCase();
    if (cat.includes('food') || cat.includes('grocer') || cat.includes('dine') || cat.includes('dining')) return 'badge-food';
    if (cat.includes('shop') || cat.includes('entertain') || cat.includes('movie') || cat.includes('play')) return 'badge-entertainment';
    if (cat.includes('transport') || cat.includes('travel') || cat.includes('taxi') || cat.includes('fuel')) return 'badge-transport';
    if (cat.includes('util') || cat.includes('bill') || cat.includes('rent')) return 'badge-utilities';
    if (cat.includes('health') || cat.includes('medic') || cat.includes('fit')) return 'badge-health';
    if (cat.includes('salary') || cat.includes('income') || cat.includes('earn')) return 'badge-income';
    return 'badge-general';
}

function renderTable(expenses, total = 0, reset = false) {
    const tbody = document.getElementById('expenseList');
    const tableContainer = document.querySelector('.table-responsive');
    const emptyState = document.getElementById('tableEmptyState');
    const loadMorePanel = document.getElementById('loadMoreBtn').parentElement;

    if (expenses.length === 0 && total === 0) {
        tbody.innerHTML = '';
        if (tableContainer) tableContainer.classList.add('d-none');
        if (emptyState) emptyState.classList.remove('d-none');
        if (loadMorePanel) loadMorePanel.classList.add('d-none');
        return;
    }

    if (tableContainer) tableContainer.classList.remove('d-none');
    if (emptyState) emptyState.classList.add('d-none');
    if (loadMorePanel) loadMorePanel.classList.remove('d-none');

    const html = expenses.map(item => {
        let dateDisplay = item.month;
        if (item.date) {
            const parts = item.date.split('-');
            if (parts.length === 3) {
                dateDisplay = `${parts[2]} ${parts[1]} ${parts[0]}`;
            } else {
                dateDisplay = item.date;
            }
        }

        const badgeClass = getCategoryBadgeClass(item.category);

        return `
        <tr>
            <td data-label="Item">
                <div class="fw-semibold text-dark">${item.item}</div>
            </td>
            <td data-label="Category">
                <span class="badge-custom ${badgeClass}">${item.category || 'General'}</span>
            </td>
            <td data-label="Date">
                <span class="badge-custom badge-date">${dateDisplay}</span>
            </td>
            <td data-label="Amount">
                <span class="fw-bold text-dark fs-6">&#8377;${(item.amount || 0).toLocaleString('en-IN')}</span>
            </td>
            <td data-label="Actions" class="text-end">
                <div class="d-flex justify-content-end gap-1">
                    <button class="btn-action btn-action-copy" onclick="duplicateExpense('${item.id}')" title="Duplicate">
                        <i class="bi bi-copy"></i>
                    </button>
                    <button class="btn-action btn-action-edit" onclick="openEditModal('${item.id}')" title="Edit">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn-action btn-action-delete" onclick="deleteExpense('${item.id}')" title="Delete">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
    `}).join('');

    if (reset || allItems.length === expenses.length) tbody.innerHTML = html;
    else tbody.insertAdjacentHTML('beforeend', html);
}

function onFilterChange() {
    currentMonthFilter = document.getElementById('monthFilter').value;
    refreshAll();
}

function onSearchChange() {
    if (searchTimeout) clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        currentPage = 1;
        loadExpenses(1, true);
    }, 400);
}

function loadMore() {
    loadExpenses(currentPage + 1, false);
}

function exportExcel(mode) {
    let url = `${API_URL}/export`;
    if (mode === 'current' && currentMonthFilter) {
        url += `?month=${encodeURIComponent(currentMonthFilter)}`;
    }
    window.location.href = url;
}

/* ── Dynamic Chart Rendering (Theme Adaptive) ── */
async function renderCharts() {
    const ctx = document.getElementById('expenseChart');
    const placeholder = document.getElementById('chartPlaceholder');
    const centerLabel = document.getElementById('chartCenterLabel');
    if (!ctx) return;

    let url = `${API_URL}/stats/category`;
    if (currentMonthFilter) url += `?month=${encodeURIComponent(currentMonthFilter)}`;

    try {
        const res = await authFetch(url);
        const data = await res.json();

        const labels = Object.keys(data);
        const values = Object.values(data);

        if (chartInstance) chartInstance.destroy();

        if (labels.length === 0) {
            ctx.style.display = 'none';
            if (placeholder) placeholder.classList.remove('d-none');
            if (centerLabel) centerLabel.style.display = 'none';
            return;
        }

        ctx.style.display = 'block';
        if (placeholder) placeholder.classList.add('d-none');
        if (centerLabel) {
            centerLabel.style.display = 'flex';
            const totalSum = values.reduce((a, b) => a + b, 0);
            document.getElementById('chartCenterValue').textContent = '₹' + totalSum.toLocaleString('en-IN');
        }

        // Adapt chart aesthetics to match light/dark styling dynamically
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
        const labelColor = currentTheme === 'dark' ? '#94a3b8' : '#64748b';
        const borderColor = currentTheme === 'dark' ? '#111827' : '#ffffff';

        chartInstance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: [
                        '#4f46e5', '#818cf8', '#06b6d4', '#10b981', '#f59e0b',
                        '#e11d48', '#ec4899', '#3b82f6', '#14b8a6'
                    ],
                    borderColor: borderColor,
                    borderWidth: 2,
                    hoverOffset: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '72%',
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            color: labelColor,
                            font: { family: 'Inter', size: 11, weight: '500' }
                        }
                    }
                }
            }
        });

    } catch (e) {
        console.error('Error drawing transaction charts:', e);
    }
}

/* ── Drag & Drop Excel Import System ── */
function setupDragAndDrop() {
    const dropZone = document.getElementById('dropZone');
    if (!dropZone) return;

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
        }, false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length) {
            handleFile(files[0]);
        }
    }, false);
}

function triggerFileInput() {
    const fileInput = document.getElementById('importFile');
    if (fileInput) fileInput.click();
}

function handleFileSelect(event) {
    const files = event.target.files;
    if (files.length) {
        handleFile(files[0]);
    }
}

function handleFile(file) {
    if (!file.name.endsWith('.xlsx')) {
        showToast('Please upload an Excel file (.xlsx)', 'danger');
        return;
    }
    selectedImportFile = file;
    const textEl = document.getElementById('dropZoneText');
    if (textEl) {
        textEl.textContent = `Selected: ${file.name}`;
        textEl.style.color = 'var(--primary-color)';
    }
}

function openImportModal() {
    selectedImportFile = null;
    const textEl = document.getElementById('dropZoneText');
    if (textEl) {
        textEl.textContent = 'Drag & Drop file here';
        textEl.style.color = '';
    }
    importModal.show();
}

async function uploadImport() {
    if (!selectedImportFile) {
        showToast('Please select or drop a file to import', 'warning');
        return;
    }

    const formData = new FormData();
    formData.append('file', selectedImportFile);

    showLoading(true);
    try {
        const res = await authFetch(`${API_URL}/import`, { method: 'POST', body: formData });
        const data = await res.json();

        if (res.ok) {
            importModal.hide();
            showToast(data.message, 'success');
            refreshAll();
        } else {
            showToast('Import failed: ' + data.error, 'danger');
        }
    } catch (e) {
        showToast('Spreadsheet upload failed due to network error', 'danger');
    } finally {
        showLoading(false);
    }
}

/* ── Transaction CRUD Actions ── */
function openSalaryModal() {
    const now = new Date();
    const month = currentMonthFilter || now.toLocaleString('en-IN', { month: 'short', year: 'numeric' });
    document.getElementById('salaryMonthLabel').textContent = month;
    document.getElementById('salaryInput').value = '';
    salaryModal.show();
}

async function saveSalary() {
    const amount = document.getElementById('salaryInput').value;
    const month = document.getElementById('salaryMonthLabel').textContent;
    if (!amount) {
        showToast('Please insert a valid salary amount', 'warning');
        return;
    }

    showLoading(true);
    try {
        await authFetch(`${API_URL}/salary`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ month, amount })
        });
        salaryModal.hide();
        loadStats();
        showToast('Salary setting saved successfully', 'success');
    } catch (e) {
        showToast('Failed to save salary details', 'danger');
    } finally {
        showLoading(false);
    }
}

function openAddModal() {
    document.getElementById('modalTitle').textContent = 'Add New Expense';
    document.getElementById('expenseForm').reset();
    document.getElementById('expenseId').value = '';

    // Automatically select today's date in local calendar
    document.getElementById('itemDate').valueAsDate = new Date();
    document.getElementById('itemCategory').value = 'General';

    expenseModal.show();
}

function duplicateExpense(id) {
    const item = allItems.find(e => e.id === id);
    if (!item) return;

    openAddModal();
    document.getElementById('itemName').value = item.item;
    document.getElementById('itemAmount').value = item.amount;
    document.getElementById('itemCategory').value = item.category || 'General';
    showToast('Duplicate transaction details loaded', 'success');
}

function openEditModal(id) {
    const item = allItems.find(e => e.id === id);
    if (!item) return;
    document.getElementById('modalTitle').textContent = 'Edit Expense';
    document.getElementById('expenseId').value = item.id;
    document.getElementById('itemName').value = item.item;
    document.getElementById('itemAmount').value = item.amount;
    document.getElementById('itemCategory').value = item.category || 'General';

    if (item.date) {
        document.getElementById('itemDate').value = item.date;
    } else {
        document.getElementById('itemDate').valueAsDate = new Date();
    }

    expenseModal.show();
}

async function saveExpense() {
    const id = document.getElementById('expenseId').value;
    const item = document.getElementById('itemName').value;
    const amount = document.getElementById('itemAmount').value;
    const category = document.getElementById('itemCategory').value;
    const date = document.getElementById('itemDate').value;

    if (!item || !amount || !date) {
        showToast('Please fill in all transaction fields', 'warning');
        return;
    }

    showLoading(true);
    const payload = { item, amount, category, date };
    const method = id ? 'PUT' : 'POST';
    const url = id ? `${API_URL}/expenses/${id}` : `${API_URL}/expenses`;

    try {
        const res = await authFetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (res.ok) {
            expenseModal.hide();
            showToast(id ? 'Transaction updated' : 'Transaction created', 'success');
            refreshAll();
        } else {
            const data = await res.json();
            showToast(data.error || 'Failed to save transaction', 'danger');
        }
    } catch (e) {
        showToast('Network error while logging expense', 'danger');
    } finally {
        showLoading(false);
    }
}

async function deleteExpense(id) {
    if (!confirm('Are you sure you want to delete this expense?')) return;
    showLoading(true);
    try {
        await authFetch(`${API_URL}/expenses/${id}`, { method: 'DELETE' });
        showToast('Transaction deleted', 'success');
        refreshAll();
    } catch (e) {
        showToast('Network error deleting transaction', 'danger');
    } finally {
        showLoading(false);
    }
}

async function confirmClearAll() {
    if (!confirm('WARNING: Are you sure you want to permanently erase ALL data? This operation cannot be undone.')) return;
    showLoading(true);
    try {
        await authFetch(`${API_URL}/expenses`, { method: 'DELETE' });
        showToast('All transactions erased', 'success');
        refreshAll();
    } catch (e) {
        showToast('Network error while erasing database', 'danger');
    } finally {
        showLoading(false);
    }
}

function showLoading(show) {
    const el = document.getElementById('loadingOverlay');
    if (el) el.style.display = show ? 'flex' : 'none';
}

function showToast(msg, type = 'primary') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const id = 'toast_' + Date.now();
    const html = `
        <div id="${id}" class="toast align-items-center text-white bg-${type} border-0 shadow-lg" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body fw-medium">${msg}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', html);
    const toastEl = document.getElementById(id);
    const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
    toast.show();
    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
}
