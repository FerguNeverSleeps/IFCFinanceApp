# app.py
import os

from flask import Flask, render_template, request, redirect, url_for, make_response, flash
from flask_sqlalchemy import SQLAlchemy
import pandas as pd, io, csv
from datetime import date
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
        '10.00': 10.00
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


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        # 1. Grab the file object from the submitted form
        #    request.files is a dict of uploaded files; 'file' matches the <input name="file">
        f = request.files.get('file')

        # 2. If the user submitted the form without choosing a file, flash an error and reload
        if not f:
            flash('No file selected', 'error')
            return redirect(url_for('upload'))

        # 3. Extract the original filename
        fn = f.filename

        # 4. Build a full path under our configured UPLOAD_FOLDER
        #    This is where we'll save the file on disk
        path = os.path.join(app.config['UPLOAD_FOLDER'], fn)

        # 5. Save the uploaded file to the server filesystem
        f.save(path)

        # 6. Use pandas to read the Excel file into a DataFrame
        #    You can then transform/process the DataFrame as needed
        df = pd.read_excel(path)

        # 7. Record in the database that this file was uploaded
        #    We don’t store the file contents here—just metadata
        up = GivtUpload(filename=fn)
        db.session.add(up)
        db.session.commit()

        # 8. Let the user know we’ve successfully received and processed the file
        flash(f'File "{fn}" uploaded and processed.', 'success')

        # 9. Redirect back to the main page (or wherever you prefer)
        return redirect(url_for('index'))

    # If it’s a GET request, simply show the upload form
    return render_template('upload.html')

if __name__ == '__main__':
    app.run(debug=True)