import sqlite3
import os

candidates = [
    r"D:\Freelance\expenses_tracker\instance\expenses.db",
    r"D:\Freelance\expenses_tracker\backend\instance\expenses.db",
    r"D:\Freelance\expenses_tracker\dist\expenses.db",
    r"D:\Freelance\expenses_tracker\dist\instance\expenses.db"
]

print(f"{'Path':<60} | {'Status':<10} | {'Expenses':<8} | {'Summaries':<9}")
print("-" * 100)

for db_path in candidates:
    if not os.path.exists(db_path):
        print(f"{db_path:<60} | MISSING    | -        | -")
        continue
        
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Check tables
        tables = [t[0] for t in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        
        if 'expense' in tables:
            count = c.execute("SELECT count(*) FROM expense").fetchone()[0]
        else:
            count = "No Table"
            
        if 'monthly_summary' in tables:
            summary_count = c.execute("SELECT count(*) FROM monthly_summary").fetchone()[0]
        else:
            summary_count = "No Table"
            
        print(f"{db_path:<60} | OK         | {str(count):<8} | {str(summary_count):<9}")
        conn.close()
    except Exception as e:
        print(f"{db_path:<60} | ERROR      | {str(e)}")
