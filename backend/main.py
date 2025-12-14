from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
from datetime import datetime
import os
import io
import sys
from models import db, Expense, MonthlySummary, Category
import openpyxl

import logging
import traceback

import logging
import traceback

# Determine correct directory for logs
if getattr(sys, 'frozen', False):
    # If .exe, write log next to .exe
    app_dir = os.path.dirname(sys.executable)
else:
    app_dir = os.path.dirname(os.path.abspath(__file__))

log_file = os.path.join(app_dir, 'debug.log')

print(f"Attempting to write logs to: {log_file}") # Console fallback

logging.basicConfig(
    filename=log_file,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logging.info("Starting Application...")

# PyInstaller Resource Helper
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
        logging.debug(f"Running in bundle mode: {base_path}")
    except Exception:
        base_path = os.path.abspath(".")
        logging.debug(f"Running in dev mode: {base_path}")

    path = os.path.join(base_path, relative_path)
    logging.debug(f"Resolved path for {relative_path}: {path}")
    return path

# Determine paths relative to where main.py is (backend/) or root if bundled
if getattr(sys, 'frozen', False):
    # Running as compiled exe
    template_dir = resource_path('templates')
    static_dir = resource_path('static')
else:
    # Running from source (backend/main.py)
    # templates are in ../frontend/templates
    # static is in ../static
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(base_dir, '..', 'frontend', 'templates')
    static_dir = os.path.join(base_dir, '..', 'static')

logging.info(f"Template Dir: {template_dir}")
logging.info(f"Static Dir: {static_dir}")

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expenses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

try:
    db.init_app(app)
    CORS(app)
    logging.info("Flask App Initialized")
except Exception as e:
    logging.error(f"Failed to init app: {e}")
    logging.error(traceback.format_exc())

with app.app_context():
    db.create_all()
    # Migration hack: Add 'date' column if missing
    try:
        with db.engine.connect() as conn:
            conn.execute(db.text("ALTER TABLE expense ADD COLUMN date VARCHAR(20)"))
    except Exception:
        pass # Already exists

    # Migration hack: Add 'category' column if missing
    try:
        with db.engine.connect() as conn:
            conn.execute(db.text("ALTER TABLE expense ADD COLUMN category VARCHAR(50) DEFAULT 'General'"))
    except Exception:
        pass # Already exists

    # Seed Default Categories
    if Category.query.count() == 0:
        defaults = ["General", "Food & Dining", "Groceries", "Transportation", "Utilities", "Entertainment", "Health", "Shopping", "Other"]
        for d in defaults:
            db.session.add(Category(name=d))
        db.session.commit()

@app.route('/')
def home():
    return render_template('dashboard.html')

@app.route('/dashboard-stats', methods=['GET'])
def dashboard_stats():
    target_month = request.args.get('month')
    if not target_month:
        now = datetime.now()
        target_month = now.strftime("%b %Y")

    current_salary_record = MonthlySummary.query.get(target_month)
    current_salary = current_salary_record.salary if current_salary_record else 0.0
    current_expenses = db.session.query(db.func.sum(Expense.amount)).filter(Expense.month == target_month).scalar() or 0.0

    # Previous Balance Calculation
    all_summaries = MonthlySummary.query.all()
    all_expenses = db.session.query(Expense.month, db.func.sum(Expense.amount)).group_by(Expense.month).all()
    expense_map = {e[0]: e[1] for e in all_expenses}
    salary_map = {s.month: s.salary for s in all_summaries}

    try:
        target_date_obj = datetime.strptime(target_month, "%b %Y")
    except:
        target_date_obj = datetime.now()

    previous_balance = 0.0
    all_months = set(list(expense_map.keys()) + list(salary_map.keys()))
    
    for m_str in all_months:
        try:
            m_date = datetime.strptime(m_str, "%b %Y")
            if m_date < target_date_obj:
                inc = salary_map.get(m_str, 0.0)
                exp = expense_map.get(m_str, 0.0)
                previous_balance += (inc - exp)
        except:
            continue

    total_available = previous_balance + current_salary
    remaining_balance = total_available - current_expenses
    
    available_months_set = sorted(list(all_months), key=lambda x: datetime.strptime(x, "%b %Y") if x else datetime.min, reverse=True)

    return jsonify({
        "current_filter": target_month,
        "salary": current_salary,
        "previous_balance": previous_balance,
        "current_expenses": current_expenses,
        "total_available": total_available,
        "remaining_balance": remaining_balance,
        "available_months": available_months_set
    })

@app.route('/stats/category', methods=['GET'])
def category_stats():
    month = request.args.get('month')
    if not month:
        month = datetime.now().strftime("%b %Y")
    
    # query sum by category
    results = db.session.query(Expense.category, db.func.sum(Expense.amount))\
        .filter(Expense.month == month)\
        .group_by(Expense.category).all()
        
    data = {r[0] or 'General': r[1] for r in results}
    return jsonify(data)

@app.route('/salary', methods=['POST'])
def set_salary():
    data = request.json
    month = data.get('month')
    amount = data.get('amount')
    if not month or amount is None: return jsonify({"error": "Missing data"}), 400
    summary = MonthlySummary.query.get(month)
    if not summary:
        summary = MonthlySummary(month=month, salary=float(amount))
        db.session.add(summary)
    else:
        summary.salary = float(amount)
    db.session.commit()
    return jsonify(summary.to_dict())

@app.route('/expenses', methods=['GET'])
def get_expenses():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 50, type=int)
    month_filter = request.args.get('month')
    search = request.args.get('search')
    category = request.args.get('category')

    # Sort by Date descending (if avail), then ID desc
    query = Expense.query.order_by(Expense.date.desc(), Expense.id.desc())
    
    if month_filter:
        query = query.filter(Expense.month == month_filter)
    
    if search:
        query = query.filter(Expense.item.ilike(f"%{search}%"))
        
    if category and category != 'All':
        query = query.filter(Expense.category == category)
    
    pagination = query.paginate(page=page, per_page=limit, error_out=False)
    
    return jsonify({
        "items": [e.to_dict() for e in pagination.items],
        "total": pagination.total,
        "page": page,
        "pages": pagination.pages,
        "has_next": pagination.has_next
    })

