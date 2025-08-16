# app.py
import os
import traceback
from decimal import Decimal
from urllib.parse import urlencode

import pandas
from flask import Flask, render_template, request, redirect, url_for, make_response, flash, abort
from flask_sqlalchemy import SQLAlchemy
import pandas as pd, io, csv
from datetime import date, datetime
import openpyxl
from sqlalchemy import text

from models import db, Offering

from werkzeug.utils import secure_filename

from models import OfferingCashSplit, ExcelUpload, Transaction,transaction1
import secrets



# --- Flask App Configuration ---
port_num = "12215"
ngrok_num = "6"

app = Flask(__name__)
#app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://postgres.vwztopgxiiaujlmagico:icfdat190501@aws-1-eu-central-1.pooler.supabase.com:5432/postgres'
#ngrok
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://tavs:190501@{ngrok_num}.tcp.ngrok.io:{port_num}/ICFfinance'

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = secrets.token_hex(16)
db = SQLAlchemy(app)

def _parse_date(s):
    """Return a date object from several common formats, else None."""
    if not s:
        return None
    if isinstance(s, date):
        return s
    if isinstance(s, datetime):
        return s.date()

    s = str(s).strip()

    # Most browsers send YYYY-MM-DD for <input type="date">, but accept others too
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass

    return None

def _load_categories():
    """Distinct category list for the dropdown."""
    sql = text('SELECT DISTINCT category FROM "transaction" ORDER BY 1;')
    return db.session.execute(sql).scalars().all()

def _is_all_category(val: str) -> bool:
    return (val or "").strip().lower() in ("", "all", "all categories")

def _tx_date_bounds():
    row = db.session.execute(text('SELECT MIN(date) AS mind, MAX(date) AS maxd FROM "transaction";')).mappings().one()
    # return ISO strings (empty if None)
    return (
        row['mind'].isoformat() if row['mind'] else "",
        row['maxd'].isoformat() if row['maxd'] else ""
    )

def build_where_and_params(start, end, category):
    clauses = []
    params = {}

    if start:
        clauses.append("date >= :start")
        params["start"] = start
    if end:
        clauses.append("date <= :end")
        params["end"] = end
    if category:
        clauses.append("category = :category")
        params["category"] = category

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where_sql, params
# Database Model

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



@app.route('/file_upload.html', methods=['POST'])
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
@app.route('/upload.html', methods=['GET', 'POST'])
def upload_excel():
    print(">>> ENTERED upload_excel, method=", request.method)
    if request.method == 'POST':
        # Retrieve uploaded file object
        file = request.files.get('file')
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

        print(f"→ About to call parse_excel on {filepath!r}")
        try:
            # Parse Excel, insert Transaction rows
            count = parse_excel(filepath, upload_entry.id)  # adds to session
            upload_entry.parsed_success = True
            db.session.commit()  # one commit for both upload row and transactions
            flash("File uploaded and parsed successfully!", "success")
        except Exception as e:
            # Show any parsing errors
            traceback.print_exc()
            flash(f"Error during parsing: {e}", "danger")

        return redirect(request.url)

    # GET: render the upload form
    # GET: render the upload form by calling the Flask view, not linking to a static file
    return render_template('upload.html')

