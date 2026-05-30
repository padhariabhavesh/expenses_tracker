from flask import Flask, request, jsonify, send_file, render_template, session, redirect, url_for
from flask_cors import CORS
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
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

import re

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(32))

# Allow localhost and any local network subnet (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
local_origin_re = re.compile(r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+)(:\d+)?$")
CORS(app, resources={r"/*": {"origins": [local_origin_re]}},
     supports_credentials=True)

# --- Database Setup ---
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI or "YOUR_PASSWORD_HERE" in MONGO_URI:
    logging.warning("MONGO_URI not set or contains placeholder. Database connection may fail.")

client = None
db = None
expenses_col = None
summary_col = None
categories_col = None
users_col = None

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client.get_database("expenses_tracker")
    client.server_info()
    expenses_col = db.expenses
    summary_col = db.monthly_summary
    categories_col = db.categories
    users_col = db.users
    # Ensure unique index on email
    users_col.create_index("email", unique=True)
    users_col.create_index("username", unique=True)
    logging.info("Connected to MongoDB via pymongo")
except Exception as e:
    logging.critical(f"Failed to connect to MongoDB: {e}")


def _db_ready():
    """Return True if the database collections are available."""
    return expenses_col is not None


# --- Helpers ---
def serialize_doc(doc):
    if not doc:
        return None
    doc['id'] = str(doc['_id'])
    del doc['_id']
    return doc


def current_user_id():
    """Return the logged-in user's ID string, or None."""
    return session.get('user_id')


def current_user_role():
    """Return the logged-in user's role, or None."""
    return session.get('role')


def is_admin():
    return current_user_role() == 'admin'


