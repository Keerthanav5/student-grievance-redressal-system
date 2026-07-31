from flask import Flask, render_template, request, redirect, session, flash
import mysql.connector
import re
from config import Config

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY


ACADEMIC_TYPE = "Academic / Class / Studies"
OFFICE_TYPE = "Fees / Library / Canteen / Office"

MAIN_CATEGORY_ACADEMIC = "Academic Issues"
MAIN_CATEGORY_ADMIN = "Administrative Issues"
MAIN_CATEGORY_CAMPUS = "Campus Facility Issues"

MAIN_CATEGORIES = (
    MAIN_CATEGORY_ACADEMIC,
    MAIN_CATEGORY_ADMIN,
    MAIN_CATEGORY_CAMPUS,
)

SUBCATEGORY_MAP = {
    MAIN_CATEGORY_ACADEMIC: (
        "Class Related Issues",
        "Faculty Issues",
        "Examination Problems",
        "Attendance Issues",
        "Internal Marks Issues",
        "Timetable Problems",
    ),
    MAIN_CATEGORY_ADMIN: (
        "Fees Issues",
        "ID Card Issues",
        "Scholarship Issues",
        "Certificate Issues",
        "Admission Issues",
        "Office Delay Problems",
    ),
    MAIN_CATEGORY_CAMPUS: (
        "Library Issues",
        "Canteen Issues",
        "Hostel Issues",
        "Transport Issues",
        "Washroom Cleanliness",
        "Infrastructure Problems",
    ),
}

ASSIGNED_ADMIN = "admin"
ASSIGNED_DEPARTMENT = "department"
ASSIGNED_OFFICE = "office"

STATUS_PENDING = "Pending"
STATUS_IN_PROGRESS = "In Progress"
STATUS_RESOLVED = "Resolved"

DEFAULT_RESOLVED_MESSAGE = "Complaint resolved successfully"

REGISTER_NUMBER_RE = re.compile(r"^[A-Z0-9]{12}$")


def normalize_register_number(value: str) -> str:
    return (value or '').strip().upper()


def is_valid_register_number(value: str) -> bool:
    return bool(REGISTER_NUMBER_RE.fullmatch(normalize_register_number(value)))


def current_role():
    return session.get('role')


def require_role(*roles):
    role = current_role()
    if role in roles:
        return True
    return False


_SCHEMA_READY = False