# --- Route: Record Cash Split ---
@app.route('/offering.html', methods=['GET', 'POST'])
def cash_split_entry():
    if request.method == 'POST':
        form = request.form  # used to repopulate on error

        # --- read fields (normalize names) ---
        date_str = (form.get('date') or '').strip()
        counted_by = (form.get('counted_by') or '').strip()
        checked_by = (form.get('checked_by') or '').strip()
        # your input might be name="carrier" or name="carrier_of_envelope"
        carrier = (form.get('carrier') or form.get('carrier_of_envelope') or '').strip()

        # collect denomination counts
        counts = []
        for k, v in form.items():
            if k.startswith('count_'):
                try:
                    counts.append(int(v or 0))
                except ValueError:
                    counts.append(0)

        # --- server-side validation ---
        errors = []
        if not date_str:
            errors.append("Date is required.")
        if not any(c > 0 for c in counts):
            errors.append("Enter at least one denomination count > 0.")
        if not (counted_by and checked_by and carrier):
            errors.append("Fill Counted By, Checked By, and Carrier of Envelope.")

        if errors:
            # ❗ Do NOT redirect -> re-render with the same values
            for msg in errors:
                flash(msg, "error")
            return render_template('offering.html', F=form), 400

        # --- success path: compute totals & save ---
        try:
            total_cash = float(form.get('total_cash', 0) or 0)
        except ValueError:
            total_cash = 0.0

        if errors:
            for msg in errors: flash(msg, "error")
            return render_template('offering.html', F=form), 400

        # --- SUCCESS PATH (replace your current save/commit code with this) ---

        # 1) Convert to the exact types your DB expects
        date_obj = _parse_date(date_str)  # returns datetime.date
        if not date_obj:
            flash("Invalid date format.", "error")
            return render_template('offering.html', F=form), 400

        try:
            # Accept "600" / "600.00" / "600,00"
            total_cash = Decimal(str(form.get('total_cash', '0')).replace(',', '.'))
        except Exception:
            total_cash = Decimal("0")

        counted_by = form.get('counted_by')
        checked_by = form.get('checked_by')
        carrier = form.get('carrier') or form.get('carrier_of_envelope')

        # 2) Build ORM rows with proper types
        offer = Offering(
            date=date_obj,  # DATE, not a string
            total_amount=total_cash,  # NUMERIC/DECIMAL
            counted_by=counted_by,
            checked_by=checked_by,
            carrier_of_envelope=carrier,
            deposit_status=False,  # or your real default
            deposit_date=None
        )

        tran = transaction1(
            subject="sunday offering",
            date=date_obj,  # DATE
            category="offering",
            amount=total_cash,  # NUMERIC/DECIMAL
            type_ofspending="asset",
            description="sunday offering"
        )

        # 3) Commit safely
        try:
            db.session.add_all([tran, offer])
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # helpful feedback + keep user input
            flash("Database error while saving the offering. Please try again.", "error")
            # optional: current_app.logger.exception(e)
            return render_template('offering.html', F=form), 500

        flash("Cash split and total recorded.", "success")
        flash("Offering saved and PDF generated.", "success")
        return redirect(url_for('cash_split_entry', saved='1'))

        # GET: render the form (empty unless just saved)
    return render_template('offering.html', F=None, just_saved=(request.args.get('saved') == '1'))

def _parse_date(s: str):
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()

def _load_categories():
    sql = text("""
        SELECT DISTINCT category
        FROM transaction
        WHERE category IS NOT NULL
        ORDER BY category
    """)
    with db.engine.begin() as conn:
        res = conn.execute(sql).fetchall()
    return [row[0] for row in res]


@app.route('/report.html', methods=['GET'])
def reportfinance_view():
    start_raw = request.args.get("start_date", "")
    end_raw = request.args.get("end_date", "")
    selected_category = (request.args.get("category") or "").strip()

    min_date, max_date = _tx_date_bounds()

    # first load: just render with bounds
    if not start_raw or not end_raw:
        return render_template(
            "report.html",
            rows=[],
            start_date=start_raw,
            end_date=end_raw,
            selected_category=(selected_category or "all categories"),
            min_date=min_date,
            max_date=max_date,
        )

    # parse & validate
    start_dt = _parse_date(start_raw)
    end_dt = _parse_date(end_raw)
    if not start_dt or not end_dt:
        flash("Please choose valid dates.")
        return redirect(url_for("reportfinance_view"))

    if start_dt > end_dt:
        flash("End date must be on or after the start date.")
        return redirect(url_for("reportfinance_view",
                                start_date=start_raw, end_date=end_raw, category=selected_category))

    category = None if selected_category.lower() in ("", "all", "all categories") else selected_category

    sql = text("""
               SELECT date, subject, type_ofspending, category, amount, description
               FROM "transaction"
               WHERE date BETWEEN :start_dt
                 AND :end_dt
                 AND (:category IS NULL
                  OR category = :category)
               ORDER BY date ASC
               """)

    with db.engine.begin() as conn:
        rows = [dict(r._mapping) for r in conn.execute(sql, {
            "start_dt": start_dt, "end_dt": end_dt, "category": category
        }).fetchall()]

    return render_template(
        "report.html",
        rows=rows,
        start_date=start_raw,
        end_date=end_raw,
        selected_category=(selected_category or "all categories"),
        min_date=min_date,
        max_date=max_date,
    )
