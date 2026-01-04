const API_URL = 'http://127.0.0.1:8000';
let currentPage = 1;
let expenseModal = new bootstrap.Modal(document.getElementById('expenseModal'));
let salaryModal = new bootstrap.Modal(document.getElementById('salaryModal'));
const LIMIT = 50;
let allItems = [];
let allCategories = [];
let currentMonthFilter = '';
let chartInstance = null;
let searchTimeout = null;
let categoryModal = new bootstrap.Modal(document.getElementById('categoryModal'));

document.addEventListener('DOMContentLoaded', () => {
    refreshAll();

    // Heartbeat for keeping .exe alive
    setInterval(() => {
        fetch(`${API_URL}/heartbeat`, { method: 'POST', keepalive: true }).catch(e => { });
    }, 2000);
});

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

// Categories
async function loadCategories() {
    try {
        const res = await fetch(`${API_URL}/categories`);
        allCategories = await res.json();
        updateCategorySelect();
    } catch (e) { console.error('Cats error:', e); }
}

function updateCategorySelect() {
    const sel = document.getElementById('itemCategory');
    if (!sel) return;

    // Keep current value if possible
    const currentVal = sel.value;

    let html = '';
    // Sort logic handled in backend or here
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
    list.innerHTML = allCategories.map(c => `
        <div class="category-list-item">
            <span>${c.name}</span>
            <button class="btn btn-sm btn-outline-danger border-0" onclick="deleteCategory(${c.id})">
                <i class="bi bi-x-lg"></i>
            </button>
        </div>
    `).join('');
}

async function addCategory() {
    const input = document.getElementById('newCatName');
    const name = input.value.trim();
    if (!name) return;

    try {
        const res = await fetch(`${API_URL}/categories`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (res.ok) {
            input.value = '';
            await loadCategories();
            renderCategoryList();
        } else {
            const d = await res.json();
            alert(d.error);
        }
    } catch (e) { console.error(e); }
}

async function deleteCategory(id) {
    if (!confirm('Delete Category?')) return;
    try {
        await fetch(`${API_URL}/categories/${id}`, { method: 'DELETE' });
        await loadCategories();
        renderCategoryList();
    } catch (e) { console.error(e); }
}

// Stats & Filter
async function loadStats() {
    try {
        const url = currentMonthFilter
            ? `${API_URL}/dashboard-stats?month=${encodeURIComponent(currentMonthFilter)}`
            : `${API_URL}/dashboard-stats`;

        const res = await fetch(url);
        const data = await res.json();

        updateStat('prevBal', data.previous_balance);
        updateStat('salaryAmount', data.salary);
        updateStat('expensesAmount', data.current_expenses);
        updateStat('remainingBal', data.remaining_balance);

        const remEl = document.getElementById('remainingBal');
        if (data.remaining_balance < 0) {
            remEl.classList.add('text-danger'); remEl.classList.remove('text-success');
        } else {
            remEl.classList.add('text-success'); remEl.classList.remove('text-danger');
        }

        updateFilterDropdown(data.available_months, data.current_filter);
        currentMonthFilter = data.current_filter;

    } catch (e) {
        console.error('Stats error:', e);
    }
}

function updateStat(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = '₹' + (val || 0).toLocaleString('en-IN');
}

function updateFilterDropdown(months, activeMonth) {
    const select = document.getElementById('monthFilter');
    if (!select) return;

    let html = '';
    months.forEach(m => {
        html += `<option value="${m}" ${m === activeMonth ? 'selected' : ''}>${m}</option>`;
    });
    // Add active if missing
    if (!months.includes(activeMonth) && activeMonth) {
        html = `<option value="${activeMonth}" selected>${activeMonth}</option>` + html;
    }
    select.innerHTML = html;
    select.value = activeMonth || '';
}

// Expenses List
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

        const res = await fetch(url);
        const data = await res.json();

        if (reset) {
            allItems = [];
            document.getElementById('expenseList').innerHTML = '';
        }

        allItems = allItems.concat(data.items);
        renderTable(data.items);

        const btn = document.getElementById('loadMoreBtn');
        const info = document.getElementById('pageInfo');
        if (data.has_next) {
            btn.style.display = 'inline-block';
            currentPage = data.page;
        } else {
            btn.style.display = 'none';
        }
        info.textContent = `Showing ${allItems.length} of ${data.total}`;

    } catch (error) { console.error(error); }
}