# --- Auth Decorators ---
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user_id():
            # API vs page request
            if request.is_json or request.path.startswith('/api'):
                return jsonify({"error": "Unauthorized", "redirect": "/login"}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user_id():
            return redirect(url_for('login_page'))
        if not is_admin():
            return jsonify({"error": "Forbidden — admin only"}), 403
        return f(*args, **kwargs)
    return decorated


# --- Seeding ---
try:
    if categories_col is not None and categories_col.count_documents({}) == 0:
        defaults = ["General", "Food & Dining", "Groceries", "Transportation",
                    "Utilities", "Entertainment", "Health", "Shopping", "Other"]
        categories_col.insert_many([{"name": d} for d in defaults])
        logging.info("Seeded default categories")
except Exception as e:
    logging.error(f"Seeding failed: {e}")


# ─────────────────────────────────────────────
#  PAGE ROUTES
# ─────────────────────────────────────────────

@app.route('/')
def home():
    if not current_user_id():
        return redirect(url_for('login_page'))
    return render_template('dashboard.html')


@app.route('/login')
def login_page():
    if current_user_id():
        return redirect(url_for('home'))
    return render_template('login.html')


@app.route('/register')
def register_page():
    if current_user_id():
        return redirect(url_for('home'))
    return render_template('register.html')


@app.route('/admin')
@admin_required
def admin_page():
    return render_template('admin.html')


# Fix #3: heartbeat
@app.route('/heartbeat', methods=['POST', 'GET'])
def heartbeat():
    return jsonify({"status": "ok"})


# ─────────────────────────────────────────────
#  AUTH API ROUTES
# ─────────────────────────────────────────────

@app.route('/auth/register', methods=['POST'])
def auth_register():
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503

    data = request.json
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    username = (data.get('username') or '').strip()
    email    = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not username or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if '@' not in email:
        return jsonify({"error": "Invalid email address"}), 400

    # First user ever → admin
    role = 'admin' if users_col.count_documents({}) == 0 else 'user'

    try:
        result = users_col.insert_one({
            "username": username,
            "email": email,
            "password_hash": generate_password_hash(password),
            "role": role,
            "is_active": True,
            "created_at": datetime.utcnow()
        })
    except Exception as e:
        if "duplicate" in str(e).lower():
            return jsonify({"error": "Username or email already registered"}), 409
        logging.error(f"Register error: {e}")
        return jsonify({"error": "Registration failed"}), 500

    session['user_id'] = str(result.inserted_id)
    session['username'] = username
    session['role'] = role

    # ── Data migration for first admin ──────────────────────────────────────
    # If this is the first user (admin), claim all existing records that were
    # created before auth was added (they have no user_id field).
    migrated_expenses = 0
    migrated_salary   = 0
    if role == 'admin':
        uid_str = str(result.inserted_id)
        exp_res = expenses_col.update_many(
            {"user_id": {"$exists": False}},
            {"$set": {"user_id": uid_str}}
        )
        sal_res = summary_col.update_many(
            {"user_id": {"$exists": False}},
            {"$set": {"user_id": uid_str}}
        )
        migrated_expenses = exp_res.modified_count
        migrated_salary   = sal_res.modified_count
        if migrated_expenses or migrated_salary:
            logging.info(
                f"Migrated {migrated_expenses} expense(s) and "
                f"{migrated_salary} salary record(s) to admin '{username}'"
            )
    # ────────────────────────────────────────────────────────────────────────

    return jsonify({
        "message": "Registered successfully",
        "role": role,
        "username": username,
        "migrated_expenses": migrated_expenses,
        "migrated_salary_records": migrated_salary
    }), 201


@app.route('/auth/login', methods=['POST'])
def auth_login():
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503

    data = request.json
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    user = users_col.find_one({"username": username})
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({"error": "Invalid username or password"}), 401

    if not user.get('is_active', True):
        return jsonify({"error": "Account is deactivated. Contact admin."}), 403

    session['user_id'] = str(user['_id'])
    session['username'] = user['username']
    session['role'] = user['role']
    logging.info(f"User logged in: {username}")
    return jsonify({
        "message": "Login successful",
        "username": user['username'],
        "role": user['role']
    })


@app.route('/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({"message": "Logged out"})


@app.route('/auth/me', methods=['GET'])
@login_required
def auth_me():
    return jsonify({
        "user_id": current_user_id(),
        "username": session.get('username'),
        "role": current_user_role()
    })


# ─────────────────────────────────────────────
#  ADMIN API ROUTES
# ─────────────────────────────────────────────

@app.route('/admin/stats', methods=['GET'])
@admin_required
def admin_stats():
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503

    total_users   = users_col.count_documents({})
    active_users  = users_col.count_documents({"is_active": True})
    total_expenses = expenses_col.count_documents({})

    amt_pipeline = [{"$group": {"_id": None, "total": {"$sum": "$amount"}}}]
    amt_result = list(expenses_col.aggregate(amt_pipeline))
    total_amount = amt_result[0]['total'] if amt_result else 0.0

    return jsonify({
        "total_users": total_users,
        "active_users": active_users,
        "total_expenses": total_expenses,
        "total_amount": total_amount
    })


@app.route('/admin/users', methods=['GET'])
@admin_required
def admin_list_users():
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503

    users = list(users_col.find({}).sort("created_at", ASCENDING))
    result = []
    for u in users:
        uid_str = str(u['_id'])
        exp_count = expenses_col.count_documents({"user_id": uid_str})
        result.append({
            "id": uid_str,
            "username": u.get('username'),
            "email": u.get('email'),
            "role": u.get('role', 'user'),
            "is_active": u.get('is_active', True),
            "created_at": u.get('created_at', '').isoformat() if u.get('created_at') else '',
            "expense_count": exp_count
        })
    return jsonify(result)


@app.route('/admin/users/<uid>', methods=['PUT'])
@admin_required
def admin_update_user(uid):
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503

    try:
        oid = ObjectId(uid)
    except Exception:
        return jsonify({"error": "Invalid user ID"}), 400

    # Prevent admin from demoting themselves
    if uid == current_user_id() and request.json.get('role') == 'user':
        return jsonify({"error": "You cannot remove your own admin role"}), 400

    data = request.json or {}
    update = {}
    if 'role' in data and data['role'] in ('admin', 'user'):
        update['role'] = data['role']
    if 'is_active' in data:
        update['is_active'] = bool(data['is_active'])

    if not update:
        return jsonify({"error": "Nothing to update"}), 400

    users_col.update_one({"_id": oid}, {"$set": update})
    return jsonify({"message": "User updated"})


@app.route('/admin/users/<uid>', methods=['DELETE'])
@admin_required
def admin_delete_user(uid):
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503

    if uid == current_user_id():
        return jsonify({"error": "You cannot delete your own account"}), 400

    try:
        oid = ObjectId(uid)
    except Exception:
        return jsonify({"error": "Invalid user ID"}), 400

    users_col.delete_one({"_id": oid})
    # Also delete their expenses and salary
    expenses_col.delete_many({"user_id": uid})
    summary_col.delete_many({"user_id": uid})
    return jsonify({"message": "User and their data deleted"})


# ─────────────────────────────────────────────
#  DASHBOARD STATS
# ─────────────────────────────────────────────

@app.route('/dashboard-stats', methods=['GET'])
@login_required
def dashboard_stats():
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503

    uid = current_user_id()
    target_month = request.args.get('month')
    if not target_month:
        target_month = datetime.now().strftime("%b %Y")

    user_filter = {} if is_admin() else {"user_id": uid}

    # Current Salary
    salary_filter = {"month": target_month, **({} if is_admin() else {"user_id": uid})}
    curr_summary = summary_col.find_one(salary_filter)
    current_salary = curr_summary['salary'] if curr_summary else 0.0

    # Current Expenses
    exp_match = {"month": target_month, **user_filter}
    pipeline = [
        {"$match": exp_match},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    res = list(expenses_col.aggregate(pipeline))
    current_expenses = res[0]['total'] if res else 0.0

    # Previous Balance
    all_salaries = list(summary_col.find({} if is_admin() else {"user_id": uid}))
    salary_map = {s['month']: s.get('salary', 0.0) for s in all_salaries}

    exp_pipeline = [
        {"$match": user_filter},
        {"$group": {"_id": "$month", "total": {"$sum": "$amount"}}}
    ]
    all_expenses_agg = list(expenses_col.aggregate(exp_pipeline))
    expense_map = {e['_id']: e['total'] for e in all_expenses_agg}

    try:
        target_date_obj = datetime.strptime(target_month, "%b %Y")
    except ValueError:
        target_date_obj = datetime.now()

    previous_balance = 0.0
    all_months = set(list(salary_map.keys()) + list(expense_map.keys()))

    for m_str in all_months:
        if not m_str:
            continue
        try:
            m_date = datetime.strptime(m_str, "%b %Y")
            if m_date < target_date_obj:
                previous_balance += salary_map.get(m_str, 0.0) - expense_map.get(m_str, 0.0)
        except ValueError:
            logging.warning(f"Skipping malformed month string: '{m_str}'")
            continue

    total_available   = previous_balance + current_salary
    remaining_balance = total_available - current_expenses

    def _safe_month_key(m_str):
        try:
            return datetime.strptime(m_str, "%b %Y") if m_str else datetime.min
        except ValueError:
            return datetime.min

    available_months_set = sorted(list(all_months), key=_safe_month_key, reverse=True)

    return jsonify({
        "current_filter":   target_month,
        "salary":           current_salary,
        "previous_balance": previous_balance,
        "current_expenses": current_expenses,
        "total_available":  total_available,
        "remaining_balance": remaining_balance,
        "available_months": available_months_set
    })


@app.route('/stats/category', methods=['GET'])
@login_required
def category_stats():
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503

    uid = current_user_id()
    month = request.args.get('month') or datetime.now().strftime("%b %Y")
    user_filter = {} if is_admin() else {"user_id": uid}

    pipeline = [
        {"$match": {"month": month, **user_filter}},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}
    ]
    results = list(expenses_col.aggregate(pipeline))
    data = {(r['_id'] or 'General'): r['total'] for r in results}
    return jsonify(data)


# ─────────────────────────────────────────────
#  SALARY
# ─────────────────────────────────────────────

@app.route('/salary', methods=['POST'])
@login_required
def set_salary():
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503

    data = request.json
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    month  = data.get('month')
    amount = data.get('amount')
    if not month or amount is None:
        return jsonify({"error": "Missing data"}), 400

    try:
        amount_float = float(amount)
    except (ValueError, TypeError):
        return jsonify({"error": "amount must be a number"}), 400

    uid = current_user_id()
    summary_col.update_one(
        {"month": month, "user_id": uid},
        {"$set": {"salary": amount_float, "user_id": uid, "month": month}},
        upsert=True
    )
    return jsonify({"month": month, "salary": amount_float})


# ─────────────────────────────────────────────
#  EXPENSES
# ─────────────────────────────────────────────

@app.route('/expenses', methods=['GET'])
@login_required
def get_expenses():
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503

    uid  = current_user_id()
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 50, type=int)
    month_filter = request.args.get('month')
    search   = request.args.get('search')
    category = request.args.get('category')

    query = {} if is_admin() else {"user_id": uid}

    if month_filter:
        query["month"] = month_filter
    if search:
        query["item"] = {"$regex": search, "$options": "i"}
    if category and category != 'All':
        query["category"] = category

    total  = expenses_col.count_documents(query)
    cursor = expenses_col.find(query).sort([("date", DESCENDING), ("_id", DESCENDING)])
    cursor = cursor.skip((page - 1) * limit).limit(limit)
    items  = [serialize_doc(doc) for doc in cursor]
    has_next = (page * limit) < total

    return jsonify({
        "items": items,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
        "has_next": has_next
    })


@app.route('/expenses', methods=['POST'])
@login_required
def add_expense():
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503

    data = request.json
    if not data or 'item' not in data or 'amount' not in data:
        return jsonify({"error": "Invalid data"}), 400

    date_str  = data.get('date')
    month_str = data.get('month')

    if date_str:
        d = None
        for fmt in ["%Y-%m-%d", "%d %m %Y", "%d-%m-%Y", "%d/%m/%Y"]:
            try:
                d = datetime.strptime(date_str, fmt)
                date_str = d.strftime("%Y-%m-%d")
                break
            except ValueError:
                pass
        if d is None:
            return jsonify({"error": f"Unrecognised date format: '{date_str}'"}), 400
        if d:
            month_str = d.strftime("%b %Y")
            data['date'] = date_str

    if not month_str:
        month_str = datetime.now().strftime("%b %Y")

    new_expense = {
        "user_id":  current_user_id(),
        "item":     data['item'],
        "amount":   float(data['amount']),
        "month":    month_str,
        "category": data.get('category', 'General'),
        "date":     date_str
    }

    res = expenses_col.insert_one(new_expense)
    return jsonify(serialize_doc(expenses_col.find_one({"_id": res.inserted_id}))), 201


@app.route('/expenses/<id>', methods=['PUT', 'DELETE'])
@login_required
def expense_op(id):
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503

    try:
        oid = ObjectId(id)
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400

    uid = current_user_id()
    # Admin can touch any expense; regular users only their own
    query = {"_id": oid} if is_admin() else {"_id": oid, "user_id": uid}

    if request.method == 'DELETE':
        res = expenses_col.delete_one(query)
        if res.deleted_count == 0:
            return jsonify({"error": "Not found or not authorised"}), 404
        return jsonify({"message": "Deleted"})

    elif request.method == 'PUT':
        data = request.json
        if not data:
            return jsonify({"error": "Missing JSON body"}), 400

        update_fields = {}
        if 'item' in data:
            update_fields['item'] = data['item']
        if 'amount' in data:
            try:
                update_fields['amount'] = float(data['amount'])
            except (ValueError, TypeError):
                return jsonify({"error": "amount must be a number"}), 400
        if 'category' in data:
            update_fields['category'] = data['category']

        if 'date' in data:
            date_str = data['date']
            d = None
            for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]:
                try:
                    d = datetime.strptime(date_str, fmt)
                    date_str = d.strftime("%Y-%m-%d")
                    break
                except ValueError:
                    pass
            if d:
                update_fields['date']  = date_str
                update_fields['month'] = d.strftime("%b %Y")
            else:
                return jsonify({"error": f"Unrecognised date format: '{date_str}'"}), 400

        expenses_col.update_one(query, {"$set": update_fields})
        return jsonify(serialize_doc(expenses_col.find_one({"_id": oid})))


