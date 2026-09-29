import os
import sqlite3
import hashlib
import uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, send_from_directory
)
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cloud_portal_dev_key_2024")

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'uploads')
ALLOWED_EXT   = {'pdf', 'doc', 'docx', 'txt', 'py', 'java', 'zip', 'png', 'jpg'}
MAX_FILE_MB   = 10
DB_PATH       = os.path.join(os.path.dirname(__file__), '..', 'portal.db')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_MB * 1024 * 1024


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id    TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            email      TEXT UNIQUE NOT NULL,
            password   TEXT NOT NULL,
            role       TEXT NOT NULL CHECK(role IN ('student','teacher','admin')),
            avatar     TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS courses (
            course_id   TEXT PRIMARY KEY,
            course_name TEXT NOT NULL,
            course_code TEXT NOT NULL,
            teacher_id  TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (teacher_id) REFERENCES users(user_id)
        );
        CREATE TABLE IF NOT EXISTS enrollments (
            enrollment_id TEXT PRIMARY KEY,
            course_id     TEXT NOT NULL,
            student_id    TEXT NOT NULL,
            enrolled_at   TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (course_id)  REFERENCES courses(course_id),
            FOREIGN KEY (student_id) REFERENCES users(user_id),
            UNIQUE(course_id, student_id)
        );
        CREATE TABLE IF NOT EXISTS assignments (
            assignment_id  TEXT PRIMARY KEY,
            course_id      TEXT NOT NULL,
            title          TEXT NOT NULL,
            description    TEXT DEFAULT '',
            deadline       TEXT NOT NULL,
            max_marks      INTEGER DEFAULT 100,
            allow_resubmit INTEGER DEFAULT 1,
            created_by     TEXT NOT NULL,
            created_at     TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (course_id)  REFERENCES courses(course_id),
            FOREIGN KEY (created_by) REFERENCES users(user_id)
        );
        CREATE TABLE IF NOT EXISTS submissions (
            submission_id TEXT PRIMARY KEY,
            assignment_id TEXT NOT NULL,
            student_id    TEXT NOT NULL,
            file_name     TEXT NOT NULL,
            storage_path  TEXT NOT NULL,
            file_size_kb  INTEGER DEFAULT 0,
            submitted_at  TEXT DEFAULT (datetime('now')),
            status        TEXT DEFAULT 'submitted',
            marks         INTEGER,
            feedback      TEXT DEFAULT '',
            graded_at     TEXT,
            FOREIGN KEY (assignment_id) REFERENCES assignments(assignment_id),
            FOREIGN KEY (student_id)    REFERENCES users(user_id)
        );
        CREATE TABLE IF NOT EXISTS notifications (
            notif_id   TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL,
            message    TEXT NOT NULL,
            is_read    INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
    """)
    db.commit()
    _seed_demo_data(db)
    db.close()


def _seed_demo_data(db):
    existing = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing > 0:
        return

    def uid(): return str(uuid.uuid4())[:8]
    def pw(p): return hashlib.sha256(p.encode()).hexdigest()

    teacher_id  = "teacher01"
    teacher2_id = "teacher02"
    students    = ["student01","student02","student03","student04"]

    db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,datetime('now'))",
        (teacher_id,"Dr. Priya Sharma","priya@college.edu",pw("teacher123"),"teacher","👩‍🏫"))
    db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,datetime('now'))",
        (teacher2_id,"Prof. Rahul Mehta","rahul@college.edu",pw("teacher123"),"teacher","👨‍🏫"))

    student_data = [
        ("student01","Neha Joshi",   "neha@student.edu",   "🧑‍💻"),
        ("student02","Arjun Singh",  "arjun@student.edu",  "👨‍🎓"),
        ("student03","Priya Patel",  "priya2@student.edu", "👩‍🎓"),
        ("student04","Rohan Kumar",  "rohan@student.edu",  "🧑‍🎓"),
    ]
    for sid, name, email, av in student_data:
        db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,datetime('now'))",
            (sid, name, email, pw("student123"), "student", av))

    db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,datetime('now'))",
        ("admin01","Admin User","admin@college.edu",pw("admin123"),"admin","⚙️"))

    courses = [
        ("CLD101","Cloud Computing",   "CC-101", teacher_id,  "Learn cloud architecture, AWS, GCP, and Azure"),
        ("PY201", "Python Programming","PY-201", teacher_id,  "Advanced Python with OOP, Flask, and APIs"),
        ("DB301", "Database Systems",  "DB-301", teacher2_id, "SQL, NoSQL, and cloud database design"),
        ("WD401", "Web Development",   "WD-401", teacher2_id, "Full-stack development with React and Node"),
    ]
    for cid, name, code, tid, desc in courses:
        db.execute("INSERT INTO courses VALUES (?,?,?,?,?,datetime('now'))",
            (cid, name, code, tid, desc))

    for sid in students:
        for cid, _, _, _, _ in courses:
            db.execute("INSERT INTO enrollments VALUES (?,?,?,datetime('now'))",
                (uid(), cid, sid))

    now     = datetime.now()
    future1 = (now + timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
    future2 = (now + timedelta(days=14)).strftime("%Y-%m-%d %H:%M")
    past1   = (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    past2   = (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M")

    assignments = [
        ("ASG001","CLD101","Cloud Architecture Report",
         "Design a 3-tier cloud architecture using AWS.",
         future1, 100, 1, teacher_id),
        ("ASG002","CLD101","Docker & Kubernetes Lab",
         "Containerize a Flask app using Docker and deploy on Kubernetes.",
         future2, 50, 1, teacher_id),
        ("ASG003","PY201","REST API Project",
         "Build a complete REST API using Flask with authentication and CRUD.",
         past1, 100, 1, teacher_id),
        ("ASG004","PY201","Python OOP Assignment",
         "Implement a library management system using Python OOP.",
         past2, 75, 0, teacher_id),
        ("ASG005","DB301","Database Design Project",
         "Design a hospital management database with ER diagram.",
         future1, 100, 1, teacher2_id),
        ("ASG006","WD401","Full Stack Mini Project",
         "Build a full-stack to-do app with React and Flask.",
         future2, 100, 1, teacher2_id),
    ]
    for a in assignments:
        db.execute("INSERT INTO assignments VALUES (?,?,?,?,?,?,?,?,datetime('now'))", a)

    subs = [
        ("SUB001","ASG003","student01","rest_api_neha.zip",
         "rest_api_neha.zip", 245,
         (now-timedelta(days=5)).isoformat(), "graded", 88,
         "Excellent work! API structure is clean. Add more error handling.", 
         (now-timedelta(days=2)).isoformat()),
        ("SUB002","ASG004","student01","library_oop_neha.py",
         "library_oop_neha.py", 12,
         (now-timedelta(days=8)).isoformat(), "graded", 70,
         "Good implementation. The Librarian class needs more methods.",
         (now-timedelta(days=6)).isoformat()),
        ("SUB003","ASG003","student02","api_project_arjun.zip",
         "api_project_arjun.zip", 198,
         (now-timedelta(days=4)).isoformat(), "submitted", None, "", None),
        ("SUB004","ASG004","student02","oop_arjun.py",
         "oop_arjun.py", 8,
         (now-timedelta(days=9)).isoformat(), "graded", 65,
         "Needs improvement in encapsulation.",
         (now-timedelta(days=5)).isoformat()),
        ("SUB005","ASG003","student03","flask_api_priya.zip",
         "flask_api_priya.zip", 310,
         (now-timedelta(days=3)).isoformat(), "submitted", None, "", None),
    ]
    for s in subs:
        db.execute("INSERT INTO submissions VALUES (?,?,?,?,?,?,?,?,?,?,?)", s)

    notifs = [
        (uid(),"student01","📝 New assignment: Cloud Architecture Report (Due in 7 days)",0),
        (uid(),"student01","✅ Your REST API Project has been graded — Score: 88/100",0),
        (uid(),"student01","📢 New assignment: Docker & Kubernetes Lab posted",0),
        (uid(),"student02","📝 New assignment: Cloud Architecture Report (Due in 7 days)",0),
        (uid(),"student02","✅ Python OOP Assignment graded — Score: 65/75",0),
        (uid(),"teacher01","📥 3 new submissions for REST API Project",0),
        (uid(),"teacher01","📥 Arjun Singh submitted Docker Lab",0),
    ]
    for n in notifs:
        db.execute("INSERT INTO notifications VALUES (?,?,?,?,datetime('now'))", n)

    db.commit()


# ── Auth helpers ──────────────────────────────────────────────
def hash_pw(p):
    return hashlib.sha256(p.encode()).hexdigest()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get('role') not in roles:
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ══════════════════════════════════════════════════════════════
#  AUTH ROUTES
# ══════════════════════════════════════════════════════════════
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        db       = get_db()
        user     = db.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (email, hash_pw(password))
        ).fetchone()
        db.close()
        if user:
            session['user_id'] = user['user_id']
            session['name']    = user['name']
            session['role']    = user['role']
            session['avatar']  = user['avatar']
            return redirect(url_for('dashboard'))
        return render_template('index.html', error="Invalid email or password", page="login")
    return render_template('index.html', page="login")


@app.route('/register', methods=['POST'])
def register():
    name     = request.form.get('name', '').strip()
    email    = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    role     = request.form.get('role', 'student')

    if not name or not email or not password:
        return render_template('index.html', reg_error="All fields required", page="register")

    db = get_db()
    existing = db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone()
    if existing:
        db.close()
        return render_template('index.html', reg_error="Email already registered", page="register")

    new_id = str(uuid.uuid4())[:8]
    db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,datetime('now'))",
        (new_id, name, email, hash_pw(password), role, "👤"))
    db.commit()
    db.close()
    return redirect(url_for('login'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ══════════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════════
@app.route('/dashboard')
@login_required
def dashboard():
    db   = get_db()
    uid  = session['user_id']
    role = session['role']

    notifs = db.execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
        (uid,)
    ).fetchall()
    unread = sum(1 for n in notifs if not n['is_read'])

    if role == 'student':
        data = _student_dashboard(db, uid)
    elif role == 'teacher':
        data = _teacher_dashboard(db, uid)
    else:
        data = _admin_dashboard(db)

    db.close()
    now_str = datetime.now().isoformat()

    return render_template('index.html',
        page="dashboard", data=data,
        notifs=notifs, unread=unread,
        now_str=now_str)


def _student_dashboard(db, uid):
    courses = db.execute("""
        SELECT c.*, u.name as teacher_name
        FROM courses c
        JOIN enrollments e ON c.course_id = e.course_id
        JOIN users u ON c.teacher_id = u.user_id
        WHERE e.student_id = ?
    """, (uid,)).fetchall()

    assignments = db.execute("""
        SELECT a.*, c.course_name, c.course_code,
               s.submission_id, s.status, s.marks,
               s.submitted_at, s.feedback
        FROM assignments a
        JOIN courses c ON a.course_id = c.course_id
        JOIN enrollments e ON c.course_id = e.course_id
        LEFT JOIN submissions s
            ON a.assignment_id = s.assignment_id
            AND s.student_id = ?
        WHERE e.student_id = ?
        ORDER BY a.deadline ASC
    """, (uid, uid)).fetchall()

    now = datetime.now()
    pending   = sum(1 for a in assignments
                    if not a['submission_id']
                    and datetime.fromisoformat(a['deadline']) > now)
    submitted = sum(1 for a in assignments if a['submission_id'])
    graded    = sum(1 for a in assignments if a['status'] == 'graded')
    overdue   = sum(1 for a in assignments
                    if not a['submission_id']
                    and datetime.fromisoformat(a['deadline']) < now)

    grades = db.execute("""
        SELECT s.marks, a.max_marks, a.title, c.course_name
        FROM submissions s
        JOIN assignments a ON s.assignment_id = a.assignment_id
        JOIN courses c ON a.course_id = c.course_id
        WHERE s.student_id = ? AND s.marks IS NOT NULL
    """, (uid,)).fetchall()

    avg_score = 0
    if grades:
        avg_score = round(sum(g['marks'] for g in grades) / len(grades), 1)

    return {
        "role":        "student",
        "courses":     [dict(c) for c in courses],
        "assignments": [dict(a) for a in assignments],
        "stats":       {
            "pending":   pending,
            "submitted": submitted,
            "graded":    graded,
            "overdue":   overdue
        },
        "grades":    [dict(g) for g in grades],
        "avg_score": avg_score,
    }


def _teacher_dashboard(db, uid):
    courses = db.execute(
        "SELECT * FROM courses WHERE teacher_id=?", (uid,)
    ).fetchall()

    assignments = db.execute("""
        SELECT a.*, c.course_name,
               COUNT(DISTINCT s.submission_id) as sub_count,
               COUNT(DISTINCT e.student_id)    as student_count,
               COUNT(CASE WHEN s.marks IS NOT NULL THEN 1 END) as graded_count
        FROM assignments a
        JOIN courses c ON a.course_id = c.course_id
        LEFT JOIN enrollments e ON c.course_id = e.course_id
        LEFT JOIN submissions s ON a.assignment_id = s.assignment_id
        WHERE a.created_by = ?
        GROUP BY a.assignment_id
        ORDER BY a.deadline ASC
    """, (uid,)).fetchall()

    total_students = db.execute("""
        SELECT COUNT(DISTINCT e.student_id) FROM enrollments e
        JOIN courses c ON e.course_id = c.course_id
        WHERE c.teacher_id = ?
    """, (uid,)).fetchone()[0]

    pending_grading = db.execute("""
        SELECT COUNT(*) FROM submissions s
        JOIN assignments a ON s.assignment_id = a.assignment_id
        WHERE a.created_by = ? AND s.marks IS NULL
    """, (uid,)).fetchone()[0]

    return {
        "role":            "teacher",
        "courses":         [dict(c) for c in courses],
        "assignments":     [dict(a) for a in assignments],
        "total_students":  total_students,
        "pending_grading": pending_grading,
    }


def _admin_dashboard(db):
    stats = {
        "total_users":       db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "total_students":    db.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0],
        "total_teachers":    db.execute("SELECT COUNT(*) FROM users WHERE role='teacher'").fetchone()[0],
        "total_courses":     db.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
        "total_assignments": db.execute("SELECT COUNT(*) FROM assignments").fetchone()[0],
        "total_submissions": db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0],
    }
    users = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    return {"role": "admin", "stats": stats, "users": [dict(u) for u in users]}


# ══════════════════════════════════════════════════════════════
#  ASSIGNMENTS
# ══════════════════════════════════════════════════════════════
@app.route('/assignments')
@login_required
def assignments():
    db   = get_db()
    uid  = session['user_id']
    role = session['role']

    if role == 'student':
        rows = db.execute("""
            SELECT a.*, c.course_name, c.course_code,
                   s.submission_id, s.status, s.marks,
                   s.submitted_at, s.feedback
            FROM assignments a
            JOIN courses c ON a.course_id = c.course_id
            JOIN enrollments e ON c.course_id = e.course_id
            LEFT JOIN submissions s
                ON a.assignment_id = s.assignment_id
                AND s.student_id = ?
            WHERE e.student_id = ?
            ORDER BY a.deadline ASC
        """, (uid, uid)).fetchall()

        courses = db.execute("""
            SELECT c.* FROM courses c
            JOIN enrollments e ON c.course_id = e.course_id
            WHERE e.student_id = ?
        """, (uid,)).fetchall()

    else:
        rows = db.execute("""
            SELECT a.*, c.course_name, c.course_code,
                   COUNT(DISTINCT s.submission_id) as sub_count
            FROM assignments a
            JOIN courses c ON a.course_id = c.course_id
            LEFT JOIN submissions s ON a.assignment_id = s.assignment_id
            WHERE a.created_by = ?
            GROUP BY a.assignment_id
            ORDER BY a.deadline ASC
        """, (uid,)).fetchall()

        courses = db.execute(
            "SELECT * FROM courses WHERE teacher_id=?", (uid,)
        ).fetchall()

    unread = db.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
        (uid,)
    ).fetchone()[0]

    db.close()
    now_str = datetime.now().isoformat()

    return render_template('index.html',
        page="assignments",
        assignments=[dict(r) for r in rows],
        courses=[dict(c) for c in courses],
        unread=unread,
        now_str=now_str)


@app.route('/assignments/create', methods=['POST'])
@login_required
@role_required('teacher')
def create_assignment():
    db  = get_db()
    aid = str(uuid.uuid4())[:8]
    db.execute(
        "INSERT INTO assignments VALUES (?,?,?,?,?,?,?,?,datetime('now'))",
        (
            aid,
            request.form['course_id'],
            request.form['title'],
            request.form['description'],
            request.form['deadline'],
            int(request.form.get('max_marks', 100)),
            1 if request.form.get('allow_resubmit') else 0,
            session['user_id']
        )
    )
    students = db.execute(
        "SELECT student_id FROM enrollments WHERE course_id=?",
        (request.form['course_id'],)
    ).fetchall()
    for s in students:
        db.execute(
            "INSERT INTO notifications VALUES (?,?,?,?,datetime('now'))",
            (str(uuid.uuid4())[:8], s['student_id'],
             f"📝 New assignment: {request.form['title']}", 0)
        )
    db.commit()
    db.close()
    return redirect(url_for('assignments'))


# ══════════════════════════════════════════════════════════════
#  SUBMISSIONS
# ══════════════════════════════════════════════════════════════
@app.route('/submit/<assignment_id>', methods=['POST'])
@login_required
@role_required('student')
def submit_assignment(assignment_id):
    db  = get_db()
    uid = session['user_id']

    asgn = db.execute(
        "SELECT * FROM assignments WHERE assignment_id=?", (assignment_id,)
    ).fetchone()

    if not asgn:
        db.close()
        return jsonify({"error": "Assignment not found"}), 404

    if datetime.fromisoformat(asgn['deadline']) < datetime.now():
        db.close()
        return jsonify({"error": "Deadline has passed"}), 400

    existing = db.execute(
        "SELECT * FROM submissions WHERE assignment_id=? AND student_id=?",
        (assignment_id, uid)
    ).fetchone()

    if existing and not asgn['allow_resubmit']:
        db.close()
        return jsonify({"error": "Resubmission not allowed"}), 400

    if 'file' not in request.files:
        db.close()
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files['file']
    if not f.filename or not allowed_file(f.filename):
        db.close()
        return jsonify({"error": "Invalid file type"}), 400

    safe_name    = secure_filename(f.filename)
    storage_name = f"{uid}_{assignment_id}_{safe_name}"
    save_path    = os.path.join(app.config['UPLOAD_FOLDER'], storage_name)
    f.save(save_path)
    file_size = os.path.getsize(save_path) // 1024

    if existing:
        db.execute("""
            UPDATE submissions
            SET file_name=?, storage_path=?, file_size_kb=?,
                submitted_at=datetime('now'), status='submitted',
                marks=NULL, feedback='', graded_at=NULL
            WHERE assignment_id=? AND student_id=?
        """, (safe_name, storage_name, file_size, assignment_id, uid))
    else:
        sid = str(uuid.uuid4())[:8]
        db.execute(
            "INSERT INTO submissions VALUES (?,?,?,?,?,?,datetime('now'),'submitted',NULL,'',NULL)",
            (sid, assignment_id, uid, safe_name, storage_name, file_size)
        )

    db.execute(
        "INSERT INTO notifications VALUES (?,?,?,?,datetime('now'))",
        (str(uuid.uuid4())[:8], asgn['created_by'],
         f"📥 {session['name']} submitted {asgn['title']}", 0)
    )
    db.commit()
    db.close()
    return jsonify({"success": True, "message": "Submitted successfully!"})


@app.route('/submissions/<assignment_id>')
@login_required
@role_required('teacher')
def view_submissions(assignment_id):
    db  = get_db()
    uid = session['user_id']

    asgn = db.execute("""
        SELECT a.*, c.course_name FROM assignments a
        JOIN courses c ON a.course_id = c.course_id
        WHERE a.assignment_id=?
    """, (assignment_id,)).fetchone()

    subs = db.execute("""
        SELECT s.*, u.name as student_name, u.email as student_email, u.avatar
        FROM submissions s
        JOIN users u ON s.student_id = u.user_id
        WHERE s.assignment_id=?
        ORDER BY s.submitted_at DESC
    """, (assignment_id,)).fetchall()

    not_submitted = db.execute("""
        SELECT u.name, u.email FROM users u
        JOIN enrollments e ON u.user_id = e.student_id
        WHERE e.course_id=? AND u.user_id NOT IN (
            SELECT student_id FROM submissions WHERE assignment_id=?
        )
    """, (asgn['course_id'], assignment_id)).fetchall()

    unread = db.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (uid,)
    ).fetchone()[0]

    db.close()
    return render_template('index.html',
        page="submissions",
        assignment=dict(asgn),
        submissions=[dict(s) for s in subs],
        not_submitted=[dict(n) for n in not_submitted],
        unread=unread)


@app.route('/grade/<submission_id>', methods=['POST'])
@login_required
@role_required('teacher')
def grade_submission(submission_id):
    marks    = request.form.get('marks')
    feedback = request.form.get('feedback', '').strip()
    db       = get_db()

    sub = db.execute(
        "SELECT * FROM submissions WHERE submission_id=?", (submission_id,)
    ).fetchone()

    db.execute("""
        UPDATE submissions
        SET marks=?, feedback=?, graded_at=datetime('now'), status='graded'
        WHERE submission_id=?
    """, (int(marks), feedback, submission_id))

    asgn = db.execute(
        "SELECT title FROM assignments WHERE assignment_id=?",
        (sub['assignment_id'],)
    ).fetchone()

    db.execute(
        "INSERT INTO notifications VALUES (?,?,?,?,datetime('now'))",
        (str(uuid.uuid4())[:8], sub['student_id'],
         f"✅ {asgn['title']} graded — Score: {marks}", 0)
    )
    db.commit()
    db.close()
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/download/<storage_path>')
@login_required
def download_file(storage_path):
    return send_from_directory(app.config['UPLOAD_FOLDER'],
                               storage_path, as_attachment=True)


# ══════════════════════════════════════════════════════════════
#  API ENDPOINTS
# ══════════════════════════════════════════════════════════════
@app.route('/api/notifications/read', methods=['POST'])
@login_required
def mark_notifications_read():
    db = get_db()
    db.execute(
        "UPDATE notifications SET is_read=1 WHERE user_id=?",
        (session['user_id'],)
    )
    db.commit()
    db.close()
    return jsonify({"success": True})


@app.route('/api/stats')
@login_required
def api_stats():
    db  = get_db()
    uid = session['user_id']

    if session['role'] == 'teacher':
        subs_by_day = db.execute("""
            SELECT DATE(s.submitted_at) as day, COUNT(*) as count
            FROM submissions s
            JOIN assignments a ON s.assignment_id = a.assignment_id
            WHERE a.created_by = ?
            GROUP BY DATE(s.submitted_at)
            ORDER BY day ASC LIMIT 14
        """, (uid,)).fetchall()

        grade_dist = db.execute("""
            SELECT
                CASE
                    WHEN CAST(s.marks AS FLOAT)/a.max_marks*100 >= 90 THEN 'A (90-100)'
                    WHEN CAST(s.marks AS FLOAT)/a.max_marks*100 >= 75 THEN 'B (75-89)'
                    WHEN CAST(s.marks AS FLOAT)/a.max_marks*100 >= 60 THEN 'C (60-74)'
                    WHEN CAST(s.marks AS FLOAT)/a.max_marks*100 >= 40 THEN 'D (40-59)'
                    ELSE 'F (<40)'
                END as grade, COUNT(*) as count
            FROM submissions s
            JOIN assignments a ON s.assignment_id = a.assignment_id
            WHERE a.created_by = ? AND s.marks IS NOT NULL
            GROUP BY grade
        """, (uid,)).fetchall()

        db.close()
        return jsonify({
            "submissions_by_day": [dict(r) for r in subs_by_day],
            "grade_distribution": [dict(r) for r in grade_dist],
        })

    else:
        scores = db.execute("""
            SELECT a.title, s.marks, a.max_marks
            FROM submissions s
            JOIN assignments a ON s.assignment_id = a.assignment_id
            WHERE s.student_id = ? AND s.marks IS NOT NULL
        """, (uid,)).fetchall()
        db.close()
        return jsonify({"scores": [dict(r) for r in scores]})


# ══════════════════════════════════════════════════════════════
#  RUN
# ══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)