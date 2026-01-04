# Expense Tracker (Padharia Manual)

A comprehensive personal finance application designed to track expenses, categorize spending, and visualize financial data effectively. 
This application can run as a standalone desktop executable or as a local web server.

## Features

- **Dashboard**: High-level view of your spending, balance, and salary for the selected month.
- **Transactions Management**: Add, edit, and delete expense records with ease.
- **Dynamic Categories**: Create and manage custom expense categories (e.g., Food, Travel, Rent, Utilities).
- **Import/Export**: 
    - **Import**: Bulk import expenses from files.
    - **Export**: Download your expense history to Excel (supports filtering).
- **Visualizations**: Interactive charts to analyze spending breakdown by category.
- **Search**: Instantly filter transactions by item name or category.
- **Recurring Expenses**: One-click duplication of existing expenses for fast entry.
- **Persistent Data**: Uses a local SQLite database (`expenses.db`) which persists across restarts.

## How to Run (End User)

### Option 1: Standalone Executable
1. Navigate to the `dist/Padharia` folder.
2. Double-click `Padharia.exe`.
3. The application will launch a window displaying the user interface.
   *(Note: The app runs a local backend server on `http://127.0.0.1:8000` internally)*.

### Option 2: From Source (Developer)
Prerequisites: Python 3.x installed.

1. **Install Dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

2. **Run the Backend**:
   ```powershell
   python backend/main.py
   ```

3. **Open Application**:
   Open functionality in your browser at `http://127.0.0.1:8000`.

## Build Instructions (For Developer)

If you made changes to the code and want to regenerate the `.exe` file, follow these steps using PowerShell.

1. **Repair/Setup Environment** (Optional, if fresh clone):
   ```powershell
   .\repair_env.ps1
   ```

2. **Activate Virtual Environment**:
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

3. **Build the Executable**:
   Use PyInstaller with the provided spec file to create the bundled app.
   ```powershell
   pyinstaller Padharia.spec --clean --noconfirm
   ```

4. **Verify Build**:
   Navigate to the `dist` folder to find your new executable.

## Troubleshooting

- **Logs**: If the application fails to start, check `debug.log` located in the same directory as the executable (or in the root folder if running from source).
- **Database**: The database is stored in `expenses.db`. Ensure this file is not locked by another process if you encounter write errors.
- **Port Conflicts**: The app uses port `8000`. Ensure no other service is using this port.

## Tech Stack
- **Backend**: Python (Flask), SQLAlchemy (SQLite)
- **Frontend**: HTML5, Bootstrap 5, Vanilla JavaScript
- **Desktop Wrapper**: PyQt5 (WebEngine)
- **Charts**: Chart.js
- **Data Handling**: OpenPyxl (Excel), Pandas (if used)