function renderTable(expenses) {
    const tbody = document.getElementById('expenseList');
    const html = expenses.map(item => {
        let dateDisplay = item.month; // Default
        if (item.date) {
            // Format 2025-12-14 to "14 12 2025" (DD MM YYYY)
            const parts = item.date.split('-');
            if (parts.length === 3) {
                dateDisplay = `${parts[2]} ${parts[1]} ${parts[0]}`;
            } else {
                dateDisplay = item.date;
            }
        }

        return `
        <tr>
            <td data-label="Item">
                <div class="fw-bold text-dark">${item.item}</div>
            </td>
            <td data-label="Category">
                <span class="badge bg-light text-secondary border">${item.category || 'General'}</span>
            </td>
            <td data-label="Date">
                <span class="badge bg-light text-dark border">${dateDisplay}</span>
            </td>
            <td data-label="Amount">
                <span class="fw-bold text-dark fs-5">₹${(item.amount || 0).toLocaleString('en-IN')}</span>
            </td>
             <td data-label="Actions">
                <div class="btn-group">
                    <button class="btn btn-sm btn-outline-secondary" onclick="duplicateExpense(${item.id})" title="Duplicate">
                        <i class="bi bi-copy"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-primary" onclick="openEditModal(${item.id})">
                        <i class="bi bi-pencil-square"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteExpense(${item.id})">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
    `}).join('');

    if (expenses.length === 0 && allItems.length === 0) {
        tbody.innerHTML = window.innerWidth >= 768
            ? `<tr><td colspan="5" class="text-center py-5 text-muted">No expenses found.</td></tr>`
            : `<div class="text-center py-5 text-muted">No expenses found.</div>`;
    } else {
        if (allItems.length === expenses.length) tbody.innerHTML = html;
        else tbody.insertAdjacentHTML('beforeend', html);
    }
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
    }, 500);
}

// Actions
function exportExcel(mode) {
    let url = `${API_URL}/export`;
    if (mode === 'current' && currentMonthFilter) {
        url += `?month=${encodeURIComponent(currentMonthFilter)}`;
    }
    // if mode === 'all', no query param needed
    window.location.href = url;
}

let importModal = new bootstrap.Modal(document.getElementById('importModal'));

function openImportModal() {
    importModal.show();
}

async function uploadImport() {
    const fileInput = document.getElementById('importFile');
    const file = fileInput.files[0];
    if (!file) { showToast('Select a file', 'warning'); return; }

    const formData = new FormData();
    formData.append('file', file);

    showLoading(true);
    try {
        const res = await fetch(`${API_URL}/import`, { method: 'POST', body: formData });
        const data = await res.json();

        if (res.ok) {
            importModal.hide();
            showToast(data.message, 'success');
            refreshAll();
        } else {
            showToast('Import failed: ' + data.error, 'danger');
        }
    } catch (e) { showToast('Error', 'danger'); }
    finally { showLoading(false); }
}

async function renderCharts() {
    const ctx = document.getElementById('expenseChart');
    if (!ctx) return;

    // Fetch stats
    let url = `${API_URL}/stats/category`;
    if (currentMonthFilter) url += `?month=${encodeURIComponent(currentMonthFilter)}`;

    try {
        const res = await fetch(url);
        const data = await res.json();
        // data: { 'Food': 120, 'Travel': 300 }

        const labels = Object.keys(data);
        const values = Object.values(data);

        if (chartInstance) chartInstance.destroy();

        if (labels.length === 0) {
            // Maybe show "No Data" placeholder? For now just empty canvas
            return;
        }

        chartInstance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: [
                        '#4e73df', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b',
                        '#858796', '#5a5c69', '#2e59d9', '#17a673'
                    ],
                    hoverOffset: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'right' }
                }
            }
        });

    } catch (e) { console.error(e); }
}

