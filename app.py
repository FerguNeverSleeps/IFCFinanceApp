# app.py
import os

import pandas
from flask import Flask, render_template, request, redirect, url_for, make_response, flash
from flask_sqlalchemy import SQLAlchemy
import pandas as pd, io, csv
from datetime import date

from models import OfferingCashSplit, ExcelUpload

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///offerings.db'
db = SQLAlchemy(app)

# Database Model
class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(20))  # 'manual' or 'givt'
    date = db.Column(db.Date)
    amount = db.Column(db.Float)


class Offering(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    date          = db.Column(db.Date,   nullable=False)
    total_amount  = db.Column(db.Float,  nullable=False)

class GivtUpload(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    filename     = db.Column(db.String(256), nullable=False)
    uploaded_at  = db.Column(db.DateTime, server_default=db.func.now())

# Create DB
with app.app_context():
    db.create_all()

# Routes
@app.route('/')
def index():
    return render_template('index.html', current_year=date.today().year)

@app.route('/manual-count')
def manual_count():
    return render_template('indexmanual.html', current_year=date.today().year)

@app.route('/import-givt')
def import_givt():
    return render_template('upload.html', current_year=date.today().year)

@app.route('/monthly-report')
def report():
    return render_template('report.html', current_year=date.today().year)

@app.route('/offering', methods=['GET', 'POST'])
def offering():
 if request.method == 'POST':
# new: read each denomination count and compute total
    denoms = {
        '0.50': 0.50,
        '1.00': 1.00,
        '2.00': 2.00,
        '5.00': 5.00,
        '10.00': 10.00,
        '20.00': 20.00,
        '50.00': 50.00,
        '100.00': 100.00,
    }
    total = 0.0
    has_entry = False
    for label, value in denoms.items():
        field = f"count_{label.replace('.', '_')}"
        # convert missing or blank to zero
        cnt = int(request.form.get(field, 0) or 0)
        if cnt > 0:
            has_entry = True
            total += cnt * value
    if not has_entry:
        flash('Please enter at least one denomination count.', 'error')
        return redirect(url_for('offering'))
    # now save
    date = request.form.get('date')
    off = Offering(date=date, total_amount=total)
    db.session.add(off)
    db.session.commit()

    flash(f'Offering of {total:.2f} saved.', 'success')
    return redirect(url_for('index'))
    return render_template('offering.html')


@app.route('/file_upload', methods=['POST'])
def file_upload():
    file = request.files['file']

    df = pandas.read_excel(file)
    if not os.path.exists("report"):
        os.mkdir("report")
    filename = f'{date.today()}.csv'
    filepath = os.path.join(app.config['report'], file.filename)
    df.to_csv(filepath, index=False)
    return render_template('report.html', filename=filename)


# --- Route: Upload Excel ---
@app.route('/upload', methods=['GET', 'POST'])
def upload_excel():
    if request.method == 'POST':
        # Retrieve uploaded file object
        file = request.files.get('excel_file')
        if not file:
            flash("No file selected", "danger")
            return redirect(request.url)

        # Secure filename and save locally
        filename = secure_filename(file.filename)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Record this upload in the DB
        upload_entry = ExcelUpload(filename=filename)
        db.session.add(upload_entry)
        db.session.commit()

        try:
            # Parse Excel, insert Transaction rows
            parse_excel(filepath, upload_entry.id)
            upload_entry.parsed_success = True
            db.session.commit()
            flash("File uploaded and parsed successfully!", "success")
        except Exception as e:
            # Show any parsing errors
            flash(f"Error during parsing: {e}", "danger")

        return redirect(request.url)

    # GET: render the upload form
    # GET: render the upload form by calling the Flask view, not linking to a static file
    return render_template('upload.html')

# --- Route: Record Cash Split ---
@app.route('/cash-split', methods=['GET', 'POST'])
def cash_split_entry():
    if request.method == 'POST':
        date = request.form['date']  # service date
        splits = []  # collect OfferingCashSplit objects

        # Loop through each denomination field in the form
        for denom_str in ['0.50', '1.00', '2.00', '5.00', '10.00']:
            count = int(request.form.get(f"count_{denom_str.replace('.', '_')}", 0))
            if count > 0:
                split = OfferingCashSplit(
                    date=date,
                    denomination=float(denom_str),
                    count=count,
                    type='coin' if float(denom_str) < 5 else 'bill'
                )
                splits.append(split)
                db.session.add(split)

        db.session.flush()  # assign temporary IDs to splits

        # Sum total amount from all splits
        total_cash = sum(s.denomination * s.count for s in splits)

        # Create one aggregated Transaction for this cash offering
        cash_tx = Transaction(
            date=date,
            subject='Cash Offering',
            source='cash',
            amount=total_cash
        )
        db.session.add(cash_tx)
        db.session.flush()  # assign cash_tx.id

        # Link each split row to this transaction
        for s in splits:
            s.transaction_id = cash_tx.id

        db.session.commit()  # save both splits and transaction
        flash("Cash split and total recorded.", "success")
        return redirect(request.url)

    # GET: render the cash split form
    # GET: render the offering entry template
    return render_template('offering.html')


# --- Route: View Report ---
@app.route('/report')
def report():
    view = request.args.get('view', 'monthly')  # options: 'daily', 'monthly', 'yearly'
    from sqlalchemy import func

    # Helper to query sums by period (bank vs. cash)
    def query_totals(source, fmt):
        return (
            db.session.query(
                func.strftime(fmt, Transaction.date).label('period'),
                func.sum(Transaction.amount).label('total')
            )
            .filter(Transaction.source == source)
            .group_by('period')
            .all()
        )

    # Determine SQL strftime format based on view
    fmt_map = {'daily':'%Y-%m-%d','monthly':'%Y-%m','yearly':'%Y'}
    fmt = fmt_map.get(view, '%Y-%m')

    # Fetch bank and cash totals
    bank = query_totals('bank', fmt)
    cash = query_totals('cash', fmt)

    # Combine into a single data structure for the template
    report_data = {}
    for period, total in bank:
        report_data.setdefault(period, {'bank': 0, 'cash': 0})['bank'] = total
    for period, total in cash:
        report_data.setdefault(period, {'bank': 0, 'cash': 0})['cash'] = total

    # Convert to sorted list of rows
    rows = sorted([
        {'period': p, 'bank': v['bank'], 'cash': v['cash'], 'total': v['bank'] + v['cash']}
        for p, v in report_data.items()
    ], key=lambda x: x['period'])

    # Render report template with context
    return render_template('report.html', view=view, rows=rows)

# --- Utility Function: Parse Excel ---
def parse_excel(filepath, upload_id):
    # Load workbook and target sheet
    xls = pd.ExcelFile(filepath)
    df = xls.parse("Account Rabo Lopend ICF")

    # Use first row as header, drop it, reset index
    df.columns = df.iloc[0]
    df = df.drop(index=0).reset_index(drop=True)

    # Convert columns to correct types
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
    df = df.dropna(subset=['Date','Amount'])  # remove invalid rows

    # Insert each row as a Transaction
    for _, row in df.iterrows():
        tx = Transaction(
            date=row['Date'],
            subject=row.get('Subject',''),
            source='bank',
            amount=row['Amount'],
            category=row.get('Surplus',''),
            excel_upload_id=upload_id
        )
        db.session.add(tx)
    db.session.commit()


if __name__ == "__main__":
    app.run(host="0.0.0.0",debug=True)