''' 
# --- Route: View Report ---
@app.route('/report.html', methods=['GET'])
def reportfinance_view():
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
'''
# --- Utility Function: Parse Excel ---
def parse_excel(filepath, upload_id):
    """
            Parse the Excel file and add Transaction rows to db.session.
            - DOES NOT commit; caller should commit/rollback.
            - Returns the number of Transaction rows added.
            """

    def _ffill(seq):
        cur = None;
        out = []
        for x in seq:
            if pd.notna(x): cur = x
            out.append(cur)
        return out

    def _combine_headers(df_raw):
        """
        Sheets use two header rows:
        row 0: category names (e.g., 'Events', 'GIVT')
        row 1: column names or 'Debet'/'Credit'
        """
        top = _ffill(df_raw.iloc[0].tolist())
        sub = df_raw.iloc[1].tolist()
        cols = []
        for t, s in zip(top, sub):
            if isinstance(s, str) and s.strip() and s.lower() not in ("debet", "credit"):
                cols.append(s)  # Date, Subject, Amount, Booked, ...
            elif isinstance(s, str) and s.lower() in ("debet", "credit"):
                cols.append(f"{t}|{s}")  # e.g., "Events|Debet"
            else:
                cols.append(str(t or s))
        df = df_raw.iloc[2:].reset_index(drop=True)
        df.columns = cols
        return df

    from models import Transaction  # adjust import path if needed

    inserted = 0
    xls = pd.ExcelFile(filepath, engine="openpyxl")

    # ---------- Sheet: Account Rabo Lopend ICF ----------
    if "Account Rabo Lopend ICF" in xls.sheet_names:
        df_raw = xls.parse("Account Rabo Lopend ICF", header=None)
        df = _combine_headers(df_raw)

        # normalize types
        if "Date" not in df.columns:
            raise ValueError("Missing 'Date' column in 'Account Rabo Lopend ICF'")
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date

        cat_cols = [c for c in df.columns if "|" in c]  # category Debet/Credit columns

        for _, row in df.iterrows():
            if pd.isna(row.get("Date")) and pd.isna(row.get("Amount")):
                continue

            category = None
            signed_amount = None
            # choose first non-zero category cell; Debet = +, Credit = -
            for c in cat_cols:
                v = row.get(c)
                if pd.notna(v) and isinstance(v, (int, float)) and v != 0:
                    name, side = c.split("|", 1)
                    category = name
                    signed_amount = float(v) * (1 if side.lower() == "debet" else -1)
                    break

            # fallback to Amount column
            if signed_amount is None and "Amount" in df.columns and pd.notna(row.get("Amount")):
                signed_amount = float(row["Amount"])

            if signed_amount is None:
                continue

            tx = Transaction(
                date=row["Date"],
                subject=(row.get("Subject") or ""),
                source="bank",
                amount=signed_amount,
                category=category,
                excel_upload_id=upload_id,
            )
            db.session.add(tx)
            inserted += 1

    # ---------- Sheet: Account Rabo Spaar ICF ----------
    if "Account Rabo Spaar ICF" in xls.sheet_names:
        df_raw = xls.parse("Account Rabo Spaar ICF", header=None)
        df = _combine_headers(df_raw)
        if "Date" not in df.columns:
            raise ValueError("Missing 'Date' column in 'Account Rabo Spaar ICF'")
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date

        for _, row in df.iterrows():
            if pd.isna(row.get("Date")) and pd.isna(row.get("Amount")):
                continue

            debit = row.get("Spaarrekening|Debet")
            credit = row.get("Spaarrekening|Credit")
            if pd.notna(debit) and debit != 0:
                signed_amount = float(debit)  # money to savings
            elif pd.notna(credit) and credit != 0:
                signed_amount = -float(credit)  # money from savings
            elif pd.notna(row.get("Amount")):
                signed_amount = float(row["Amount"])
            else:
                continue

            tx = Transaction(
                date=row["Date"],
                subject=(row.get("Subject") or ""),
                source="bank",
                amount=signed_amount,
                category="Spaarrekening",
                excel_upload_id=upload_id,
            )
            db.session.add(tx)
            inserted += 1

    return inserted

@app.route('/report-summary', methods=['GET'])
@app.route('/report-summary', methods=['GET'])
def report_summary():
    start_raw = (request.args.get('start') or request.args.get('start_date') or '').strip()
    end_raw = (request.args.get('end') or request.args.get('end_date') or '').strip()
    category_in = (request.args.get('category') or '').strip()

    # treat “all categories” / empty as no filter
    cat_l = category_in.lower()
    category = None if cat_l in ('', 'all', 'all categories') else category_in

    # build WHERE + params (pass real date objects)
    params, clauses = {}, []
    if start_raw:
        params['start'] = _parse_date(start_raw)  # returns datetime.date
        clauses.append('date >= :start')
    if end_raw:
        params['end'] = _parse_date(end_raw)
        clauses.append('date <= :end')
    if category is not None:
        params['category'] = category
        clauses.append('category = :category')

    where_sql = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''

    total_sql = text(f"""
           SELECT COALESCE(SUM(amount),0)::numeric(18,2) AS total
           FROM "transaction"
           {where_sql}
       """)
    by_category_sql = text(f"""
           SELECT category,
                  COUNT(*) AS count,
                  COALESCE(SUM(amount),0)::numeric(18,2) AS total
           FROM "transaction"
           {where_sql}
           GROUP BY category
           ORDER BY category
       """)
    monthly_sql = text(f"""
           SELECT to_char(date_trunc('month', date), 'YYYY-MM') AS period,
                  COALESCE(SUM(amount),0)::numeric(18,2) AS total
           FROM "transaction"
           {where_sql}
           GROUP BY 1
           ORDER BY 1
       """)

    with db.engine.begin() as con:
        total = con.execute(total_sql, params).scalar() or 0
        by_category = con.execute(by_category_sql, params).mappings().all()
        monthly = con.execute(monthly_sql, params).mappings().all()

    show_monthly = len(monthly) >= 2

    return render_template(
        'reportsummary.html',
        total=total,
        by_category=by_category,
        monthly=monthly,
        show_monthly=show_monthly,
        start=start_raw, end=end_raw, category=category_in
    )

