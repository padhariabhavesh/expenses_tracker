import os
import uuid
import sqlite3
import logging
from datetime import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("db_service")

def to_mongo_id(val):
    if isinstance(val, str) and ObjectId.is_valid(val):
        return ObjectId(val)
    return val

class DbService:
    def __init__(self, mongo_uri=None, sqlite_db_path="data/expenses.db"):
        self.mongo_uri = mongo_uri
        self.sqlite_db_path = sqlite_db_path
        self.client = None
        self.mongo_db = None
        self.is_online = False
        
        # Ensure SQLite data directory exists
        os.makedirs(os.path.dirname(self.sqlite_db_path), exist_ok=True)
        
        # Initialize SQLite database schema
        self._init_sqlite()
        
        # Try to connect to MongoDB
        self.connect_mongodb()
        
        # If online, attempt startup sync
        if self.is_online:
            try:
                self.sync_offline_data()
            except Exception as e:
                logger.error(f"Startup synchronization failed: {e}")

    def _init_sqlite(self):
        """Initializes the SQLite schema with synced flags for tracking local offline additions."""
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        
        # Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE,
                email TEXT UNIQUE,
                password_hash TEXT,
                role TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT,
                synced INTEGER DEFAULT 1
            )
        """)
        
        # Categories Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE,
                synced INTEGER DEFAULT 1
            )
        """)
        
        # Expenses Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                item TEXT,
                amount REAL,
                month TEXT,
                category TEXT,
                date TEXT,
                synced INTEGER DEFAULT 1
            )
        """)
        
        # Monthly Summary Table (Salary)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monthly_summary (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                month TEXT,
                salary REAL,
                synced INTEGER DEFAULT 1,
                UNIQUE(user_id, month)
            )
        """)

        # Migration to add UNIQUE constraint on (user_id, month) if not already present
        cursor.execute("PRAGMA index_list(monthly_summary)")
        indexes = cursor.fetchall()
        has_unique_user_month = False
        for idx in indexes:
            if idx[2] == 1:  # is unique index
                cursor.execute(f"PRAGMA index_info({idx[1]})")
                cols = [c[2] for c in cursor.fetchall()]
                if set(cols) == {"user_id", "month"}:
                    has_unique_user_month = True
                    break
        
        if not has_unique_user_month:
            logger.info("Migrating monthly_summary table to add UNIQUE(user_id, month)...")
            try:
                # Check if old table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='monthly_summary'")
                if cursor.fetchone():
                    cursor.execute("ALTER TABLE monthly_summary RENAME TO monthly_summary_old")
                    cursor.execute("""
                        CREATE TABLE monthly_summary (
                            id TEXT PRIMARY KEY,
                            user_id TEXT,
                            month TEXT,
                            salary REAL,
                            synced INTEGER DEFAULT 1,
                            UNIQUE(user_id, month)
                        )
                    """)
                    # Copy data, grouping by user_id and month to eliminate duplicates
                    cursor.execute("""
                        INSERT OR REPLACE INTO monthly_summary (id, user_id, month, salary, synced)
                        SELECT id, user_id, month, salary, synced FROM monthly_summary_old
                        GROUP BY user_id, month
                    """)
                    cursor.execute("DROP TABLE monthly_summary_old")
                    logger.info("monthly_summary table migration successful.")
            except Exception as e:
                logger.error(f"Failed to migrate monthly_summary table: {e}")
        
        conn.commit()
        conn.close()
        logger.info("Local SQLite schema verified.")

    def connect_mongodb(self):
        """Attempts connection to MongoDB. Reverts to offline SQLite mode if connection fails."""
        if not self.mongo_uri or "YOUR_PASSWORD_HERE" in self.mongo_uri:
            logger.warning("No valid MongoDB URI configured. Running in local SQLite mode.")
            self.is_online = False
            return False

        try:
            logger.info("Attempting connection to MongoDB Atlas...")
            self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=3000)
            # Use database from URI if specified, otherwise default to "expenses_tracker"
            try:
                self.mongo_db = self.client.get_default_database()
            except Exception:
                self.mongo_db = self.client.get_database("expenses_tracker")
            # Check connection
            self.client.server_info()
            self.is_online = True
            logger.info(f"Successfully connected to MongoDB Atlas (Online). Database: {self.mongo_db.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB Atlas: {e}. Defaulting to SQLite (Offline).")
            self.client = None
            self.mongo_db = None
            self.is_online = False
            return False

    def sync_offline_data(self):
        """Synchronizes unsynced local SQLite data to MongoDB and toggles the sync flag."""
        if not self.is_online or self.mongo_db is None:
            return False

        logger.info("Starting synchronization of offline records...")
        conn = sqlite3.connect(self.sqlite_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. Sync Users
        cursor.execute("SELECT * FROM users WHERE synced = 0")
        users = cursor.fetchall()
        for u in users:
            user_doc = dict(u)
            del user_doc['synced']
            user_doc['_id'] = u['id']
            if 'id' in user_doc:
                del user_doc['id']
            if 'is_active' in user_doc:
                user_doc['is_active'] = bool(user_doc['is_active'])
            if 'created_at' in user_doc and isinstance(user_doc['created_at'], str):
                try:
                    user_doc['created_at'] = datetime.fromisoformat(user_doc['created_at'])
                except Exception:
                    pass
            self.mongo_db.users.replace_one({"_id": to_mongo_id(u['id'])}, user_doc, upsert=True)
            cursor.execute("UPDATE users SET synced = 1 WHERE id = ?", (u['id'],))

        # 2. Sync Categories
        cursor.execute("SELECT * FROM categories WHERE synced = 0")
        categories = cursor.fetchall()
        for c in categories:
            cat_doc = dict(c)
            del cat_doc['synced']
            cat_doc['_id'] = c['id']
            if 'id' in cat_doc:
                del cat_doc['id']
            self.mongo_db.categories.replace_one({"_id": to_mongo_id(c['id'])}, cat_doc, upsert=True)
            cursor.execute("UPDATE categories SET synced = 1 WHERE id = ?", (c['id'],))

        # 3. Sync Salaries
        cursor.execute("SELECT * FROM monthly_summary WHERE synced = 0")
        salaries = cursor.fetchall()
        for s in salaries:
            sal_doc = dict(s)
            del sal_doc['synced']
            if 'id' in sal_doc:
                del sal_doc['id']
            sal_doc['salary'] = float(sal_doc['salary'])
            # Check for existing document in MongoDB by month/user_id to prevent duplicates
            existing = self.mongo_db.monthly_summary.find_one({"month": s['month'], "user_id": s['user_id']})
            if existing:
                existing_id = str(existing['_id'])
                self.mongo_db.monthly_summary.update_one(
                    {"_id": existing['_id']},
                    {"$set": {"salary": sal_doc['salary']}}
                )
                if s['id'] != existing_id:
                    cursor.execute("UPDATE monthly_summary SET id = ?, synced = 1 WHERE id = ?", (existing_id, s['id']))
                else:
                    cursor.execute("UPDATE monthly_summary SET synced = 1 WHERE id = ?", (s['id'],))
            else:
                sal_doc['_id'] = s['id']
                self.mongo_db.monthly_summary.replace_one({"_id": to_mongo_id(s['id'])}, sal_doc, upsert=True)
                cursor.execute("UPDATE monthly_summary SET synced = 1 WHERE id = ?", (s['id'],))

        # 4. Sync Expenses
        cursor.execute("SELECT * FROM expenses WHERE synced = 0")
        expenses = cursor.fetchall()
        for e in expenses:
            exp_doc = dict(e)
            del exp_doc['synced']
            exp_doc['_id'] = e['id']
            if 'id' in exp_doc:
                del exp_doc['id']
            exp_doc['amount'] = float(exp_doc['amount'])
            self.mongo_db.expenses.replace_one({"_id": to_mongo_id(e['id'])}, exp_doc, upsert=True)
            cursor.execute("UPDATE expenses SET synced = 1 WHERE id = ?", (e['id'],))

        conn.commit()
        conn.close()
        logger.info("Synchronization complete.")
        return True

    def sync_down_user_data(self, user_id):
        """Downloads/caches all data for the given user from MongoDB Atlas to local SQLite."""
        if not self.is_online or self.mongo_db is None:
            return False

        logger.info(f"Syncing down data from MongoDB Atlas for user: {user_id}")
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()

        try:
            # 1. Sync User Document
            user_doc = self.mongo_db.users.find_one({"_id": to_mongo_id(user_id)})
            if user_doc:
                uid = str(user_doc['_id'])
                cursor.execute("""
                    INSERT OR REPLACE INTO users (id, username, email, password_hash, role, is_active, created_at, synced)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    uid,
                    user_doc.get('username'),
                    user_doc.get('email'),
                    user_doc.get('password_hash'),
                    user_doc.get('role', 'user'),
                    1 if user_doc.get('is_active', True) else 0,
                    user_doc.get('created_at').isoformat() if isinstance(user_doc.get('created_at'), datetime) else user_doc.get('created_at'),
                ))

            # 2. Sync Categories (Categories are global, not per-user)
            categories = list(self.mongo_db.categories.find())
            for c in categories:
                cid = str(c['_id'])
                cursor.execute("""
                    INSERT OR REPLACE INTO categories (id, name, synced)
                    VALUES (?, ?, 1)
                """, (cid, c.get('name')))

            # 3. Sync Salaries (monthly_summary)
            salaries = list(self.mongo_db.monthly_summary.find({"user_id": user_id}))
            for s in salaries:
                sid = str(s['_id'])
                cursor.execute("""
                    INSERT OR REPLACE INTO monthly_summary (id, user_id, month, salary, synced)
                    VALUES (?, ?, ?, ?, 1)
                """, (
                    sid,
                    user_id,
                    s.get('month'),
                    float(s.get('salary', 0.0))
                ))

            # 4. Sync Expenses
            expenses = list(self.mongo_db.expenses.find({"user_id": user_id}))
            for e in expenses:
                eid = str(e['_id'])
                cursor.execute("""
                    INSERT OR REPLACE INTO expenses (id, user_id, item, amount, category, date, month, synced)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    eid,
                    user_id,
                    e.get('item'),
                    float(e.get('amount', 0.0)),
                    e.get('category', 'General'),
                    e.get('date'),
                    e.get('month')
                ))

            conn.commit()
            logger.info("Sync down completed successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to sync down user data: {e}")
            self.is_online = False
            return False
        finally:
            conn.close()

    # ──────────────────────────────────────────────────────────────────────────
    #  USERS CRUD
    # ──────────────────────────────────────────────────────────────────────────

    def get_user_by_username(self, username):
        if self.is_online and self.mongo_db is not None:
            try:
                doc = self.mongo_db.users.find_one({"username": username})
                if doc:
                    doc['id'] = str(doc['_id'])
                return doc
            except Exception as e:
                logger.error(f"Mongo get_user_by_username failed: {e}")
                self.is_online = False
        
        # SQLite
        conn = sqlite3.connect(self.sqlite_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_user_by_email(self, email):
        if self.is_online and self.mongo_db is not None:
            try:
                doc = self.mongo_db.users.find_one({"email": email.lower()})
                if doc:
                    doc['id'] = str(doc['_id'])
                return doc
            except Exception as e:
                logger.error(f"Mongo get_user_by_email failed: {e}")
                self.is_online = False
        
        conn = sqlite3.connect(self.sqlite_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE LOWER(email) = ?", (email.lower(),))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_user_by_id(self, uid):
        if self.is_online and self.mongo_db is not None:
            try:
                doc = self.mongo_db.users.find_one({"_id": to_mongo_id(uid)})
                if doc:
                    doc['id'] = str(doc['_id'])
                return doc
            except Exception as e:
                logger.error(f"Mongo get_user_by_id failed: {e}")
                self.is_online = False
        
        conn = sqlite3.connect(self.sqlite_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (uid,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def count_users(self):
        if self.is_online and self.mongo_db is not None:
            try:
                return self.mongo_db.users.count_documents({})
            except Exception as e:
                logger.error(f"Mongo count_users failed: {e}")
                self.is_online = False
        
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def count_active_users(self):
        if self.is_online and self.mongo_db is not None:
            try:
                return self.mongo_db.users.count_documents({"is_active": True})
            except Exception as e:
                logger.error(f"Mongo count_active_users failed: {e}")
                self.is_online = False
        
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def create_user(self, username, email, password_hash, role, is_active=True):
        uid = str(uuid.uuid4())
        created_at = datetime.utcnow()
        
        user_doc = {
            "id": uid,
            "username": username,
            "email": email.lower(),
            "password_hash": password_hash,
            "role": role,
            "is_active": is_active,
            "created_at": created_at.isoformat()
        }

        # Always save locally first for resilience
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (id, username, email, password_hash, role, is_active, created_at, synced)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """, (uid, username, email.lower(), password_hash, role, 1 if is_active else 0, created_at.isoformat()))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            raise Exception("Username or email already registered")
        conn.close()

        # Attempt Mongo save
        if self.is_online and self.mongo_db is not None:
            try:
                mongo_doc = dict(user_doc)
                mongo_doc['_id'] = uid
                mongo_doc['created_at'] = created_at
                if 'id' in mongo_doc:
                    del mongo_doc['id']
                self.mongo_db.users.insert_one(mongo_doc)
                
                # Mark as synced locally
                conn = sqlite3.connect(self.sqlite_db_path)
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET synced = 1 WHERE id = ?", (uid,))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Failed to sync user register: {e}")
                self.is_online = False
                
        return user_doc

    def list_users(self):
        if self.is_online and self.mongo_db is not None:
            try:
                docs = list(self.mongo_db.users.find({}).sort("created_at", 1))
                users = []
                for d in docs:
                    d['id'] = str(d['_id'])
                    del d['_id']
                    d['created_at'] = d['created_at'].isoformat() if isinstance(d.get('created_at'), datetime) else d.get('created_at')
                    users.append(d)
                return users
            except Exception as e:
                logger.error(f"Mongo list_users failed: {e}")
                self.is_online = False

        conn = sqlite3.connect(self.sqlite_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users ORDER BY created_at ASC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_user(self, uid, update_fields):
        # Update SQLite locally first
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        set_clause = []
        params = []
        for k, v in update_fields.items():
            if k == 'is_active':
                set_clause.append("is_active = ?")
                params.append(1 if v else 0)
            elif k in ('role',):
                set_clause.append(f"{k} = ?")
                params.append(v)
        
        if set_clause:
            set_clause.append("synced = 0")
            params.append(uid)
            query = f"UPDATE users SET {', '.join(set_clause)} WHERE id = ?"
            cursor.execute(query, params)
            conn.commit()
        conn.close()

        # Sync MongoDB
        if self.is_online and self.mongo_db is not None:
            try:
                self.mongo_db.users.update_one({"_id": to_mongo_id(uid)}, {"$set": update_fields})
                conn = sqlite3.connect(self.sqlite_db_path)
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET synced = 1 WHERE id = ?", (uid,))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Failed to sync user update: {e}")
                self.is_online = False
        return True

    def delete_user(self, uid):
        # Delete locally
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?", (uid,))
        cursor.execute("DELETE FROM expenses WHERE user_id = ?", (uid,))
        cursor.execute("DELETE FROM monthly_summary WHERE user_id = ?", (uid,))
        conn.commit()
        conn.close()

        # Delete from MongoDB
        if self.is_online and self.mongo_db is not None:
            try:
                self.mongo_db.users.delete_one({"_id": to_mongo_id(uid)})
                self.mongo_db.expenses.delete_many({"user_id": uid})
                self.mongo_db.monthly_summary.delete_many({"user_id": uid})
            except Exception as e:
                logger.error(f"Failed to sync user deletion: {e}")
                self.is_online = False
        return True

    def reset_password(self, username, email, new_password_hash):
        """Resets user password if username and email match."""
        user = self.get_user_by_username(username)
        if not user or user.get('email', '').lower() != email.lower():
            return False

        uid = user['id']
        # Update SQLite locally
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password_hash = ?, synced = 0 WHERE id = ?", (new_password_hash, uid))
        conn.commit()
        conn.close()

        # Update MongoDB
        if self.is_online and self.mongo_db is not None:
            try:
                self.mongo_db.users.update_one({"_id": to_mongo_id(uid)}, {"$set": {"password_hash": new_password_hash}})
                conn = sqlite3.connect(self.sqlite_db_path)
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET synced = 1 WHERE id = ?", (uid,))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Failed to sync password reset: {e}")
                self.is_online = False
        return True

    # ──────────────────────────────────────────────────────────────────────────
    #  EXPENSES CRUD (Isolate strictly to user_id)
    # ──────────────────────────────────────────────────────────────────────────

    def get_expenses_count(self, user_id=None):
        query = {}
        if user_id:
            query["user_id"] = user_id
            
        if self.is_online and self.mongo_db is not None:
            try:
                return self.mongo_db.expenses.count_documents(query)
            except Exception as e:
                logger.error(f"Mongo get_expenses_count failed: {e}")
                self.is_online = False
        
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        if user_id:
            cursor.execute("SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,))
        else:
            cursor.execute("SELECT COUNT(*) FROM expenses")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_expenses_total_amount(self):
        if self.is_online and self.mongo_db is not None:
            try:
                amt_pipeline = [{"$group": {"_id": None, "total": {"$sum": "$amount"}}}]
                amt_result = list(self.mongo_db.expenses.aggregate(amt_pipeline))
                return amt_result[0]['total'] if amt_result else 0.0
            except Exception as e:
                logger.error(f"Mongo get_expenses_total_amount failed: {e}")
                self.is_online = False

        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(amount) FROM expenses")
        res = cursor.fetchone()[0]
        conn.close()
        return res if res else 0.0

    def query_expenses(self, user_id, month=None, search=None, category=None, skip=0, limit=50):
        """Returns isolated, parsed list of expenses matching filter params."""
        # Clean local rows format
        def _parse_row(r):
            d = dict(r)
            d['amount'] = float(d['amount'])
            return d

        if self.is_online and self.mongo_db is not None:
            try:
                query = {"user_id": user_id}
                if month:
                    query["month"] = month
                if search:
                    query["item"] = {"$regex": search, "$options": "i"}
                if category and category != 'All':
                    query["category"] = category

                cursor = self.mongo_db.expenses.find(query).sort([("date", -1), ("_id", -1)])
                total = self.mongo_db.expenses.count_documents(query)
                cursor = cursor.skip(skip).limit(limit)
                items = []
                for doc in cursor:
                    doc['id'] = str(doc['_id'])
                    del doc['_id']
                    if 'amount' in doc:
                        doc['amount'] = float(doc['amount'])
                    items.append(doc)
                return items, total
            except Exception as e:
                logger.error(f"Mongo query failed, falling back to local SQLite: {e}")
                self.is_online = False

        # SQLite Query builder
        conn = sqlite3.connect(self.sqlite_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        where_clauses = ["user_id = ?"]
        params = [user_id]

        if month:
            where_clauses.append("month = ?")
            params.append(month)
        if search:
            where_clauses.append("item LIKE ?")
            params.append(f"%{search}%")
        if category and category != 'All':
            where_clauses.append("category = ?")
            params.append(category)

        where_str = " AND ".join(where_clauses)
        
        # Count Query
        count_query = f"SELECT COUNT(*) FROM expenses WHERE {where_str}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        # Results Query
        results_query = f"""
            SELECT * FROM expenses 
            WHERE {where_str} 
            ORDER BY date DESC, id DESC 
            LIMIT ? OFFSET ?
        """
        cursor.execute(results_query, params + [limit, skip])
        rows = cursor.fetchall()
        conn.close()

        return [_parse_row(r) for r in rows], total

    def add_expense(self, user_id, item, amount, category, date, month):
        eid = str(uuid.uuid4())
        
        expense_doc = {
            "id": eid,
            "user_id": user_id,
            "item": item,
            "amount": float(amount),
            "category": category,
            "date": date,
            "month": month
        }

        # SQLite first
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO expenses (id, user_id, item, amount, category, date, month, synced)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """, (eid, user_id, item, float(amount), category, date, month))
        conn.commit()
        conn.close()

        # MongoDB sync
        if self.is_online and self.mongo_db is not None:
            try:
                mongo_doc = dict(expense_doc)
                mongo_doc['_id'] = eid
                if 'id' in mongo_doc:
                    del mongo_doc['id']
                self.mongo_db.expenses.insert_one(mongo_doc)
                
                # Mark as synced
                conn = sqlite3.connect(self.sqlite_db_path)
                cursor = conn.cursor()
                cursor.execute("UPDATE expenses SET synced = 1 WHERE id = ?", (eid,))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Failed to sync new expense: {e}")
                self.is_online = False

        return expense_doc

    def get_expense_by_id(self, eid, user_id):
        if self.is_online and self.mongo_db is not None:
            try:
                doc = self.mongo_db.expenses.find_one({"_id": to_mongo_id(eid), "user_id": user_id})
                if doc:
                    doc['id'] = str(doc['_id'])
                    del doc['_id']
                    if 'amount' in doc:
                        doc['amount'] = float(doc['amount'])
                return doc
            except Exception as e:
                logger.error(f"Mongo get_expense_by_id failed: {e}")
                self.is_online = False
        
        conn = sqlite3.connect(self.sqlite_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM expenses WHERE id = ? AND user_id = ?", (eid, user_id))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def update_expense(self, eid, user_id, update_fields):
        # Update SQLite
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        set_clause = []
        params = []
        for k, v in update_fields.items():
            if k in ('item', 'category', 'date', 'month'):
                set_clause.append(f"{k} = ?")
                params.append(v)
            elif k == 'amount':
                set_clause.append("amount = ?")
                params.append(float(v))
                
        if set_clause:
            set_clause.append("synced = 0")
            params += [eid, user_id]
            query = f"UPDATE expenses SET {', '.join(set_clause)} WHERE id = ? AND user_id = ?"
            cursor.execute(query, params)
            conn.commit()
        conn.close()

        # MongoDB Sync
        if self.is_online and self.mongo_db is not None:
            try:
                self.mongo_db.expenses.update_one({"_id": to_mongo_id(eid), "user_id": user_id}, {"$set": update_fields})
                conn = sqlite3.connect(self.sqlite_db_path)
                cursor = conn.cursor()
                cursor.execute("UPDATE expenses SET synced = 1 WHERE id = ?", (eid,))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Failed to sync expense update: {e}")
                self.is_online = False
        return True

    def delete_expense(self, eid, user_id):
        # Delete SQLite
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (eid, user_id))
        conn.commit()
        conn.close()

        # Delete MongoDB
        if self.is_online and self.mongo_db is not None:
            try:
                self.mongo_db.expenses.delete_one({"_id": to_mongo_id(eid), "user_id": user_id})
            except Exception as e:
                logger.error(f"Failed to sync expense deletion: {e}")
                self.is_online = False
        return True

    def clear_all_user_expenses(self, user_id):
        # SQLite
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM monthly_summary WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

        # MongoDB
        if self.is_online and self.mongo_db is not None:
            try:
                self.mongo_db.expenses.delete_many({"user_id": user_id})
                self.mongo_db.monthly_summary.delete_many({"user_id": user_id})
            except Exception as e:
                logger.error(f"Failed to sync clear expenses: {e}")
                self.is_online = False
        return True

    # ──────────────────────────────────────────────────────────────────────────
    #  MONTHLY SALARY / SUMMARIES (Isolated to user_id)
    # ──────────────────────────────────────────────────────────────────────────

    def get_salary(self, user_id, month):
        if self.is_online and self.mongo_db is not None:
            try:
                doc = self.mongo_db.monthly_summary.find_one({"month": month, "user_id": user_id})
                return doc['salary'] if doc else 0.0
            except Exception as e:
                logger.error(f"Mongo get_salary failed: {e}")
                self.is_online = False
        
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT salary FROM monthly_summary WHERE month = ? AND user_id = ?", (month, user_id))
        res = cursor.fetchone()
        conn.close()
        return res[0] if res else 0.0

    def set_salary(self, user_id, month, amount):
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        
        # Check if exists
        cursor.execute("SELECT id FROM monthly_summary WHERE month = ? AND user_id = ?", (month, user_id))
        row = cursor.fetchone()
        
        if row:
            sid = row[0]
            cursor.execute("UPDATE monthly_summary SET salary = ?, synced = 0 WHERE id = ?", (float(amount), sid))
        else:
            sid = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO monthly_summary (id, user_id, month, salary, synced)
                VALUES (?, ?, ?, ?, 0)
            """, (sid, user_id, month, float(amount)))
            
        conn.commit()
        conn.close()

        # MongoDB Sync
        if self.is_online and self.mongo_db is not None:
            try:
                existing = self.mongo_db.monthly_summary.find_one({"month": month, "user_id": user_id})
                if existing:
                    existing_id = str(existing['_id'])
                    self.mongo_db.monthly_summary.update_one(
                        {"_id": existing['_id']},
                        {"$set": {"salary": float(amount)}}
                    )
                    if sid != existing_id:
                        conn = sqlite3.connect(self.sqlite_db_path)
                        cursor = conn.cursor()
                        cursor.execute("UPDATE monthly_summary SET id = ?, synced = 1 WHERE id = ?", (existing_id, sid))
                        conn.commit()
                        conn.close()
                        sid = existing_id
                    else:
                        conn = sqlite3.connect(self.sqlite_db_path)
                        cursor = conn.cursor()
                        cursor.execute("UPDATE monthly_summary SET synced = 1 WHERE id = ?", (sid,))
                        conn.commit()
                        conn.close()
                else:
                    self.mongo_db.monthly_summary.replace_one(
                        {"_id": to_mongo_id(sid)},
                        {"user_id": user_id, "month": month, "salary": float(amount)},
                        upsert=True
                    )
                    conn = sqlite3.connect(self.sqlite_db_path)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE monthly_summary SET synced = 1 WHERE id = ?", (sid,))
                    conn.commit()
                    conn.close()
            except Exception as e:
                logger.error(f"Failed to sync salary setup: {e}")
                self.is_online = False
        return {"month": month, "salary": float(amount)}

    def get_all_salaries_map(self, user_id):
        if self.is_online and self.mongo_db is not None:
            try:
                docs = list(self.mongo_db.monthly_summary.find({"user_id": user_id}))
                return {d['month']: d.get('salary', 0.0) for d in docs}
            except Exception as e:
                logger.error(f"Mongo get_all_salaries_map failed: {e}")
                self.is_online = False

        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT month, salary FROM monthly_summary WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return {r[0]: float(r[1]) for r in rows}

    def aggregate_expenses_by_month(self, user_id):
        if self.is_online and self.mongo_db is not None:
            try:
                exp_pipeline = [
                    {"$match": {"user_id": user_id}},
                    {"$group": {"_id": "$month", "total": {"$sum": "$amount"}}}
                ]
                all_expenses_agg = list(self.mongo_db.expenses.aggregate(exp_pipeline))
                return {e['_id']: float(e['total']) for e in all_expenses_agg}
            except Exception as e:
                logger.error(f"Mongo aggregate_expenses_by_month failed: {e}")
                self.is_online = False

        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT month, SUM(amount) FROM expenses WHERE user_id = ? GROUP BY month", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return {r[0]: float(r[1]) for r in rows}

    def aggregate_expenses_by_category(self, user_id, month):
        if self.is_online and self.mongo_db is not None:
            try:
                pipeline = [
                    {"$match": {"month": month, "user_id": user_id}},
                    {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}
                ]
                results = list(self.mongo_db.expenses.aggregate(pipeline))
                return {(r['_id'] or 'General'): float(r['total']) for r in results}
            except Exception as e:
                logger.error(f"Mongo aggregate_expenses_by_category failed: {e}")
                self.is_online = False

        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT category, SUM(amount) 
            FROM expenses 
            WHERE user_id = ? AND month = ? 
            GROUP BY category
        """, (user_id, month))
        rows = cursor.fetchall()
        conn.close()
        return {r[0] if r[0] else 'General': float(r[1]) for r in rows}

    def get_expenses_list_for_export(self, user_id, month_filter=None):
        if self.is_online and self.mongo_db is not None:
            try:
                query = {"user_id": user_id}
                if month_filter:
                    query["month"] = month_filter
                docs = list(self.mongo_db.expenses.find(query).sort("date", -1))
                for d in docs:
                    d['id'] = str(d['_id'])
                    del d['_id']
                    if 'amount' in d:
                        d['amount'] = float(d['amount'])
                return docs
            except Exception as e:
                logger.error(f"Mongo get_expenses_list_for_export failed: {e}")
                self.is_online = False

        conn = sqlite3.connect(self.sqlite_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if month_filter:
            cursor.execute("SELECT * FROM expenses WHERE user_id = ? AND month = ? ORDER BY date DESC", (user_id, month_filter))
        else:
            cursor.execute("SELECT * FROM expenses WHERE user_id = ? ORDER BY date DESC", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ──────────────────────────────────────────────────────────────────────────
    #  CATEGORIES CRUD
    # ──────────────────────────────────────────────────────────────────────────

    def list_categories(self):
        if self.is_online and self.mongo_db is not None:
            try:
                cats = list(self.mongo_db.categories.find().sort("name", 1))
                result = []
                for c in cats:
                    c['id'] = str(c['_id'])
                    del c['_id']
                    result.append(c)
                return result
            except Exception as e:
                logger.error(f"Mongo list_categories failed: {e}")
                self.is_online = False

        conn = sqlite3.connect(self.sqlite_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM categories ORDER BY name ASC")
        rows = cursor.fetchall()
        conn.close()
        
        # Fallback Seeding if SQLite empty
        if not rows:
            defaults = ["General", "Food & Dining", "Groceries", "Transportation",
                        "Utilities", "Entertainment", "Health", "Shopping", "Other"]
            conn = sqlite3.connect(self.sqlite_db_path)
            cursor = conn.cursor()
            for d in defaults:
                cursor.execute("INSERT OR IGNORE INTO categories (id, name, synced) VALUES (?, ?, 0)", (str(uuid.uuid4()), d))
            conn.commit()
            cursor.execute("SELECT * FROM categories ORDER BY name ASC")
            rows = cursor.fetchall()
            conn.close()
            
        return [dict(r) for r in rows]

    def add_category(self, name):
        cid = str(uuid.uuid4())
        
        # SQLite
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM categories WHERE name = ?", (name,))
        if cursor.fetchone():
            conn.close()
            raise Exception("Category exists")
        
        cursor.execute("INSERT INTO categories (id, name, synced) VALUES (?, ?, 0)", (cid, name))
        conn.commit()
        conn.close()

        # MongoDB Sync
        if self.is_online and self.mongo_db is not None:
            try:
                if not self.mongo_db.categories.find_one({"name": name}):
                    self.mongo_db.categories.insert_one({"_id": cid, "name": name})
                    conn = sqlite3.connect(self.sqlite_db_path)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE categories SET synced = 1 WHERE id = ?", (cid,))
                    conn.commit()
                    conn.close()
            except Exception as e:
                logger.error(f"Failed to sync category addition: {e}")
                self.is_online = False
                
        return {"id": cid, "name": name}

    def delete_category(self, cid):
        # Find category name
        conn = sqlite3.connect(self.sqlite_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM categories WHERE id = ?", (cid,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise Exception("Category not found")
        
        cat_name = row[0]
        
        # Check active usage
        cursor.execute("SELECT COUNT(*) FROM expenses WHERE category = ?", (cat_name,))
        count = cursor.fetchone()[0]
        if count > 0:
            conn.close()
            raise Exception(f"Cannot delete: {count} expense(s) use this category.")
            
        cursor.execute("DELETE FROM categories WHERE id = ?", (cid,))
        conn.commit()
        conn.close()

        # MongoDB
        if self.is_online and self.mongo_db is not None:
            try:
                self.mongo_db.categories.delete_one({"_id": to_mongo_id(cid)})
            except Exception as e:
                logger.error(f"Failed to sync category deletion: {e}")
                self.is_online = False
                
        return True