def ensure_schema():
    conn = db()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            register_number VARCHAR(12) PRIMARY KEY,
            student_name VARCHAR(100) NOT NULL,
            student_password VARCHAR(255) NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute("SHOW COLUMNS FROM students")
    student_cols = {row[0] for row in cursor.fetchall()}

    if 'student_password' not in student_cols:
        cursor.execute(
            "ALTER TABLE students ADD COLUMN student_password VARCHAR(255) NOT NULL DEFAULT ''"
        )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS complaints (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_register_number VARCHAR(12) NOT NULL DEFAULT '',
            student_name VARCHAR(100) NOT NULL,
            complaint_text TEXT NOT NULL,
            complaint_type VARCHAR(80) NOT NULL,
            main_category VARCHAR(80) NOT NULL DEFAULT '',
            sub_category VARCHAR(80) NOT NULL DEFAULT '',
            assigned_to VARCHAR(20) NOT NULL DEFAULT 'admin',
            status VARCHAR(20) NOT NULL DEFAULT 'Pending',
            response_message TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute("SHOW COLUMNS FROM complaints")
    cols = {row[0] for row in cursor.fetchall()}

    # Migrate legacy column names if the table existed previously.
    if 'student_name' not in cols and 'name' in cols:
        cursor.execute("ALTER TABLE complaints CHANGE name student_name VARCHAR(100)")
        cols.add('student_name')

    if 'complaint_text' not in cols and 'issue' in cols:
        cursor.execute("ALTER TABLE complaints CHANGE issue complaint_text TEXT")
        cols.add('complaint_text')

    if 'student_register_number' not in cols:
        cursor.execute(
            "ALTER TABLE complaints ADD COLUMN student_register_number VARCHAR(12) NOT NULL DEFAULT ''"
        )
        cols.add('student_register_number')

    if 'complaint_type' not in cols:
        cursor.execute(
            "ALTER TABLE complaints ADD COLUMN complaint_type VARCHAR(80) NOT NULL DEFAULT %s",
            (ACADEMIC_TYPE,),
        )
        cols.add('complaint_type')

    if 'main_category' not in cols:
        cursor.execute(
            "ALTER TABLE complaints ADD COLUMN main_category VARCHAR(80) NOT NULL DEFAULT ''"
        )
        cols.add('main_category')

    if 'sub_category' not in cols:
        cursor.execute(
            "ALTER TABLE complaints ADD COLUMN sub_category VARCHAR(80) NOT NULL DEFAULT ''"
        )
        cols.add('sub_category')

    if 'assigned_to' not in cols:
        cursor.execute(
            "ALTER TABLE complaints ADD COLUMN assigned_to VARCHAR(20) NOT NULL DEFAULT %s",
            (ASSIGNED_ADMIN,),
        )
        cols.add('assigned_to')

    if 'status' not in cols:
        cursor.execute(
            "ALTER TABLE complaints ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT %s",
            (STATUS_PENDING,),
        )
        cols.add('status')

    if 'response_message' not in cols:
        cursor.execute(
            "ALTER TABLE complaints ADD COLUMN response_message TEXT",
        )
        cols.add('response_message')

    if 'created_at' not in cols:
        cursor.execute(
            "ALTER TABLE complaints ADD COLUMN created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
        )
        cols.add('created_at')

        # Backfill new category columns from legacy complaint_type.
        cursor.execute(
                """
                UPDATE complaints
                SET main_category=%s
                WHERE (main_category IS NULL OR main_category='')
                    AND complaint_type=%s
                """,
                (MAIN_CATEGORY_ACADEMIC, ACADEMIC_TYPE),
        )
        cursor.execute(
                """
                UPDATE complaints
                SET main_category=%s
                WHERE (main_category IS NULL OR main_category='')
                    AND complaint_type=%s
                """,
                (MAIN_CATEGORY_ADMIN, OFFICE_TYPE),
        )

    conn.commit()

    # Backfill registered students from existing complaints so legacy data keeps working.
    # This keeps the project simple while still enforcing uniqueness for new registrations.
    cursor.execute(
        """
        INSERT IGNORE INTO students (register_number, student_name)
        SELECT DISTINCT student_register_number, student_name
        FROM complaints
        WHERE student_register_number IS NOT NULL
          AND student_register_number <> ''
          AND student_name IS NOT NULL
          AND student_name <> ''
        """
    )

    conn.commit()
    conn.close()


def student_register_number_exists(regno: str) -> bool:
    regno = normalize_register_number(regno)
    if not regno:
        return False

    conn = db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM students WHERE register_number=%s LIMIT 1",
        (regno,),
    )
    row = cursor.fetchone()
    conn.close()
    return bool(row)


@app.before_request
def _ensure_schema_once():
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    ensure_schema()
    _SCHEMA_READY = True


@app.route('/')
def home():
    role = current_role()
    if role == 'student':
        return redirect('/student')
    if role == 'department':
        return redirect('/department')
    if role == 'office':
        return redirect('/office')
    if role == 'admin':
        return redirect('/admin')
    return render_template('index.html')


@app.route('/student')
def student_panel():
    if not require_role('student'):
        return redirect('/student_login')
    return redirect('/my_complaints')


@app.route('/student_dashboard')
@app.route('/my_complaints')
def student_dashboard():
    if not require_role('student'):
        return redirect('/student_login')

    regno = (session.get('student_register_number') or '').strip().upper()
    if not regno:
        session.clear()
        return redirect('/student_login')

    conn = db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM complaints WHERE student_register_number=%s ORDER BY id DESC",
        (regno,),
    )
    data = cursor.fetchall()
    conn.close()

    return render_template(
        'student_dashboard.html',
        role=current_role(),
        student_register_number=regno,
        data=data,
    )

def db():
    return mysql.connector.connect(
        host=Config.HOST,
        user=Config.USER,
        password=Config.PASSWORD,
        database=Config.DATABASE
    )