@app.route('/offeringsview.html', methods=['GET'])
def offerings_list():
    sql = text("""
               SELECT id, date, total_amount, counted_by, checked_by, carrier_of_envelope,
                   deposit_status,deposit_date
               FROM offerings
               ORDER BY date DESC
""")
    # query from the Offering table (or Transaction if you kept it there)
    # Run the query
    result = db.session.execute(sql)

    # Convert rows to plain dicts in a version-safe way
    offers = []
    for row in result:
        # SQLAlchemy 1.4/2.0: row._mapping is a Mapping
        if hasattr(row, "_mapping"):
            offers.append(dict(row._mapping))
        else:
            # Older versions: RowProxy is already dict-able
            offers.append(dict(row))
    return render_template('offeringsview.html', offers=offers)

@app.route('/offeringedit.html', methods=['GET','POST'])
def edit_offering():
    # 1) Grab optional date‐range filters so we can re‐render the list after POST
    start = request.args.get('start_date', '')
    end = request.args.get('end_date', '')

    # 2) Build the same list query you used in /offerings list
    qry = db.session.query(Offering)
    if start:
        sd = datetime.strptime(start, '%Y-%m-%d').date()
        qry = qry.filter(Offering.date >= sd)
    if end:
        ed = datetime.strptime(end, '%Y-%m-%d').date()
        qry = qry.filter(Offering.date <= ed)
    offers = qry.order_by(Offering.date.desc()).all()

    # id from query string (?id=123) or hidden input on POST
    offer_id = request.args.get("id", type=int) or request.form.get("id", type=int)
    if not offer_id:
        abort(400, description="Missing offering id")

    # --- FETCH via SQL (replaces Offering.query.get_or_404) ---
    offer = db.session.execute(
        text("""
             SELECT id, date, total_amount, counted_by, checked_by, carrier_of_envelope, deposit_status, deposit_date
             FROM offerings
             WHERE id = :id
             """),
        {"id": offer_id},
    ).mappings().first()
    if offer is None:
        abort(404)

    if request.method == "POST":
        deposit_status = "deposit_status" in request.form
        date_str = (request.form.get("deposit_date") or "").strip()
        deposit_date = (
            datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None
        )

        # --- UPDATE via SQL ---
        db.session.execute(
            text("""
                 UPDATE offerings
                 SET deposit_status = :status,
                     deposit_date   = :date
                 WHERE id = :id
                 """),
            {"status": deposit_status, "date": deposit_date, "id": offer_id},
        )
        db.session.commit()
        flash("Offering updated.", "success")
        #return redirect(url_for("offerings_list"))
        # Pass the raw start/end strings back so the form can re-fill its inputs
        return render_template('offeringsview.html',
                               offers=offers,
                               start_date=start or '',
                               end_date=end or '')

    # GET – render form
    return render_template("offeringedit.html", offer=offer, id=offer_id)
@app.route('/transactions.html', methods=['GET', 'POST'])
def transaction_input():
    if request.method == 'POST':
        date = request.form['tdate']  # service date
        total_cash = float(request.form['tamount'] or 0)

        db.session.flush()  # assign temporary IDs to splits

        # ... your existing split logic to compute `total_cash` ...

        subject = request.form.get('tsubject')
        category = request.form.get('tcategory')
        category = category.lower()
        tcreated = request.form.get('tcreated_at')
        tcreated = tcreated.lower()
        tspending = request.form.get('tspending')
        tspending = tspending.lower()
        # (2) insert into the offerings table
        offer = transaction1(
            date=date,
            amount=total_cash,
            category=category,
            subject=subject,
            description=tcreated,
            type_ofspending=tspending
        )
        db.session.add(offer)
        db.session.flush()  # assign cash_tx.id

        db.session.commit()  # save both splits and transaction
        flash("Financial input recorded", "success")
        return redirect('transactions.html')

    # GET: render the cash split form
    # GET: render the offering entry template
    return render_template('transactions.html')


if __name__ == "__main__":
    app.run(host="0.0.0.0",debug=True)