@app.route('/expenses', methods=['POST'])
def add_expense():
    data = request.json
    if not data or 'item' not in data or 'amount' not in data:
        return jsonify({"error": "Invalid data"}), 400
    
    # Logic: If date provided, derive month. Else default.
    date_str = data.get('date') # YYYY-MM-DD
    month_str = data.get('month') # Fallback

    if date_str:
        # Parse date to get month "Nov 2025"
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            month_str = d.strftime("%b %Y")
        except:
            pass # Keep what was passed or default logic below

    if not month_str:
        month_str = datetime.now().strftime("%b %Y")
        
    new_expense = Expense(
        item=data['item'],
        amount=float(data['amount']),
        month=month_str,
        category=data.get('category', 'General'),
        date=date_str
    )
    db.session.add(new_expense)
    db.session.commit()
    return jsonify(new_expense.to_dict()), 201

@app.route('/expenses/<int:id>', methods=['PUT'])
def update_expense(id):
    expense = Expense.query.get_or_404(id)
    data = request.json
    
    expense.item = data.get('item', expense.item)
    expense.amount = float(data.get('amount', expense.amount))
    expense.category = data.get('category', expense.category)
    
    # Date/Month Logic
    date_str = data.get('date')
    if date_str:
        expense.date = date_str
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            expense.month = d.strftime("%b %Y")
        except:
            pass
            
    db.session.commit()
    return jsonify(expense.to_dict())

@app.route('/expenses/<int:id>', methods=['DELETE'])
def delete_expense(id):
    expense = Expense.query.get_or_404(id)
    db.session.delete(expense)
    db.session.commit()
    return jsonify({"message": "Deleted"})

@app.route('/expenses', methods=['DELETE'])
def clear_expenses():
    try:
        db.session.query(Expense).delete()
        db.session.query(MonthlySummary).delete()
        db.session.commit()
        return jsonify({"message": "All data deleted"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/export', methods=['GET'])
def export_excel():
    month_filter = request.args.get('month')
    
    # Query Data
    query = Expense.query.order_by(Expense.date.desc())
    if month_filter:
        query = query.filter(Expense.month == month_filter)
    expenses = query.all()
    
    # Create Workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Expenses"
    
    # Header
    ws.append(["ID", "Date", "Item", "Category", "Amount", "Month"])
    
    # Rows
    for e in expenses:
        ws.append([e.id, e.date or "", e.item, e.category or "General", e.amount, e.month])
        
    # Stats Sheet
    ws_stats = wb.create_sheet("Summary")
    ws_stats.append(["Metric", "Value"])
    if month_filter:
        # Calculate stats for this month reused from logic?
        # For simplicity, let's just dump what we know
        pass
        
    # Save to Bytes
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    
    filename = f"Expenses_{month_filter}.xlsx" if month_filter else "All_Expenses.xlsx"
    
    return send_file(
        out,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )



@app.route('/categories', methods=['GET'])
def get_categories():
    files = Category.query.order_by(Category.name).all()
    return jsonify([f.to_dict() for f in files])

@app.route('/categories', methods=['POST'])
def add_category():
    data = request.json
    name = data.get('name', '').strip()
    if not name: return jsonify({"error": "Missing name"}), 400
    
    if Category.query.filter_by(name=name).first():
        return jsonify({"error": "Exists"}), 400
        
    cat = Category(name=name)
    db.session.add(cat)
    db.session.commit()
    return jsonify(cat.to_dict()), 201

@app.route('/categories/<int:id>', methods=['DELETE'])
def delete_category(id):
    cat = Category.query.get_or_404(id)
    db.session.delete(cat)
    db.session.commit()
    return jsonify({"message": "Deleted"})

# Auto-Shutdown Logic
import threading
import time

last_active_time = time.time()
shutdown_lock = threading.Lock()

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    global last_active_time
    with shutdown_lock:
        last_active_time = time.time()
    return jsonify({"status": "ok"})

def monitor_activity():
    """Checks for heartbeat. If no heartbeat for 5 seconds, shutdown."""
    logging.info("Activity Monitor Started")
    # Grace period for startup
    time.sleep(10) 
    
    while True:
        time.sleep(1)
        with shutdown_lock:
            # If > 5 seconds inactive
            elapsed = time.time() - last_active_time
            if elapsed > 5:
                logging.info(f"No heartbeat for {elapsed:.1f}s. Shutting down...")
                os._exit(0) # Force exit

if __name__ == '__main__':
    logging.info("Starting Server...")
    try:
        import webbrowser
        
        # Start Activity Monitor
        threading.Thread(target=monitor_activity, daemon=True).start()
        
        def open_browser():
            logging.info("Opening Browser...")
            webbrowser.open_new('http://127.0.0.1:8000')
            
        threading.Timer(1, open_browser).start()
        app.run(debug=False, host='127.0.0.1', port=8000)
    except Exception as e:
        logging.critical(f"Server crash: {e}")
        logging.critical(traceback.format_exc())
        input("Press Enter to exit...") # Keep window open to see error if console visible