@app.route('/expenses', methods=['DELETE'])
@login_required
def clear_expenses():
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503
    try:
        uid = current_user_id()
        if is_admin():
            expenses_col.delete_many({})
            summary_col.delete_many({})
        else:
            expenses_col.delete_many({"user_id": uid})
            summary_col.delete_many({"user_id": uid})
        return jsonify({"message": "All data deleted"})
    except Exception as e:
        logging.error(f"clear_expenses error: {e}")
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
#  EXPORT
# ─────────────────────────────────────────────

@app.route('/export', methods=['GET'])
@login_required
def export_excel():
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503

    uid = current_user_id()
    month_filter = request.args.get('month')
    query = {} if is_admin() else {"user_id": uid}
    if month_filter:
        query["month"] = month_filter

    expenses = list(expenses_col.find(query).sort("date", DESCENDING))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Expenses"
    ws.append(["ID", "Date", "Item", "Category", "Amount", "Month"])

    for e in expenses:
        ws.append([str(e['_id']), e.get('date', ''), e.get('item'),
                   e.get('category', 'General'), e.get('amount'), e.get('month')])

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)

    filename = f"Expenses_{month_filter}.xlsx" if month_filter else "All_Expenses.xlsx"
    return send_file(out,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=filename)


# ─────────────────────────────────────────────
#  CATEGORIES
# ─────────────────────────────────────────────

