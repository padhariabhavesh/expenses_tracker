# Expense Tracker

A comprehensive personal finance application to track expenses, categorize spending, and visualize data.

## Features

- **Dashboard**: High-level view of your spending, balance, and salary.
- **Transactions**: Add, edit, and delete expense records.
- **Dynamic Categories**: Create and manage custom expense categories (e.g., Food, Travel, Rent).
- **Visualizations**: Interactive charts to see spending breakdown by category.
- **Search**: Instantly filter transactions by item name.
- **Recurring Expenses**: Easily duplicate existing expenses for fast entry.
- **Export Data**: Download your expense history to Excel (Current Filters or All Data).
- **Auto-Shutdown**: If running the standalone Executable, the app closes automatically when you close the browser.

## How to Run

### Option 1: Standalone Executable (Recommended)
1. Navigate to the `dist` folder.
2. Double-click `ExpenseTracker.exe`.
3. The application will launch in your default web browser.

### Option 2: From Source (Python)
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the application:
   ```bash
   python backend/main.py
   ```
3. Open `http://127.0.0.1:8000` in your browser.

## Tech Stack
- **Backend**: Python (Flask), SQLAlchemy (SQLite)
- **Frontend**: HTML5, Bootstrap 5, Vanilla JavaScript
- **Charts**: Chart.js
- **Export**: OpenPyxl

## Project Structure
- `backend/`: Flask application and database models.
- `frontend/`: HTML templates.
- `static/`: CSS and JavaScript files.
- `dist/`: Compiled executable.
Manual Verification
Repair Environment:
Run the provided repair_env.ps1 script to recreate the virtual environment and install dependencies.
Activate Virtual Environment:
Run 
.\venv\Scripts\Activate.ps1
Rebuild Application:
Run pyinstaller Padharia.spec --clean --noconfirm.
Run Executable:
Navigate to dist/Padharia.
Run Padharia.exe.
