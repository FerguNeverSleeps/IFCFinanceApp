# app.py
from flask import Flask, render_template, request, redirect, url_for, make_response
from flask_sqlalchemy import SQLAlchemy
import pandas as pd, io, csv
from datetime import date
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///offerings.db'
db = SQLAlchemy(app)

class Transaction(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    source    = db.Column(db.String(20))       # 'manual' or 'givt'
    date      = db.Column(db.Date)
    amount    = db.Column(db.Float)

db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

# ... more routes below ...

if __name__ == "__main__":
    app.run(debug=True)



@app.route('/add_manual', methods=['POST'])
def add_manual():
    total = 0.0
    for denom_str in request.form:
        if denom_str.startswith('qty_'):
            denom = float(denom_str.split('_')[1])
            qty   = int(request.form[denom_str])
            total += denom * qty
    txn = Transaction(source='manual', date=date.today(), amount=total)
    db.session.add(txn)
    db.session.commit()
    return redirect(url_for('index'))