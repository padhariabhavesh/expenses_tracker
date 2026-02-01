import sqlite3
import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Paths
sqlite_db_path = r"D:\Freelance\expenses_tracker\dist\expenses.db"
env_path = r"D:\Freelance\expenses_tracker\.env"

# Load Env
load_dotenv(env_path)
mongo_uri = os.getenv("MONGO_URI")

if not mongo_uri or "YOUR_PASSWORD_HERE" in mongo_uri:
    print("Error: MONGO_URI not set properly in .env")
    exit(1)

# Connect to MongoDB
try:
    client = MongoClient(mongo_uri)
    db = client.get_database("expenses_tracker")
    print("Connected to MongoDB")
except Exception as e:
    print(f"Failed to connect to MongoDB: {e}")
    exit(1)

# Connect to SQLite
if not os.path.exists(sqlite_db_path):
    print(f"SQLite DB not found at {sqlite_db_path}")
    exit(1)

conn = sqlite3.connect(sqlite_db_path)
cursor = conn.cursor()
print(f"Connected to SQLite: {sqlite_db_path}")

# --- Migrate Categories ---
print("Migrating Categories...")
cursor.execute("SELECT name FROM category") # Assuming table name is 'category' based on previous exports
sqlite_cats = cursor.fetchall()

count = 0
for row in sqlite_cats:
    cat_name = row[0]
    if not db.categories.find_one({"name": cat_name}):
        db.categories.insert_one({"name": cat_name})
        count += 1
print(f"  Added {count} new categories.")

# --- Migrate Expenses ---
print("Migrating Expenses...")
# SQLite: id, item, amount, category, month, date
# Note: Check column order from earlier export or select by name
cursor.execute("SELECT item, amount, category, month, date FROM expense")
expenses = cursor.fetchall()

expense_docs = []
for row in expenses:
    # Convert row to dict
    doc = {
        "item": row[0],
        "amount": float(row[1]) if row[1] is not None else 0.0,
        "category": row[2] or "General",
        "month": row[3],
        "date": row[4] # Keeping as string YYYY-MM-DD
    }
    expense_docs.append(doc)

if expense_docs:
    # Optional: Clear existing seeded/test data?
    # db.expenses.delete_many({}) 
    result = db.expenses.insert_many(expense_docs)
    print(f"  Inserted {len(result.inserted_ids)} expenses.")
else:
    print("  No expenses found in SQLite.")

# --- Migrate Monthly Summaries ---
print("Migrating Monthly Summaries...")
cursor.execute("SELECT month, salary FROM monthly_summary")
summaries = cursor.fetchall()

count = 0
for row in summaries:
    month = row[0]
    salary = float(row[1]) if row[1] is not None else 0.0
    
    # Upsert
    res = db.monthly_summary.update_one(
        {"month": month},
        {"$set": {"salary": salary}},
        upsert=True
    )
    if res.upserted_id or res.modified_count:
        count += 1

print(f"  Processed {count} monthly summaries.")

conn.close()
client.close()
print("Migration Complete.")
