from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
from datetime import datetime
import os
import io
import sys
import logging
import traceback
from pymongo import MongoClient, DESCENDING, ASCENDING
from bson.objectid import ObjectId
from dotenv import load_dotenv
import openpyxl

# Load environment variables
# Load environment variables
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
    env_path = os.path.join(base_dir, '.env')
else:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(base_dir, '.env')

load_dotenv(env_path)

# --- Logging Setup ---
if getattr(sys, 'frozen', False):
    app_dir = os.path.dirname(sys.executable)
else:
    app_dir = os.path.dirname(os.path.abspath(__file__))

log_file = os.path.join(app_dir, 'debug.log')
logging.basicConfig(
    filename=log_file,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logging.info("Starting Application (MongoDB Version)...")

# --- Path Helpers ---
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

if getattr(sys, 'frozen', False):
    template_dir = resource_path('templates')
    static_dir = resource_path('static')
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(base_dir, '..', 'frontend', 'templates')
    static_dir = os.path.join(base_dir, '..', 'static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
CORS(app)

# --- Database Setup ---
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI or "YOUR_PASSWORD_HERE" in MONGO_URI:
    logging.warning("MONGO_URI not set or contains placeholder. Database connection may fail.")

try:
    client = MongoClient(MONGO_URI)
    db = client.get_database("expenses_tracker")
    # Test connection
    client.server_info()
    logging.info("Connected to MongoDB via pymongo")
except Exception as e:
    logging.critical(f"Failed to connect to MongoDB: {e}")
    # We continue, but routes will likely fail

expenses_col = db.expenses
summary_col = db.monthly_summary
categories_col = db.categories

# --- Helper ---
def serialize_doc(doc):
    if not doc: return None
    doc['id'] = str(doc['_id'])
    del doc['_id']
    return doc

# --- Seeding ---
try:
    if categories_col.count_documents({}) == 0:
        defaults = ["General", "Food & Dining", "Groceries", "Transportation", "Utilities", "Entertainment", "Health", "Shopping", "Other"]
        categories_col.insert_many([{"name": d} for d in defaults])
        logging.info("Seeded default categories")
except Exception as e:
    logging.error(f"Seeding failed: {e}")

# --- Routes ---

@app.route('/')
def home():
    return render_template('dashboard.html')

@app.route('/dashboard-stats', methods=['GET'])
def dashboard_stats():
    target_month = request.args.get('month')
    if not target_month:
        target_month = datetime.now().strftime("%b %Y")

    # Current Salary
    curr_summary = summary_col.find_one({"month": target_month})
    current_salary = curr_summary['salary'] if curr_summary else 0.0

    # Current Expenses
    pipeline = [
        {"$match": {"month": target_month}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    res = list(expenses_col.aggregate(pipeline))
    current_expenses = res[0]['total'] if res else 0.0

    # Previous Balance logic
    # Fetch all summaries and aggregated expenses
    all_salaries = list(summary_col.find({}))
    salary_map = {s['month']: s.get('salary', 0.0) for s in all_salaries}

    exp_pipeline = [
        {"$group": {"_id": "$month", "total": {"$sum": "$amount"}}}
    ]
    all_expenses = list(expenses_col.aggregate(exp_pipeline))
    expense_map = {e['_id']: e['total'] for e in all_expenses}

    try:
        target_date_obj = datetime.strptime(target_month, "%b %Y")
    except:
        target_date_obj = datetime.now()

    previous_balance = 0.0
    all_months = set(list(salary_map.keys()) + list(expense_map.keys()))

    for m_str in all_months:
        if not m_str: continue 
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
    
    pipeline = [
        {"$match": {"month": month}},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}
    ]
    results = list(expenses_col.aggregate(pipeline))
    data = { (r['_id'] or 'General'): r['total'] for r in results }
    return jsonify(data)

@app.route('/salary', methods=['POST'])
def set_salary():
    data = request.json
    month = data.get('month')
    amount = data.get('amount')
    if not month or amount is None: return jsonify({"error": "Missing data"}), 400
    
    res = summary_col.update_one(
        {"month": month},
        {"$set": {"salary": float(amount)}},
        upsert=True
    )
    
    return jsonify({"month": month, "salary": float(amount)})

@app.route('/expenses', methods=['GET'])
def get_expenses():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 50, type=int)
    month_filter = request.args.get('month')
    search = request.args.get('search')
    category = request.args.get('category')

    query = {}
    if month_filter:
        query["month"] = month_filter
    if search:
        query["item"] = {"$regex": search, "$options": "i"}
    if category and category != 'All':
        query["category"] = category

    total = expenses_col.count_documents(query)
    
    # Sort by date desc, then _id desc (using _id as proxy for creation time if needed, or stick to natural)
    # The original was: order_by(Expense.date.desc(), Expense.id.desc())
    cursor = expenses_col.find(query).sort([("date", DESCENDING), ("_id", DESCENDING)])
    cursor = cursor.skip((page - 1) * limit).limit(limit)

    items = [serialize_doc(doc) for doc in cursor]

    has_next = (page * limit) < total

    return jsonify({
        "items": items,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit, # ceil division
        "has_next": has_next
    })

@app.route('/expenses', methods=['POST'])
def add_expense():
    data = request.json
    if not data or 'item' not in data or 'amount' not in data:
        return jsonify({"error": "Invalid data"}), 400
    
    # Date logic (reused)
    date_str = data.get('date')
    month_str = data.get('month')

    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except:
            d = None
            # Try other formats, keeping it simple here or copying full logic?
            # Let's trust the frontend sends YYYY-MM-DD or simple parsing
            for fmt in ["%d %m %Y", "%d-%m-%Y", "%d/%m/%Y"]:
                 try:
                     d = datetime.strptime(date_str, fmt)
                     date_str = d.strftime("%Y-%m-%d")
                     break
                 except: pass
        
        if d:
            month_str = d.strftime("%b %Y")
            data['date'] = date_str

    if not month_str:
         month_str = datetime.now().strftime("%b %Y")

    new_expense = {
        "item": data['item'],
        "amount": float(data['amount']),
        "month": month_str,
        "category": data.get('category', 'General'),
        "date": date_str
    }
    
    res = expenses_col.insert_one(new_expense)
    return jsonify(serialize_doc(expenses_col.find_one({"_id": res.inserted_id}))), 201

@app.route('/expenses/<id>', methods=['PUT', 'DELETE'])
def expense_op(id):
    # Consolidating for brevity handling _id lookup
    try:
        oid = ObjectId(id)
    except:
        return jsonify({"error": "Invalid ID"}), 400

    if request.method == 'DELETE':
        res = expenses_col.delete_one({"_id": oid})
        if res.deleted_count == 0: return jsonify({"error": "Not found"}), 404
        return jsonify({"message": "Deleted"})
    
    elif request.method == 'PUT':
        data = request.json
        update_fields = {}
        if 'item' in data: update_fields['item'] = data['item']
        if 'amount' in data: update_fields['amount'] = float(data['amount'])
        if 'category' in data: update_fields['category'] = data['category']
        
        # Date update logic
        if 'date' in data:
            date_str = data['date']
            update_fields['date'] = date_str
            # Try to update month too
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d")
                update_fields['month'] = d.strftime("%b %Y")
            except:
                pass # Parse failures handled loosely as before

        expenses_col.update_one({"_id": oid}, {"$set": update_fields})
        return jsonify(serialize_doc(expenses_col.find_one({"_id": oid})))

@app.route('/expenses', methods=['DELETE']) # Clear all
def clear_expenses():
    try:
        expenses_col.delete_many({})
        summary_col.delete_many({})
        return jsonify({"message": "All data deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/export', methods=['GET'])
def export_excel():
    month_filter = request.args.get('month')
    query = {}
    if month_filter:
        query["month"] = month_filter
        
    expenses = list(expenses_col.find(query).sort("date", DESCENDING))
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Expenses"
    ws.append(["ID", "Date", "Item", "Category", "Amount", "Month"])
    
    for e in expenses:
        ws.append([str(e['_id']), e.get('date', ''), e.get('item'), e.get('category', 'General'), e.get('amount'), e.get('month')])
        
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    
    filename = f"Expenses_{month_filter}.xlsx" if month_filter else "All_Expenses.xlsx"
    return send_file(out, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=filename)


@app.route('/categories', methods=['GET'])
def get_categories():
    cats = list(categories_col.find().sort("name", ASCENDING))
    return jsonify([serialize_doc(c) for c in cats])

@app.route('/categories', methods=['POST'])
def add_category():
    data = request.json
    name = data.get('name', '').strip()
    if not name: return jsonify({"error": "Missing name"}), 400
    
    if categories_col.find_one({"name": name}):
        return jsonify({"error": "Exists"}), 400
        
    res = categories_col.insert_one({"name": name})
    return jsonify({"id": str(res.inserted_id), "name": name}), 201

@app.route('/categories/<id>', methods=['DELETE'])
def delete_category(id):
    try:
        oid = ObjectId(id)
        categories_col.delete_one({"_id": oid})
        return jsonify({"message": "Deleted"})
    except:
        return jsonify({"error": "Invalid ID"}), 400

if __name__ == '__main__':
    logging.info("Starting Server...")
    try:
        import threading
        
        def run_flask():
            app.run(debug=False, host='127.0.0.1', port=8000, use_reloader=False)

        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        # PyQt5 App
        from PyQt5.QtWidgets import QApplication, QMainWindow
        from PyQt5.QtWebEngineWidgets import QWebEngineView
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QIcon

        qt_app = QApplication( sys.argv)
        qt_app.setApplicationName("Padharia Expense Tracker")

        class MainWindow(QMainWindow):
            def __init__(self):
                super().__init__()
                self.setWindowTitle("Padharia Expense Tracker")
                self.resize(1200, 800)
                icon_path = resource_path(os.path.join('static', 'rupee.ico'))
                self.setWindowIcon(QIcon(icon_path))
                
                self.browser = QWebEngineView()
                self.browser.setUrl(QUrl("http://127.0.0.1:8000"))
                self.setCentralWidget(self.browser)
                
                # Handle Downloads
                self.browser.page().profile().downloadRequested.connect(self.on_download_requested)

            def on_download_requested(self, download):
                from PyQt5.QtWidgets import QFileDialog
                
                # Propose filename
                suggested_filename = download.suggestedFileName()
                
                # Open Save Dialog
                path, _ = QFileDialog.getSaveFileName(self, "Save File", suggested_filename, "Excel Files (*.xlsx);;All Files (*)")
                
                if path:
                    download.setPath(path)
                    download.accept()
                else:
                    download.cancel()

        window = MainWindow()
        window.show()
        logging.info("PyQt5 Window Launched")
        sys.exit(qt_app.exec_())

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        logging.critical(f"Server crash: {e}")
        logging.critical(traceback.format_exc())
        sys.exit(1)
