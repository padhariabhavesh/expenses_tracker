# Migration to MongoDB Atlas

## Goal Description
Replace the existing SQLite database with MongoDB Atlas. This involves removing SQLAlchemy, adding PyMongo, and refactoring the CRUD logic in `backend/main.py` and `backend/models.py`.

## User Review Required
> [!IMPORTANT]
> **Database Password**: The connection string provided contains `<db_password>`. You will need to provide the actual password or update the code/config file with the correct URI after the changes.

> [!WARNING]
> **Data Migration**: This plan focuses on switching the backend to use MongoDB for *future* data. Existing data in SQLite will NOT be automatically migrated to MongoDB with this plan, but you have the CSV exports from the previous step which can be imported if needed.

## Proposed Changes

### Dependencies
#### [MODIFY] [requirements.txt](file:///d:/Freelance/expenses_tracker/requirements.txt)
- Remove `flask-sqlalchemy`
- Add `pymongo`, `dnspython`, `python-dotenv`

### Configuration
#### [NEW] [.env](file:///d:/Freelance/expenses_tracker/.env)
- Store `MONGO_URI` here.

### Backend
#### [MODIFY] [backend/models.py](file:///d:/Freelance/expenses_tracker/backend/models.py)
- Remove `db.Model` and `SQLAlchemy`.
- Create helper classes/functions for data validation if needed, or keeping simple dict structures.

#### [MODIFY] [backend/main.py](file:///d:/Freelance/expenses_tracker/backend/main.py)
- Initialize `pymongo.MongoClient`.
- Replace all `Expense.query...` and `db.session...` calls with `db.expenses.find...` etc.
- Handle pagination manually or using MongoDB `skip/limit`.
- Ensure `_id` handling (MongoDB uses ObjectId, which needs conversion to string for JSON).

### Cleanup
#### [DELETE] [check_db.py](file:///d:/Freelance/expenses_tracker/check_db.py)
- No longer relevant for MongoDB.

## Verification Plan

### Manual Verification
1.  **Startup**: Run `python backend/main.py` and ensure it connects to MongoDB (will fail auth if password wrong, need to verify error handling).
2.  **Add Expense**: Add a new expense via the UI. Check if it appears in MongoDB (dashboard stats should update).
3.  **List**: Verify the expenses list loads.
4.  **Edit/Delete**: Verify update and delete operations.
