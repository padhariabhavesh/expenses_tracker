from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(100))
    amount = db.Column(db.Float)
    category = db.Column(db.String(50), default='General')
    month = db.Column(db.String(20)) # Keep for easy grouping/filtering
    date = db.Column(db.String(20))  # New: Store YYYY-MM-DD

    def to_dict(self):
        return {
            "id": self.id,
            "item": self.item,
            "amount": self.amount,
            "category": self.category,
            "month": self.month,
            "date": self.date 
        }

class MonthlySummary(db.Model):
    month = db.Column(db.String(20), primary_key=True)
    salary = db.Column(db.Float, default=0.0)

    def to_dict(self):
        return {
            "month": self.month,
            "salary": self.salary
        }

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

    def to_dict(self):
        return { "id": self.id, "name": self.name }