def get_admin_analytics():
    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status=%s THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN status=%s THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN status=%s THEN 1 ELSE 0 END) AS resolved
        FROM complaints
        """,
        (STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_RESOLVED),
    )
    counts = cursor.fetchone() or {}

    cursor.execute(
        """
        SELECT
            SUM(CASE WHEN assigned_to=%s THEN 1 ELSE 0 END) AS department,
            SUM(CASE WHEN assigned_to=%s THEN 1 ELSE 0 END) AS office
        FROM complaints
        """,
        (ASSIGNED_DEPARTMENT, ASSIGNED_OFFICE),
    )
    assigned = cursor.fetchone() or {}

    # Optional: last 12 months trend (works only if created_at is populated)
    cursor.execute(
        """
        SELECT DATE_FORMAT(created_at, '%%Y-%%m') AS ym, COUNT(*) AS cnt
        FROM complaints
        GROUP BY ym
        ORDER BY ym DESC
        LIMIT 12
        """
    )
    trend_rows = cursor.fetchall() or []
    conn.close()

    trend_rows = list(reversed(trend_rows))
    trend_labels = [r.get('ym') for r in trend_rows if r.get('ym')]
    trend_counts = [int(r.get('cnt') or 0) for r in trend_rows if r.get('ym')]

    return {
        'total': int(counts.get('total') or 0),
        'pending': int(counts.get('pending') or 0),
        'in_progress': int(counts.get('in_progress') or 0),
        'resolved': int(counts.get('resolved') or 0),
        'department': int(assigned.get('department') or 0),
        'office': int(assigned.get('office') or 0),
        'trend_labels': trend_labels,
        'trend_counts': trend_counts,
    }

# ADMIN DASHBOARD
@app.route('/admin')
def admin_dashboard():
    if not require_role('admin'):
        return redirect('/admin_login')

    conn = db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM complaints ORDER BY id DESC")
    data = cursor.fetchall()
    conn.close()
    return render_template("admin.html", data=data, role=current_role())


@app.route('/admin/analytics')
def admin_analytics_dashboard():
    if not require_role('admin'):
        return redirect('/admin_login')

    analytics = get_admin_analytics()
    return render_template(
        'admin_analytics.html',
        role=current_role(),
        analytics=analytics,
    )


@app.route('/department')
def department_dashboard():
    if not require_role('department'):
        return redirect('/department_login')

    conn = db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT * FROM complaints
        WHERE assigned_to=%s AND main_category=%s
        ORDER BY id DESC
        """,
        (ASSIGNED_DEPARTMENT, MAIN_CATEGORY_ACADEMIC),
    )
    data = cursor.fetchall()
    conn.close()
    return render_template('department.html', data=data, role=current_role())


@app.route('/office')
def office_dashboard():
    if not require_role('office'):
        return redirect('/office_login')

    conn = db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT * FROM complaints
        WHERE assigned_to=%s AND main_category IN (%s, %s)
        ORDER BY id DESC
        """,
        (ASSIGNED_OFFICE, MAIN_CATEGORY_ADMIN, MAIN_CATEGORY_CAMPUS),
    )
    data = cursor.fetchall()
    conn.close()
    return render_template('office.html', data=data, role=current_role())


@app.route('/login')
def login():
    return redirect('/')


@app.route('/student_login', methods=['GET', 'POST'])
def student_login():
    error = None
    success = None
    if request.method == 'GET' and request.args.get('registered') == '1':
        success = 'Registration completed successfully!!'
    if request.method == 'POST':
        regno = normalize_register_number(request.form.get('register_number'))
        password = request.form.get('password') or ''

        if not regno or not password:
            error = 'Register Number and Password are required.'
        elif not is_valid_register_number(regno):
            error = 'Register number must be exactly 12 characters'
        else:
            conn = db()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT register_number
                FROM students
                WHERE register_number=%s AND student_password=%s
                LIMIT 1
                """,
                (regno, password),
            )
            row = cursor.fetchone()
            conn.close()

            if not row:
                if student_register_number_exists(regno):
                    error = 'Invalid student credentials.'
                else:
                    error = 'Register number not registered. Please register first.'
            else:
                session.clear()
                session['role'] = 'student'
                session['student_register_number'] = regno
                return redirect('/student')

    return render_template(
        'role_login.html',
        role=current_role(),
        page_title='Student Login',
        login_role='student',
        error=error,
        success=success,
    )


@app.route('/student_register', methods=['GET', 'POST'])
def student_register():
    error = None
    success = None

    if request.method == 'POST':
        regno = normalize_register_number(request.form.get('register_number'))
        name = (request.form.get('student_name') or '').strip()

        if not regno or not name:
            error = 'Register Number and Name are required.'
        elif not is_valid_register_number(regno):
            error = 'Register number must be exactly 12 characters'
        elif student_register_number_exists(regno):
            error = 'Register number already exists. Please login.'
        else:
            session['pending_student'] = {
                'register_number': regno,
                'student_name': name,
            }
            return redirect('/student_create_password')

    return render_template(
        'student_register.html',
        role=current_role(),
        page_title='Student Registration',
        error=error,
        success=success,
    )