function openSalaryModal() {
    const month = currentMonthFilter || formatDate(new Date());
    document.getElementById('salaryMonthLabel').textContent = month;
    document.getElementById('salaryInput').value = '';
    salaryModal.show();
}

async function saveSalary() {
    const amount = document.getElementById('salaryInput').value;
    const month = document.getElementById('salaryMonthLabel').textContent;
    if (!amount) { showToast('Invalid amount', 'warning'); return; }

    showLoading(true);
    try {
        await fetch(`${API_URL}/salary`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ month, amount })
        });
        salaryModal.hide();
        loadStats();
        showToast('Salary saved', 'success');
    } catch (e) { showToast('Error', 'danger'); }
    finally { showLoading(false); }
}

function openAddModal() {
    document.getElementById('modalTitle').textContent = 'Add New Expense';
    document.getElementById('expenseForm').reset();
    document.getElementById('expenseId').value = '';

    // Set Default Date to Today
    document.getElementById('itemDate').valueAsDate = new Date();
    document.getElementById('itemCategory').value = 'General';

    expenseModal.show();
}

function duplicateExpense(id) {
    const item = allItems.find(e => e.id === id);
    if (!item) return;

    openAddModal();
    // Pre-fill
    document.getElementById('itemName').value = item.item;
    document.getElementById('itemAmount').value = item.amount;
    document.getElementById('itemCategory').value = item.category || 'General';
    // Date stays today
    showToast('Duplicate info loaded', 'info');
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
        document.getElementById('itemDate').valueAsDate = new Date(); // fallback
    }

    expenseModal.show();
}

async function saveExpense() {
    const id = document.getElementById('expenseId').value;
    const item = document.getElementById('itemName').value;
    const amount = document.getElementById('itemAmount').value;
    const category = document.getElementById('itemCategory').value;
    const date = document.getElementById('itemDate').value; // YYYY-MM-DD

    if (!item || !amount || !date) {
        showToast('Fill all fields', 'warning'); return;
    }

    showLoading(true);
    const payload = { item, amount, category, date };
    const method = id ? 'PUT' : 'POST';
    const url = id ? `${API_URL}/expenses/${id}` : `${API_URL}/expenses`;

    try {
        await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        expenseModal.hide();
        showToast('Saved', 'success');
        refreshAll();
    } catch (e) {
        showToast('Error', 'danger');
    } finally {
        showLoading(false);
    }
}

async function deleteExpense(id) {
    if (!confirm('Delete?')) return;
    showLoading(true);
    try {
        await fetch(`${API_URL}/expenses/${id}`, { method: 'DELETE' });
        showToast('Deleted', 'success');
        refreshAll();
    } catch (e) { showToast('Error', 'danger'); }
    finally { showLoading(false); }
}

async function confirmClearAll() {
    if (!confirm('WARNING: ERASE ALL?')) return;
    showLoading(true);
    try {
        await fetch(`${API_URL}/expenses`, { method: 'DELETE' });
        refreshAll();
    } catch (e) { showToast('Error', 'danger'); }
    finally { showLoading(false); }
}

function showLoading(show) {
    const el = document.getElementById('loadingOverlay');
    if (el) el.style.display = show ? 'flex' : 'none';
}

function showToast(msg, type = 'primary') {
    const container = document.getElementById('toastContainer');
    const id = 'toast_' + Date.now();
    const html = `
        <div id="${id}" class="toast align-items-center text-white bg-${type} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">${msg}</div>
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
