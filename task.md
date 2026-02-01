# Task: Migrate to MongoDB Atlas

- [x] Dependencies
    - [x] Update `requirements.txt` (remove `flask-sqlalchemy`, add `pymongo`, `dnspython`, `python-dotenv`)
- [x] Configuration
    - [x] Create `.env` file template for MongoDB URI
    - [x] Update `main.py` to load config
- [x] Backend Refactoring
    - [x] Modify `backend/models.py` to remove SQLAlchemy and adapt for MongoDB
    - [x] Refactor `backend/main.py` to use `pymongo` instead of `db.session`
    - [x] Migrate data from SQLite to MongoDB (New Step)
- [x] Cleanup
    - [x] Remove `check_db.py` (SQLite specific)
    - [x] Remove SQLite database files (`expenses.db`)
- [x] Verification
    - [x] Verify application startup
    - [x] Verify MongoDB connection (Confirmed via migration script)
