from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy import select, func
import hmac
# Initialize SQLAlchemy ORM
db = SQLAlchemy()

class ExcelUpload(db.Model):
    __tablename__ = 'excel_uploads'
    id = db.Column(db.Integer, primary_key=True)  # unique ID
    filename = db.Column(db.String(255), nullable=False)  # original filename
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow())  # timestamp of upload
    parsed_success = db.Column(db.Boolean, default=False)  # did parsing complete?

    # Relationship to Transaction: one upload → many transactions
    transactions = db.relationship('Transaction', backref='excel_upload', lazy=True)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)  # unique ID
    date = db.Column(db.Date, nullable=False)  # date of transaction
    subject = db.Column(db.String(255))  # description (e.g., "GIVT + Rabo Direct")
    source = db.Column(db.String(50))  # 'bank' or 'cash'
    amount = db.Column(db.Float, nullable=False)  # transaction amount
    category = db.Column(db.String(100), nullable=True)  # optional category tag
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # record creation time
    # Who counted and checked the cash, and who carried the envelope
    counted_by = db.Column(db.String(100), nullable=True)
    checked_by = db.Column(db.String(100), nullable=True)
    carrier_of_envelope = db.Column(db.String(100), nullable=True)

    # ForeignKey linking back to which Excel file it came from
    excel_upload_id = db.Column(db.Integer, db.ForeignKey('excel_uploads.id'), nullable=True)
    # Relationship to OfferingCashSplit: one transaction → many cash splits
    cash_splits = db.relationship('OfferingCashSplit', backref='transaction', lazy=True)

class OfferingCashSplit(db.Model):
    __tablename__ = 'offering_cash_split'
    id = db.Column(db.Integer, primary_key=True)  # unique ID
    date = db.Column(db.Date, nullable=False)  # service date
    denomination = db.Column(db.Float, nullable=False)  # coin/bill value (e.g., 0.50)
    count = db.Column(db.Integer, nullable=False)  # number of items counted
    type = db.Column(db.String(10), nullable=False)  # 'coin' or 'bill'

    # ForeignKey linking back to the aggregated cash transaction
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=True)

class Offering(db.Model):
    __tablename__ = 'offerings'

    id                   = db.Column(db.Integer, primary_key=True)
    date                 = db.Column(db.Date,    nullable=False)
    total_amount         = db.Column(db.Numeric(12,2), nullable=False)
    counted_by           = db.Column(db.String(100), nullable=True)
    checked_by           = db.Column(db.String(100), nullable=True)
    carrier_of_envelope  = db.Column(db.String(100), nullable=True)
    deposit_status       = db.Column(db.Boolean, default=False, nullable=False)
    deposit_date         = db.Column(db.Date,    nullable=True)
#transaction for the table of registering spending
class transaction1(db.Model):
    __tablename__ = 'transaction'
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(20), nullable=False)
    date = db.Column(db.Date, nullable=False)
    category = db.Column(db.String(255), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    type_ofspending = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(255),nullable=False)

class User(db.Model):
    __tablename__ = "users"  # avoid "user" (reserved in some DBs)

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80),  unique=True, index=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active     = db.Column(db.Boolean, default=True,  nullable=False)
    is_admin      = db.Column(db.Boolean, default=False, nullable=False)
    created_at    = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at    = db.Column(db.DateTime, nullable=False,server_default=db.func.now(), onupdate=db.func.now())

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        ph = self.password_hash or ""
        # If it's a real hash, verify with Werkzeug
        if ph.startswith(("pbkdf2:", "scrypt:", "argon2:", "bcrypt")):
            return check_password_hash(ph, password)
        # Legacy fallback: stored as plaintext (temporary)
        return hmac.compare_digest(ph, password)

    def __repr__(self) -> str:
        return f"<User {self.username}>"