@app.route('/categories', methods=['GET'])
@login_required
def get_categories():
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503
    cats = list(categories_col.find().sort("name", ASCENDING))
    return jsonify([serialize_doc(c) for c in cats])


@app.route('/categories', methods=['POST'])
@login_required
def add_category():
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503
    data = request.json
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"error": "Missing name"}), 400
    if categories_col.find_one({"name": name}):
        return jsonify({"error": "Exists"}), 400
    res = categories_col.insert_one({"name": name})
    return jsonify({"id": str(res.inserted_id), "name": name}), 201


@app.route('/categories/<id>', methods=['DELETE'])
@login_required
def delete_category(id):
    if not _db_ready():
        return jsonify({"error": "Database not connected"}), 503
    try:
        oid = ObjectId(id)
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400

    cat_doc = categories_col.find_one({"_id": oid})
    if not cat_doc:
        return jsonify({"error": "Category not found"}), 404

    in_use_count = expenses_col.count_documents({"category": cat_doc["name"]})
    if in_use_count > 0:
        return jsonify({
            "error": f"Cannot delete: {in_use_count} expense(s) use this category. "
                     "Reassign or delete those expenses first."
        }), 409

    categories_col.delete_one({"_id": oid})
    return jsonify({"message": "Deleted"})


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == '__main__':
    logging.info("Starting Server...")
    try:
        import threading

        def run_flask():
            app.run(debug=False, host='0.0.0.0', port=8000, use_reloader=False)

        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        from PyQt5.QtWidgets import QApplication, QMainWindow
        from PyQt5.QtWebEngineWidgets import QWebEngineView
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QIcon

        qt_app = QApplication(sys.argv)
        qt_app.setApplicationName("Padharia Expense Tracker")

        class MainWindow(QMainWindow):
            def __init__(self):
                super().__init__()
                self.setWindowTitle("Padharia Expense Tracker")
                self.resize(1280, 860)
                icon_path = resource_path(os.path.join('static', 'rupee.ico'))
                self.setWindowIcon(QIcon(icon_path))

                self.browser = QWebEngineView()
                self.browser.setUrl(QUrl("http://127.0.0.1:8000"))
                self.setCentralWidget(self.browser)

                self.browser.page().profile().downloadRequested.connect(self.on_download_requested)

            def on_download_requested(self, download):
                from PyQt5.QtWidgets import QFileDialog
                suggested_filename = download.suggestedFileName()
                path, _ = QFileDialog.getSaveFileName(
                    self, "Save File", suggested_filename, "Excel Files (*.xlsx);;All Files (*)")
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
