import sqlite3
import os
import csv
from datetime import datetime

# Define candidates based on known paths
candidates = [
    (r"D:\Freelance\expenses_tracker\instance\expenses.db", "root_instance"),
    (r"D:\Freelance\expenses_tracker\backend\instance\expenses.db", "backend_instance"),
    (r"D:\Freelance\expenses_tracker\dist\expenses.db", "dist_root"),
    (r"D:\Freelance\expenses_tracker\dist\instance\expenses.db", "dist_instance")
]

# Create exports directory with timestamp
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
base_export_dir = os.path.join(os.getcwd(), "exports", f"export_{timestamp}")
os.makedirs(base_export_dir, exist_ok=True)

print(f"Starting export to: {base_export_dir}")
print("-" * 60)

for db_path, label in candidates:
    if not os.path.exists(db_path):
        print(f"Skipping {label}: File not found ({db_path})")
        continue

    print(f"Processing {label}...")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        if not tables:
            print(f"  No tables found in {label}")
            conn.close()
            continue

        # Create subfolder for this database
        db_export_dir = os.path.join(base_export_dir, label)
        os.makedirs(db_export_dir, exist_ok=True)

        for table_name_tuple in tables:
            table_name = table_name_tuple[0]
            
            # Skip internal sqlite tables
            if table_name.startswith('sqlite_'):
                continue
                
            csv_path = os.path.join(db_export_dir, f"{table_name}.csv")
            
            try:
                # Get data
                cursor.execute(f"SELECT * FROM {table_name}")
                rows = cursor.fetchall()
                
                # Get column headers
                headers = [description[0] for description in cursor.description]
                
                if rows:
                    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow(headers)
                        writer.writerows(rows)
                    print(f"  Exported {table_name}: {len(rows)} rows -> {csv_path}")
                else:
                    print(f"  Skipped {table_name}: No data")
                    
            except Exception as e:
                print(f"  Failed to export table {table_name}: {e}")

        conn.close()
        
    except Exception as e:
        print(f"Error processing {db_path}: {e}")

print("-" * 60)
print("Export complete.")
