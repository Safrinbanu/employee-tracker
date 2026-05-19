from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, redirect, session, flash
from pymongo import MongoClient
import os

app = Flask(__name__)
app.secret_key = "employee_secret_key"

# =========================
# MONGODB CONFIG
# =========================

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["employee_tracker"]

employees_col = db["employees"]
updates_col = db["daily_updates"]
attendance_col = db["attendance"]

employees_col.create_index("email", unique=True)


# =========================
# HELPERS
# =========================

def get_today_str():
    return datetime.now().strftime("%Y-%m-%d")


def format_time(dt):
    if dt is None:
        return "--:--"
    return dt.strftime("%H:%M")


def calc_hours(check_in, check_out):
    if check_in is None or check_out is None:
        return "0h 00m"
    diff = check_out - check_in
    total_minutes = int(diff.total_seconds() // 60)
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{h}h {m:02d}m"


# =========================
# ROUTES
# =========================

@app.route('/')
def home():
    return render_template('login.html')


@app.route('/admin/add-employee', methods=['GET', 'POST'])
def admin_add_employee():
    if 'admin' not in session:
        return redirect('/admin')
    if request.method == 'POST':
        try:
            employees_col.insert_one({
                "name": request.form['name'],
                "email": request.form['email'],
                "password": request.form['password']
            })
            flash("Employee registered successfully!")
            return redirect('/admin-dashboard')
        except Exception:
            return render_template('add_employee.html', error="Email already registered.")
    return render_template('add_employee.html')


@app.route('/login', methods=['POST'])
def login():
    employee = employees_col.find_one({
        "email": request.form['email'],
        "password": request.form['password']
    })
    if employee:
        session['employee_name'] = employee['name']
        return redirect('/dashboard')
    return render_template('login.html', error="Invalid Email or Password")


@app.route('/dashboard')
def dashboard():
    if 'employee_name' not in session:
        return redirect('/')

    emp_name = session['employee_name']
    employee = employees_col.find_one({"name": emp_name})

    total_updates = updates_col.count_documents({"employee_name": emp_name})
    total_attendance = attendance_col.count_documents({"employee_name": emp_name})

    today_str = get_today_str()
    today_record = attendance_col.find_one({"employee_name": emp_name, "date": today_str})

    check_in_time = "--:--"
    check_out_time = "--:--"
    hours_worked = "0h 00m"
    today_status = "Not Checked In"

    if today_record:
        check_in_time = format_time(today_record.get("check_in"))
        check_out_time = format_time(today_record.get("check_out"))
        hours_worked = calc_hours(today_record.get("check_in"), today_record.get("check_out"))
        today_status = today_record.get("status", "Half Day")

    return render_template(
        'dashboard.html',
        name=emp_name,
        employee=employee,
        total_updates=total_updates,
        total_attendance=total_attendance,
        check_in_time=check_in_time,
        check_out_time=check_out_time,
        hours_worked=hours_worked,
        today_status=today_status
    )


@app.route('/check-in', methods=['POST'])
def check_in():
    if 'employee_name' not in session:
        return redirect('/')

    emp_name = session['employee_name']
    today_str = get_today_str()

    existing = attendance_col.find_one({"employee_name": emp_name, "date": today_str})
    if existing:
        flash("You have already checked in today.")
        return redirect('/dashboard')

    attendance_col.insert_one({
        "employee_name": emp_name,
        "status": "Half Day",
        "check_in": datetime.now(),
        "check_out": None,
        "date": today_str
    })

    flash("Checked in successfully!")
    return redirect('/dashboard')


@app.route('/check-out', methods=['POST'])
def check_out():
    if 'employee_name' not in session:
        return redirect('/')

    emp_name = session['employee_name']
    today_str = get_today_str()

    record = attendance_col.find_one({"employee_name": emp_name, "date": today_str})

    if not record:
        flash("No check-in found for today. Please check in first.")
        return redirect('/dashboard')

    if record.get("check_out"):
        flash("You have already checked out today.")
        return redirect('/dashboard')

    now = datetime.now()
    attendance_col.update_one(
        {"_id": record["_id"]},
        {"$set": {"check_out": now, "status": "Present"}}
    )

    flash("Checked out successfully!")
    return redirect('/dashboard')


@app.route('/attendance')
def attendance():
    if 'employee_name' not in session:
        return redirect('/')

    emp_name = session['employee_name']
    records_cursor = attendance_col.find({"employee_name": emp_name}).sort("date", -1)

    records = []
    for r in records_cursor:
        records.append({
            "date": r.get("date", ""),
            "status": r.get("status", ""),
            "check_in": format_time(r.get("check_in")),
            "check_out": format_time(r.get("check_out")),
            "hours": calc_hours(r.get("check_in"), r.get("check_out"))
        })

    return render_template('attendance.html', attendance=records)


@app.route('/add-update', methods=['GET', 'POST'])
def add_update():
    if 'employee_name' not in session:
        return redirect('/')

    if request.method == 'POST':
        updates_col.insert_one({
            "employee_name": session['employee_name'],
            "work_update": request.form['work_update'],
            "date": datetime.now()
        })
        flash("Update submitted successfully!")
        return redirect('/updates')

    return render_template('add_update.html')


@app.route('/updates')
def updates():
    if 'employee_name' not in session:
        return redirect('/')

    data_cursor = updates_col.find({"employee_name": session['employee_name']}).sort("date", -1)
    data = list(data_cursor)
    return render_template('updates.html', updates=data)


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == 'admin123':
            session['admin'] = True
            return redirect('/admin-dashboard')
        return render_template('admin_login.html', error="Invalid Admin Login")
    return render_template('admin_login.html')


@app.route('/admin-dashboard')
def admin_dashboard():
    if 'admin' not in session:
        return redirect('/admin')

    updates_list = list(updates_col.find().sort("date", -1))
    return render_template('admin_dashboard.html', updates=updates_list)


@app.route('/admin-attendance')
def admin_attendance():
    if 'admin' not in session:
        return redirect('/admin')

    search = request.args.get('search', '')
    date_filter = request.args.get('date', '')

    query = {}
    if search:
        query["employee_name"] = {"$regex": search, "$options": "i"}
    if date_filter:
        query["date"] = date_filter

    records_cursor = attendance_col.find(query).sort("date", -1)
    records = []
    for r in records_cursor:
        records.append({
            "employee_name": r.get("employee_name", ""),
            "date": r.get("date", ""),
            "status": r.get("status", ""),
            "check_in": format_time(r.get("check_in")),
            "check_out": format_time(r.get("check_out")),
            "hours": calc_hours(r.get("check_in"), r.get("check_out"))
        })

    total_records = attendance_col.count_documents({})
    present_count = attendance_col.count_documents({"status": "Present"})
    half_day_count = attendance_col.count_documents({"status": "Half Day"})
    pending_checkout = attendance_col.count_documents({"check_out": None})

    return render_template(
        'admin_attendance.html',
        attendance=records,
        total_records=total_records,
        present_count=present_count,
        half_day_count=half_day_count,
        pending_checkout=pending_checkout
    )


@app.route('/admin-logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/admin')


@app.route('/logout')
def logout():
    session.pop('employee_name', None)
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=True)