@app.route('/student_create_password', methods=['GET', 'POST'])
def student_create_password():
    pending = session.get('pending_student') or {}
    regno = normalize_register_number(pending.get('register_number'))
    name = (pending.get('student_name') or '').strip()

    if not regno or not name:
        return redirect('/student_register')

    error = None

    if request.method == 'POST':
        password = (request.form.get('password') or '').strip()
        confirm = (request.form.get('confirm_password') or '').strip()

        if not password or not confirm:
            error = 'Password and Confirm Password are required.'
        elif password != confirm:
            error = 'Passwords do not match.'
        elif student_register_number_exists(regno):
            error = 'Register number already exists. Please login.'
        else:
            conn = db()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO students (register_number, student_name, student_password)
                    VALUES (%s, %s, %s)
                    """,
                    (regno, name, password),
                )
                conn.commit()
                session.pop('pending_student', None)
                return redirect('/student_login?registered=1')
            except mysql.connector.IntegrityError:
                conn.rollback()
                error = 'Register number already exists. Please login.'
            finally:
                conn.close()

    return render_template(
        'student_create_password.html',
        role=current_role(),
        page_title='Create Password',
        register_number=regno,
        student_name=name,
        error=error,
    )


@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''

        if not username or not password:
            error = 'Username and Password are required.'
        elif username != Config.ADMIN_USERNAME or password != Config.ADMIN_PASSWORD:
            error = 'Invalid admin credentials.'
        else:
            session.clear()
            session['role'] = 'admin'
            session['admin_username'] = username
            return redirect('/admin')

    return render_template(
        'role_login.html',
        role=current_role(),
        page_title='Admin Login',
        login_role='admin',
        error=error,
    )


@app.route('/department_login', methods=['GET', 'POST'])
def department_login():
    error = None
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''

        if not username or not password:
            error = 'Username and Password are required.'
        elif username != Config.DEPARTMENT_USERNAME or password != Config.DEPARTMENT_PASSWORD:
            error = 'Invalid department credentials.'
        else:
            session.clear()
            session['role'] = 'department'
            session['department_username'] = username
            return redirect('/department')

    return render_template(
        'role_login.html',
        role=current_role(),
        page_title='Department Login',
        login_role='department',
        error=error,
    )


@app.route('/office_login', methods=['GET', 'POST'])
def office_login():
    error = None
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''

        if not username or not password:
            error = 'Username and Password are required.'
        elif username != Config.OFFICE_USERNAME or password != Config.OFFICE_PASSWORD:
            error = 'Invalid office credentials.'
        else:
            session.clear()
            session['role'] = 'office'
            session['office_username'] = username
            return redirect('/office')

    return render_template(
        'role_login.html',
        role=current_role(),
        page_title='Office Management Login',
        login_role='office',
        error=error,
    )


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ADD COMPLAINT
@app.route('/add', methods=['GET','POST'])
def add():
    if current_role() in ('admin', 'department', 'office'):
        return redirect('/')

    if not require_role('student'):
        return redirect('/student_login')

    if request.method == 'POST':
        regno = (session.get('student_register_number') or '').strip().upper()
        if not regno:
            session.clear()
            return redirect('/student_login')

        name = (request.form.get('name') or '').strip()
        issue = (request.form.get('issue') or '').strip()
        main_category = (request.form.get('main_category') or '').strip()
        sub_category = (request.form.get('sub_category') or '').strip()

        if main_category not in MAIN_CATEGORIES:
            flash('Please select a valid main category.')
            return redirect('/add')

        valid_subcategories = SUBCATEGORY_MAP.get(main_category, ())
        if sub_category not in valid_subcategories:
            flash('Please select a valid sub-category.')
            return redirect('/add')

        complaint_type = main_category

        assigned_to = ASSIGNED_ADMIN

        conn = db()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO complaints (
                student_register_number,
                student_name,
                complaint_text,
                complaint_type,
                main_category,
                sub_category,
                assigned_to,
                status,
                response_message
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                regno,
                name,
                issue,
                complaint_type,
                main_category,
                sub_category,
                assigned_to,
                STATUS_PENDING,
                '',
            ),
        )

        conn.commit()
        conn.close()

        flash(f'Hey {name}, complaint registered successfully')

        return redirect('/my_complaints')

    return render_template(
        "add.html",
        role=current_role(),
        main_categories=MAIN_CATEGORIES,
        subcategory_map=SUBCATEGORY_MAP,
    )

@app.route('/resolve/<int:id>')
def resolve(id):
    role = current_role()
    if role not in ('admin', 'department', 'office'):
        return redirect('/')

    conn = db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, assigned_to, status, response_message FROM complaints WHERE id=%s", (id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return redirect('/')

    if role == 'department' and row.get('assigned_to') != ASSIGNED_DEPARTMENT:
        conn.close()
        return redirect('/department')

    if role == 'office' and row.get('assigned_to') != ASSIGNED_OFFICE:
        conn.close()
        return redirect('/office')

    resolved_message = row.get('response_message') or ''
    if not resolved_message.strip():
        resolved_message = DEFAULT_RESOLVED_MESSAGE

    cursor2 = conn.cursor()
    cursor2.execute(
        "UPDATE complaints SET status=%s, response_message=%s WHERE id=%s",
        (STATUS_RESOLVED, resolved_message, id),
    )
    conn.commit()
    conn.close()

    if role == 'department':
        return redirect('/department')
    if role == 'office':
        return redirect('/office')
    return redirect('/admin')


@app.route('/assign/<int:id>/<string:target>')
def assign(id, target):
    if not require_role('admin'):
        return redirect('/admin_login')

    target = (target or '').strip().lower()
    if target not in (ASSIGNED_DEPARTMENT, ASSIGNED_OFFICE):
        return redirect('/admin')

    conn = db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, status, assigned_to, main_category FROM complaints WHERE id=%s",
        (id,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return redirect('/admin')

    main_category = (row.get('main_category') or '').strip()
    if main_category == MAIN_CATEGORY_ACADEMIC and target != ASSIGNED_DEPARTMENT:
        conn.close()
        return redirect('/admin')
    if main_category in (MAIN_CATEGORY_ADMIN, MAIN_CATEGORY_CAMPUS) and target != ASSIGNED_OFFICE:
        conn.close()
        return redirect('/admin')

    # Allow assignment only once.
    assigned_to = (row.get('assigned_to') or '').strip().lower()
    if assigned_to and assigned_to not in (ASSIGNED_ADMIN, target):
        conn.close()
        return redirect('/admin')

    if row.get('status') == STATUS_RESOLVED:
        conn.close()
        return redirect('/admin')

    cursor2 = conn.cursor()
    cursor2.execute(
        "UPDATE complaints SET assigned_to=%s, status=%s WHERE id=%s",
        (target, STATUS_IN_PROGRESS, id),
    )
    conn.commit()
    conn.close()
    return redirect('/admin')


@app.route('/complaint_action/<int:id>', methods=['POST'])
def complaint_action(id):
    role = current_role()
    if role not in ('department', 'office'):
        return redirect('/')

    action = (request.form.get('action') or '').strip().lower()
    message = (request.form.get('response_message') or '').strip()

    conn = db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, assigned_to, status, response_message FROM complaints WHERE id=%s",
        (id,),
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return redirect('/department' if role == 'department' else '/office')

    if role == 'department' and row.get('assigned_to') != ASSIGNED_DEPARTMENT:
        conn.close()
        return redirect('/department')

    if role == 'office' and row.get('assigned_to') != ASSIGNED_OFFICE:
        conn.close()
        return redirect('/office')

    if action == 'resolve':
        if not message:
            message = row.get('response_message') or ''
        if not message.strip():
            message = DEFAULT_RESOLVED_MESSAGE

        cursor2 = conn.cursor()
        cursor2.execute(
            "UPDATE complaints SET status=%s, response_message=%s WHERE id=%s",
            (STATUS_RESOLVED, message, id),
        )
        conn.commit()
        conn.close()
        return redirect('/department' if role == 'department' else '/office')

    if action == 'update':
        if not message:
            conn.close()
            return redirect('/department' if role == 'department' else '/office')

        cursor2 = conn.cursor()
        cursor2.execute(
            "UPDATE complaints SET status=%s, response_message=%s WHERE id=%s",
            (STATUS_IN_PROGRESS, message, id),
        )
        conn.commit()
        conn.close()
        return redirect('/department' if role == 'department' else '/office')

    conn.close()
    return redirect('/department' if role == 'department' else '/office')

# DELETE
@app.route('/delete/<int:id>')
def delete(id):
    if not require_role('admin'):
        return redirect('/admin_login')

    conn = db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM complaints WHERE id=%s", (id,))
    conn.commit()
    conn.close()

    return redirect('/admin')

if __name__ == '__main__':
    app.run(debug=True)