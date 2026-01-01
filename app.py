import os
import sqlite3
from datetime import date, timedelta, datetime
from flask import Flask, render_template, request, redirect, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from uuid import uuid4
import random
from email.message import EmailMessage
import smtplib

# PDF generation
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# scheduler & payments
from apscheduler.schedulers.background import BackgroundScheduler
import stripe

# load config (user should create config.py from config.example.py)
try:
    import config
except Exception:
    config = None

# config-driven settings (read from config.py or env)
DUE_REMINDER_DAYS = int(getattr(config, 'DUE_REMINDER_DAYS', os.environ.get('DUE_REMINDER_DAYS', 2)))
LOW_STOCK_THRESHOLD = int(getattr(config, 'LOW_STOCK_THRESHOLD', os.environ.get('LOW_STOCK_THRESHOLD', 1)))
STRIPE_SECRET_KEY = getattr(config, 'STRIPE_SECRET_KEY', os.environ.get('STRIPE_SECRET_KEY'))
STRIPE_PUBLISHABLE_KEY = getattr(config, 'STRIPE_PUBLISHABLE_KEY', os.environ.get('STRIPE_PUBLISHABLE_KEY'))
stripe.api_key = STRIPE_SECRET_KEY or None

app = Flask(__name__)
app.secret_key = (getattr(config, "SECRET_KEY", None) or os.environ.get("SECRET_KEY") or "dev_secret")
DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

# ---------- DATABASE ----------
def db_connect():
    con = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db_connect()
    cur = con.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS books(
        id INTEGER PRIMARY KEY,
        title TEXT,
        author TEXT,
        isbn TEXT,
        category TEXT,
        quantity INTEGER,
        available INTEGER
    )""")

    # Ensure image/pdf columns exist (migrate older DBs)
    col_info = cur.execute("PRAGMA table_info(books)").fetchall()
    col_names = [c["name"] for c in col_info]
    if "image" not in col_names:
        cur.execute("ALTER TABLE books ADD COLUMN image TEXT")
    if "pdf" not in col_names:
        cur.execute("ALTER TABLE books ADD COLUMN pdf TEXT")

    # Ensure users table has verification and reset columns (migrate older DBs)
    ucol_info = cur.execute("PRAGMA table_info(users)").fetchall()
    ucol_names = [c["name"] for c in ucol_info]
    if "is_active" not in ucol_names:
        cur.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 0")
    if "verify_token" not in ucol_names:
        cur.execute("ALTER TABLE users ADD COLUMN verify_token TEXT")
    if "reset_token" not in ucol_names:
        cur.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
    if "reset_expires" not in ucol_names:
        cur.execute("ALTER TABLE users ADD COLUMN reset_expires TEXT")

    cur.execute("""CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        book_id INTEGER,
        issue_date TEXT,
        due_date TEXT,
        return_date TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(book_id) REFERENCES books(id)
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS fines(
        id INTEGER PRIMARY KEY,
        transaction_id INTEGER,
        amount INTEGER,
        status TEXT,
        FOREIGN KEY(transaction_id) REFERENCES transactions(id)
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        amount INTEGER,
        method TEXT,
        date TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    # seed admin if missing
    admin = cur.execute("SELECT * FROM users WHERE role='admin'").fetchone()
    if not admin:
        cur.execute(
            "INSERT INTO users (name,email,password,role,is_active) VALUES (?,?,?,?,?)",
            ("Sajib Ahmed Razon", "ahmedrazon58@gmail.com", generate_password_hash("22203142"), "admin", 1)
        )
    # make sure any existing admin is active
    cur.execute("UPDATE users SET is_active=1 WHERE role='admin'")

    # seed sample books (ensure at least these are present) — 50 books across requested categories
    book_count = cur.execute("SELECT COUNT(*) as c FROM books").fetchone()["c"]
    # if DB already has some books, leave them but add any missing sample books below
    if book_count < 50:
        # reuse the same list used by admin seed action if run later
        sample_books_raw = [
            ("The Quran: Translation and Commentary", "Various", "978-0000000101", "Islamic"),
            ("Introduction to Hadith", "M. Khan", "978-0000000102", "Islamic"),
            ("Islamic History Overview", "A. Rahman", "978-0000000103", "Islamic"),
            ("Contemporary Islamic Thought", "S. Ahmed", "978-0000000104", "Islamic"),
            ("Islamic Jurisprudence", "F. Malik", "978-0000000105", "Islamic"),
            ("Stories of the Prophets", "N. Karim", "978-0000000106", "Islamic"),

            ("Physics: Principles and Problems", "J. Walker", "978-0000000201", "Science"),
            ("Chemistry Essentials", "L. Chang", "978-0000000202", "Science"),
            ("Biology Today", "R. Peters", "978-0000000203", "Science"),
            ("Astronomy Basics", "K. Shah", "978-0000000204", "Science"),
            ("Environmental Science", "H. Gomez", "978-0000000205", "Science"),
            ("Introduction to Geology", "P. Singh", "978-0000000206", "Science"),
            ("Scientific Method and Research", "D. Clark", "978-0000000207", "Science"),

            ("Learning Python", "M. Lutz", "978-0000000301", "Software"),
            ("Clean Architecture", "R. Martin", "978-0000000302", "Software"),
            ("The Pragmatic Programmer", "Andrew Hunt", "978-0000000303", "Software"),
            ("Effective Java", "J. Bloch", "978-0000000304", "Software"),
            ("Fluent Python", "L. Ramalho", "978-0000000305", "Software"),
            ("Design Patterns", "E. Gamma", "978-0000000306", "Software"),
            ("Introduction to Algorithms", "T. Cormen", "978-0000000307", "Software"),
            ("Web Development with Flask", "S. Brown", "978-0000000308", "Software"),

            ("Bangla Grammar and Usage", "M. Rahman", "978-0000000401", "Bangla"),
            ("Bangla Literature: Classics", "Various", "978-0000000402", "Bangla"),
            ("Modern Bangla Poetry", "A. Islam", "978-0000000403", "Bangla"),
            ("Bangla Prose Anthology", "R. Choudhury", "978-0000000404", "Bangla"),
            ("Teach Yourself Bangla", "S. Banerjee", "978-0000000405", "Bangla"),
            ("Bangla for Beginners", "L. Hasan", "978-0000000406", "Bangla"),

            ("English Grammar in Use", "R. Murphy", "978-0000000501", "English"),
            ("English Literature: An Introduction", "J. Smith", "978-0000000502", "English"),
            ("Oxford Dictionary", "OUP", "978-0000000503", "English"),
            ("Creative Writing Basics", "E. Williams", "978-0000000504", "English"),
            ("English Comprehension", "H. Lewis", "978-0000000505", "English"),
            ("Conversation English", "D. Brown", "978-0000000506", "English"),
            ("English Vocabulary Builder", "S. Clark", "978-0000000507", "English"),

            ("Elementary Algebra", "G. Thomas", "978-0000000601", "Math"),
            ("Calculus I", "J. Stewart", "978-0000000602", "Math"),
            ("Discrete Mathematics", "R. Johnson", "978-0000000603", "Math"),
            ("Statistics and Probability", "L. Evans", "978-0000000604", "Math"),
            ("Linear Algebra", "G. Strang", "978-0000000605", "Math"),
            ("Number Theory Essentials", "A. N. Khan", "978-0000000606", "Math"),

            ("Art History Overview", "P. Miller", "978-0000000701", "Arts"),
            ("Drawing Techniques", "A. Lopez", "978-0000000702", "Arts"),
            ("Painting for Beginners", "C. Moore", "978-0000000703", "Arts"),
            ("Sculpture Essentials", "V. Rossi", "978-0000000704", "Arts"),
            ("Graphic Design Principles", "K. Hunter", "978-0000000705", "Arts"),
            ("Photography Basics", "L. Carter", "978-0000000706", "Arts"),

            ("Business Management", "P. Drucker", "978-0000000801", "Business"),
            ("Marketing 101", "S. Kotler", "978-0000000802", "Business"),
            ("Finance for Non-Finance", "R. Patel", "978-0000000803", "Business"),
            ("Entrepreneurship Guide", "M. Khan", "978-0000000804", "Business"),
        ]
        # build tuples with quantity between 5 and 10
        sample_books = []
        for t,a,isbn,cat in sample_books_raw:
            q = random.randint(5,10)
            sample_books.append((t,a,isbn,cat,q,q))
        # insert missing sample books if they are not already present
        existing = set([r['title'] for r in cur.execute("SELECT title FROM books").fetchall()])
        to_add = [b for b in sample_books if b[0] not in existing]
        if to_add:
            cur.executemany("INSERT INTO books (title,author,isbn,category,quantity,available) VALUES (?,?,?,?,?,?)", to_add)

    con.commit()
    con.close()

init_db()

# ---------- EMAIL ----------
def send_email(to, subject, body, attachments=None, html=None):
    """Send an email. attachments is an optional list of tuples: (filename, bytes, mimetype).
    Optional html parameter can be provided for an HTML alternative body."""
    MAIL_EMAIL = getattr(config, "MAIL_EMAIL", os.environ.get("MAIL_EMAIL"))
    MAIL_PASSWORD = getattr(config, "MAIL_PASSWORD", os.environ.get("MAIL_PASSWORD"))
    if not MAIL_EMAIL or not MAIL_PASSWORD:
        app.logger.warning("Email credentials not configured; skipping send_email")
        return False

    msg = EmailMessage()
    msg["From"] = MAIL_EMAIL
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    if html:
        try:
            msg.add_alternative(html, subtype='html')
        except Exception:
            app.logger.exception('Failed to attach HTML alternative to email')

    if attachments:
        for fname, data, mimetype in attachments:
            maintype, subtype = mimetype.split("/", 1)
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=fname)

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(MAIL_EMAIL, MAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        app.logger.info("Email sent to %s subject=%s", to, subject)
        return True
    except Exception as e:
        app.logger.exception("Failed to send email to %s (subject=%s): %s", to, subject, e)
        return False

# ---------- HELPERS ----------
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("user_role") != "admin":
            flash("Admin access required", "danger")
            app.logger.warning("Unauthorized admin access attempt user_id=%s", session.get("user_id"))
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated

# ---------- AUTH ----------
@app.route("/", methods=["GET", "POST"]) 
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        con = db_connect()
        user = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        con.close()

        if user and check_password_hash(user["password"], password):
            if not user["is_active"]:
                flash("Account not activated. Please check your email for verification or <a href='/resend'>resend</a>.", "warning")
                con.close()
                return redirect(url_for("login"))
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_role"] = user["role"]
            app.logger.info("User logged in id=%s email=%s role=%s", user["id"], user["email"], user["role"])
            return redirect(url_for("dashboard"))
        app.logger.warning("Failed login attempt for email=%s", email)
        flash("Invalid credentials", "danger")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        token = uuid4().hex
        con = db_connect()
        try:
            con.execute("INSERT INTO users (name,email,password,role,is_active,verify_token) VALUES (?,?,?,?,?,?)",
                        (name, email, generate_password_hash(password), "member", 0, token))
            con.commit()

            # send verification email
            verify_link = url_for("verify", token=token, _external=True)
            # render HTML template for verification
            html = render_template('email/verify.html', name=name, link=verify_link)
            txt = f"Hi {name},\n\nPlease verify your account by clicking: {verify_link}\n\nIf you did not register, ignore this email."
            ok = send_email(email, "Verify your Library account", txt, html=html)
            if ok:
                app.logger.info('Sent verification email to %s (new user id pending)', email)
            else:
                app.logger.warning('Failed to send verification email to %s', email)

            # notify admin
            adm = con.execute("SELECT email FROM users WHERE role='admin' LIMIT 1").fetchone()
            if adm:
                send_email(adm["email"], "New user registered (pending)", f"New user registered: {name} <{email}> - awaiting verification")

            flash("Registration successful. Check your email for a verification link.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email already registered.", "warning")
        finally:
            con.close()

    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route('/account/send_reset', methods=['POST'])
@login_required
def account_send_reset():
    uid = session.get('user_id')
    con = db_connect()
    user = con.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not user:
        con.close()
        flash('User not found', 'warning')
        return redirect(url_for('dashboard'))
    token = uuid4().hex
    expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    con.execute('UPDATE users SET reset_token=?, reset_expires=? WHERE id=?', (token, expires, uid))
    con.commit()
    app.logger.info('User user_id=%s requested reset email via dashboard', uid)
    con.close()
    link = url_for('reset_password', token=token, _external=True)
    html = render_template('email/reset.html', name=user['name'], link=link)
    txt = f"Hi {user['name']},\n\nYou requested a password reset. Use the link below to set a new password:\n{link}\nThis link expires in 1 hour."
    ok = send_email(user['email'], 'Reset your Library password', txt, html=html)
    if ok:
        flash('Reset email sent. Check your inbox.', 'success')
    else:
        flash('Failed to send reset email. Please contact admin.', 'warning')
    return redirect(url_for('dashboard'))

# ---------- PASSWORD RESET ----------
@app.route('/forgot', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        con = db_connect()
        user = con.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        if user:
            token = uuid4().hex
            expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()
            con.execute('UPDATE users SET reset_token=?, reset_expires=? WHERE id=?', (token, expires, user['id']))
            con.commit()
            app.logger.info('Password reset requested for user_id=%s email=%s', user['id'], email)
            con.close()
            link = url_for('reset_password', token=token, _external=True)
            html = render_template('email/reset.html', name=user['name'], link=link)
            txt = f"Hi {user['name']},\n\nTo reset your password click: {link}\nThis link expires in 1 hour."
            ok = send_email(email, 'Reset your Library password', txt, html=html)
            if ok:
                app.logger.info('Reset email sent to user_id=%s email=%s', user['id'], email)
            else:
                app.logger.warning('Failed to send reset email to user_id=%s email=%s', user['id'], email)
            flash('If that email exists in our system, a reset link has been sent.', 'info')
            return redirect(url_for('login'))
        con.close()
        flash('If that email exists in our system, a reset link has been sent.', 'info')
        return redirect(url_for('login'))
    return render_template('forgot.html')

@app.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    con = db_connect()
    user = con.execute('SELECT * FROM users WHERE reset_token=?', (token,)).fetchone()
    if not user:
        con.close()
        flash('Invalid or expired reset link.', 'warning')
        return redirect(url_for('login'))
    expires = user['reset_expires']
    if not expires or datetime.utcnow() > datetime.fromisoformat(expires):
        # expired
        con.execute('UPDATE users SET reset_token=NULL, reset_expires=NULL WHERE id=?', (user['id'],))
        con.commit()
        con.close()
        flash('Invalid or expired reset link.', 'warning')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password')
        password2 = request.form.get('password2')
        if not password or password != password2:
            flash('Passwords do not match or are empty.', 'warning')
            return render_template('reset.html')
        con.execute('UPDATE users SET password=?, reset_token=NULL, reset_expires=NULL WHERE id=?', (generate_password_hash(password), user['id']))
        con.commit()
        con.close()
        app.logger.info('Password changed for user_id=%s email=%s', user['id'], user['email'])
        # send HTML receipt for password change
        html = f"<p>Hi {user['name']},</p><p>Your password was successfully changed. If you didn't do this, contact the library admin immediately.</p>"
        txt = f"Hi {user['name']},\n\nYour password was successfully changed. If you didn't do this, contact admin."
        ok = send_email(user['email'], 'Your password has been changed', txt, html=html)
        if ok:
            app.logger.info('Password change email sent to user_id=%s', user['id'])
        else:
            app.logger.warning('Failed to send password change email to user_id=%s', user['id'])
        flash('Password updated. You can now log in.', 'success')
        return redirect(url_for('login'))

    con.close()
    return render_template('reset.html')
@app.route("/verify/<token>")
def verify(token):
    con = db_connect()
    user = con.execute("SELECT * FROM users WHERE verify_token=?", (token,)).fetchone()
    if not user:
        con.close()
        flash("Invalid or expired verification link.", "warning")
        return redirect(url_for("login"))
    con.execute("UPDATE users SET is_active=1, verify_token=NULL WHERE id=?", (user["id"],))
    admin = con.execute("SELECT email FROM users WHERE role='admin' LIMIT 1").fetchone()
    con.commit()
    con.close()

    # welcome email with simple HTML
    html = render_template('email/verify.html', name=user['name'], link=url_for('login', _external=True))
    txt = f"Hi {user['name']}, your account is now active. Welcome!"
    ok = send_email(user["email"], "Your Library account is active", txt, html=html)
    if ok:
        app.logger.info('Welcome email sent to user_id=%s email=%s', user['id'], user['email'])
    else:
        app.logger.warning('Failed to send welcome email to user_id=%s email=%s', user['id'], user['email'])

@app.route("/resend", methods=["GET", "POST"])
def resend_verification():
    if request.method == "POST":
        email = request.form.get("email")
        con = db_connect()
        user = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not user:
            con.close()
            flash("Email not found.", "warning")
            return redirect(url_for("resend_verification"))
        if user["is_active"]:
            con.close()
            flash("Account already active. Please log in.", "info")
            return redirect(url_for("login"))
        token = user["verify_token"] or uuid4().hex
        con.execute("UPDATE users SET verify_token=? WHERE id=?", (token, user["id"]))
        admin = con.execute("SELECT email FROM users WHERE role='admin' LIMIT 1").fetchone()
        con.commit()
        con.close()
        link = url_for("verify", token=token, _external=True)
        send_email(email, "Verify your Library account", f"Hi {user['name']},\n\nPlease verify your account by clicking: {link}")
        if admin:
            send_email(admin["email"], "User requested verification resend", f"Resend requested for: {user['name']} <{email}>")
        flash("Verification email sent.", "success")
        return redirect(url_for("login"))
    return render_template("resend.html")
@app.route("/dashboard")
@login_required
def dashboard():
    app.logger.info("Dashboard requested user_id=%s role=%s", session.get("user_id"), session.get("user_role"))
    if session.get("user_role") == "admin":
        con = db_connect()
        user_count = con.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        book_count = con.execute("SELECT COUNT(*) as c FROM books").fetchone()["c"]
        fine_count = con.execute("SELECT COUNT(*) as c FROM fines").fetchone()["c"]
        recent_books = con.execute("SELECT id,title,author,available FROM books ORDER BY id DESC LIMIT 8").fetchall()
        # active transactions (current borrows)
        active_txs = con.execute(
            "SELECT t.id as txid, u.name as user_name, b.title as book_title, b.quantity as book_quantity, b.available as book_available, t.issue_date, t.due_date FROM transactions t JOIN users u ON t.user_id=u.id JOIN books b ON t.book_id=b.id WHERE t.return_date IS NULL ORDER BY t.issue_date DESC LIMIT 50"
        ).fetchall()
        con.close()
        return render_template("admin.html", user_count=user_count, book_count=book_count, fine_count=fine_count, recent_books=recent_books, active_txs=active_txs)
    return render_template("member.html")

# ---------- ADMIN ROUTES ----------
@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    con = db_connect()
    users = con.execute("SELECT id,name,email,role FROM users").fetchall()
    con.close()
    return render_template("users.html", users=users)

@app.route("/admin/user/<int:uid>/promote", methods=["POST"])
@login_required
@admin_required
def promote_user(uid):
    new_role = request.form.get("role")
    if new_role not in ("admin","member"):
        flash("Invalid role", "warning")
        return redirect(url_for("admin_users"))
    con = db_connect()
    con.execute("UPDATE users SET role=? WHERE id=?", (new_role, uid))
    con.commit()
    con.close()
    flash("User role updated", "success")
    return redirect(url_for("admin_users"))

@app.route('/admin/user/<int:uid>/send_reset', methods=['POST'])
@login_required
@admin_required
def admin_send_reset(uid):
    con = db_connect()
    user = con.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not user:
        con.close()
        flash('User not found', 'warning')
        return redirect(url_for('admin_users'))
    token = uuid4().hex
    expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    con.execute('UPDATE users SET reset_token=?, reset_expires=? WHERE id=?', (token, expires, uid))
    con.commit()
    app.logger.info('Admin user_id=%s triggered reset for user_id=%s', session.get('user_id'), uid)
    con.close()
    link = url_for('reset_password', token=token, _external=True)
    html = render_template('email/reset.html', name=user['name'], link=link)
    txt = f"Hi {user['name']},\n\nAn admin has requested a password reset for your account. Use the link below to set a new password:\n{link}\nThis link expires in 1 hour."
    ok = send_email(user['email'], 'Reset your Library password', txt, html=html)
    if ok:
        flash('Reset email sent to user', 'success')
    else:
        flash('Failed to send reset email', 'warning')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:uid>/set_temp_password', methods=['POST'])
@login_required
@admin_required
def admin_set_temp_password(uid):
    import secrets
    temp = secrets.token_urlsafe(8)
    con = db_connect()
    user = con.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not user:
        con.close()
        flash('User not found', 'warning')
        return redirect(url_for('admin_users'))
    con.execute('UPDATE users SET password=? WHERE id=?', (generate_password_hash(temp), uid))
    con.commit()
    app.logger.info('Admin user_id=%s set temp password for user_id=%s', session.get('user_id'), uid)
    con.close()
    # email the temp password (advise change at next login)
    html = f"<p>Hi {user['name']},</p><p>An administrator set a temporary password for your account. Use the password below to log in and change it immediately:</p><p><strong>{temp}</strong></p>"
    txt = f"Hi {user['name']},\n\nAn administrator set a temporary password for your account. Use the password below to log in and change it immediately:\n{temp}"
    ok = send_email(user['email'], 'Temporary password - Library', txt, html=html)
    if ok:
        flash('Temporary password set and emailed to user', 'success')
    else:
        flash('Temporary password set but email failed', 'warning')
    return redirect(url_for('admin_users'))

@app.route("/admin/transactions")
@login_required
@admin_required
def admin_transactions():
    con = db_connect()
    txs = con.execute("SELECT t.*, u.name as user_name, b.title as book_title FROM transactions t JOIN users u ON t.user_id=u.id JOIN books b ON t.book_id=b.id ORDER BY t.issue_date DESC").fetchall()
    con.close()
    return render_template("transactions.html", transactions=txs)

@app.route("/admin/fine/<int:fid>/pay", methods=["POST"])
@login_required
@admin_required
def admin_mark_fine_paid(fid):
    con = db_connect()
    con.execute("UPDATE fines SET status='Paid' WHERE id=?", (fid,))
    con.commit()
    con.close()
    flash("Fine marked as paid", "success")
    return redirect(url_for("fines"))

@app.route("/admin/payments")
@login_required
@admin_required
def admin_payments():
    con = db_connect()
    payments = con.execute("SELECT p.*, u.name as user_name FROM payments p JOIN users u ON p.user_id=u.id ORDER BY date DESC").fetchall()
    con.close()
    return render_template("payments_admin.html", payments=payments) 

# ---------- BOOKS ----------
@app.route("/add_book", methods=["POST"])
@login_required
@admin_required
def add_book():
    app.logger.info("Add book by admin user_id=%s", session.get("user_id"))

    title = request.form.get("title")
    author = request.form.get("author")
    isbn = request.form.get("isbn")
    category = request.form.get("category") or "General"
    quantity = int(request.form.get("quantity") or 1)

    # Uploads removed: images and PDFs are no longer accepted via the admin form
    con = db_connect()
    con.execute("INSERT INTO books (title,author,isbn,category,quantity,available) VALUES (?,?,?,?,?,?)",
                (title, author, isbn, category, quantity, quantity))
    con.commit()
    con.close()
    flash("Book added", "success")
    return redirect(url_for("dashboard"))

@app.route("/books")
@login_required
def books():
    q = request.args.get('q','').strip()
    con = db_connect()
    if q:
        like = f"%{q}%"
        books = con.execute("SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR isbn LIKE ? OR category LIKE ?", (like,like,like,like)).fetchall()
    else:
        books = con.execute("SELECT * FROM books").fetchall()
    con.close()
    return render_template("books.html", books=books, q=q)

@app.route('/book/<int:book_id>')
@login_required
def book_detail(book_id):
    con = db_connect()
    b = con.execute('SELECT * FROM books WHERE id=?', (book_id,)).fetchone()
    con.close()
    if not b:
        flash('Book not found', 'warning')
        return redirect(url_for('books'))
    return render_template('book_detail.html', book=b)

# ---------- BORROW ----------
def generate_issue_pdf(txid):
    con = db_connect()
    tx = con.execute("SELECT t.*, u.name as user_name, u.email as user_email, b.title as book_title FROM transactions t JOIN users u ON t.user_id=u.id JOIN books b ON t.book_id=b.id WHERE t.id=?", (txid,)).fetchone()
    con.close()
    if not tx:
        return None
    buf = BytesIO()
    p = canvas.Canvas(buf, pagesize=letter)
    p.setFont('Helvetica', 12)
    p.drawString(50, 750, f"Library Issue Receipt")
    p.drawString(50, 730, f"Transaction ID: {tx['id']}")
    p.drawString(50, 710, f"Member: {tx['user_name']}")
    p.drawString(50, 690, f"Email: {tx['user_email']}")
    p.drawString(50, 670, f"Book: {tx['book_title']}")
    p.drawString(50, 650, f"Issue date: {tx['issue_date']}")
    p.drawString(50, 630, f"Due date: {tx['due_date']}")
    p.drawString(50, 610, "Thank you for using the library.")
    p.showPage()
    p.save()
    buf.seek(0)
    return buf.read()


def generate_return_pdf(txid):
    con = db_connect()
    tx = con.execute("SELECT t.*, u.name as user_name, u.email as user_email, b.title as book_title FROM transactions t JOIN users u ON t.user_id=u.id JOIN books b ON t.book_id=b.id WHERE t.id=?", (txid,)).fetchone()
    fine = con.execute("SELECT amount FROM fines WHERE transaction_id=?", (txid,)).fetchone()
    con.close()
    if not tx:
        return None
    buf = BytesIO()
    p = canvas.Canvas(buf, pagesize=letter)
    p.setFont('Helvetica', 12)
    p.drawString(50, 750, f"Library Return Receipt")
    p.drawString(50, 730, f"Transaction ID: {tx['id']}")
    p.drawString(50, 710, f"Member: {tx['user_name']}")
    p.drawString(50, 690, f"Email: {tx['user_email']}")
    p.drawString(50, 670, f"Book: {tx['book_title']}")
    p.drawString(50, 650, f"Issue date: {tx['issue_date']}")
    p.drawString(50, 630, f"Return date: {tx['return_date'] if tx['return_date'] else date.today().isoformat()}")
    p.drawString(50, 610, f"Fine: {fine['amount'] if fine else 0}")
    p.drawString(50, 590, "Thank you for using the library.")
    p.showPage()
    p.save()
    buf.seek(0)
    return buf.read()


@app.route('/receipt/issue/<int:txid>')
@login_required
def receipt_issue(txid):
    data = generate_issue_pdf(txid)
    if not data:
        flash('Receipt not found', 'warning')
        return redirect(url_for('dashboard'))
    return (data, 200, {
        'Content-Type': 'application/pdf',
        'Content-Disposition': f'attachment; filename="issue_receipt_{txid}.pdf"'
    })

# ---------- ADMIN: BOOK EDIT / DELETE ----------
@app.route('/admin/book/<int:book_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_book(book_id):
    con = db_connect()
    b = con.execute('SELECT * FROM books WHERE id=?', (book_id,)).fetchone()
    if not b:
        con.close()
        flash('Book not found', 'warning')
        return redirect(url_for('books'))
    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        isbn = request.form.get('isbn')
        category = request.form.get('category')
        try:
            quantity = int(request.form.get('quantity') or 0)
        except ValueError:
            quantity = b['quantity']
        # adjust available based on quantity delta
        available = b['available']
        delta = quantity - b['quantity']
        new_available = max(0, available + delta)
        con.execute('UPDATE books SET title=?, author=?, isbn=?, category=?, quantity=?, available=? WHERE id=?', (title, author, isbn, category, quantity, new_available, book_id))
        con.commit()
        con.close()
        flash('Book updated', 'success')
        return redirect(url_for('book_detail', book_id=book_id))
    con.close()
    return render_template('edit_book.html', book=b)

@app.route('/admin/book/<int:book_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_book(book_id):
    con = db_connect()
    # prevent deletion if there are active borrows
    active = con.execute('SELECT COUNT(*) as c FROM transactions WHERE book_id=? AND return_date IS NULL', (book_id,)).fetchone()['c']
    if active:
        con.close()
        flash('Cannot delete book with active borrows', 'warning')
        return redirect(url_for('book_detail', book_id=book_id))
    b = con.execute('SELECT * FROM books WHERE id=?', (book_id,)).fetchone()
    if not b:
        con.close()
        flash('Book not found', 'warning')
        return redirect(url_for('books'))
    # remove files if present
    if b['image']:
        try:
            p = os.path.join(os.path.dirname(__file__), b['image'])
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            app.logger.exception('Failed to remove book image file')
    if b['pdf']:
        try:
            p = os.path.join(os.path.dirname(__file__), b['pdf'])
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            app.logger.exception('Failed to remove book pdf file')
    con.execute('DELETE FROM books WHERE id=?', (book_id,))
    con.commit()
    con.close()
    flash('Book deleted', 'success')
    return redirect(url_for('books'))

# ---------- ADMIN: DELETE USER ----------
@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    con = db_connect()
    u = con.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    if not u:
        con.close()
        flash('User not found', 'warning')
        return redirect(url_for('admin_users'))
    if u['role'] == 'admin':
        con.close()
        flash('Cannot delete an admin user', 'warning')
        return redirect(url_for('admin_users'))
    # prevent deletion if active borrows or unpaid fines
    active = con.execute('SELECT COUNT(*) as c FROM transactions WHERE user_id=? AND return_date IS NULL', (user_id,)).fetchone()['c']
    unpaid = con.execute("SELECT COUNT(*) as c FROM fines f JOIN transactions t ON f.transaction_id=t.id WHERE t.user_id=? AND f.status!='paid'", (user_id,)).fetchone()['c']
    if active or unpaid:
        con.close()
        flash('Cannot delete user: active borrows or unpaid fines exist', 'warning')
        return redirect(url_for('admin_users'))
    # remove fines, payments, transactions
    tids = [r['id'] for r in con.execute('SELECT id FROM transactions WHERE user_id=?', (user_id,)).fetchall()]
    if tids:
        con.executemany('DELETE FROM fines WHERE transaction_id=?', [(t,) for t in tids])
    con.execute('DELETE FROM payments WHERE user_id=?', (user_id,))
    con.execute('DELETE FROM transactions WHERE user_id=?', (user_id,))
    con.execute('DELETE FROM users WHERE id=?', (user_id,))
    con.commit()
    con.close()
    flash('User deleted', 'success')
    return redirect(url_for('admin_users'))

@app.route('/receipt/return/<int:txid>')
@login_required
def receipt_return(txid):
    data = generate_return_pdf(txid)
    if not data:
        flash('Receipt not found', 'warning')
        return redirect(url_for('dashboard'))
    return (data, 200, {
        'Content-Type': 'application/pdf',
        'Content-Disposition': f'attachment; filename="return_receipt_{txid}.pdf"'
    })

# modified borrow: attach pdf to email
@app.route('/borrow/<int:book_id>')
@login_required
def borrow(book_id):
    try:
        user_id = session.get("user_id")
        if not user_id:
            flash('Login required', 'warning')
            return redirect(url_for('login'))
        issue = date.today()
        due = issue + timedelta(days=14)

        con = db_connect()
        book = con.execute("SELECT available,title FROM books WHERE id=?", (book_id,)).fetchone()
        if not book or book["available"] <= 0:
            flash("Book not available", "warning")
            con.close()
            return redirect(url_for("books"))

        con.execute("INSERT INTO transactions (user_id,book_id,issue_date,due_date,return_date) VALUES (?,?,?,?,?)",
                    (user_id, book_id, issue.isoformat(), due.isoformat(), None))
        con.execute("UPDATE books SET available=available-1 WHERE id=?", (book_id,))

        # get user email
        u = con.execute("SELECT email,name FROM users WHERE id=?", (user_id,)).fetchone()
        txid = con.execute('SELECT last_insert_rowid() as id').fetchone()[0]
        con.commit()
        con.close()

        # send issue confirmation email with PDF attachment
        pdf = generate_issue_pdf(txid)
        attachments = []
        if pdf:
            attachments.append((f'issue_receipt_{txid}.pdf', pdf, 'application/pdf'))
        if u:
            try:
                send_email(u['email'], "Book issued - Library receipt", f"Hi {u['name']},\n\nYou borrowed '{book['title']}' on {issue.isoformat()} due on {due.isoformat()}.", attachments=attachments)
            except Exception:
                app.logger.exception('Failed to send issue email for tx %s', txid)

        flash("Book borrowed successfully ⭐", "success")
        return redirect(url_for("dashboard"))
    except Exception as e:
        app.logger.exception('Error during borrow for book_id=%s user_id=%s: %s', book_id, session.get('user_id'), e)
        flash('Unable to process borrow request. Please try again or contact an admin. ⚠️', 'danger')
        return redirect(url_for('books'))

# modified return_book: attach PDF
@app.route("/return/<int:tid>")
@login_required
def return_book(tid):
    con = db_connect()
    tx = con.execute("SELECT * FROM transactions WHERE id=?", (tid,)).fetchone()
    if not tx:
        flash("Transaction not found", "warning")
        con.close()
        return redirect(url_for("dashboard"))

    if tx["return_date"]:
        flash("Already returned", "info")
        con.close()
        return redirect(url_for("dashboard"))

    due = date.fromisoformat(tx["due_date"])
    today = date.today()
    overdue = (today - due).days
    overdue_days = overdue if overdue > 0 else 0

    con.execute("UPDATE transactions SET return_date=? WHERE id=?", (today.isoformat(), tid))
    con.execute("UPDATE books SET available=available+1 WHERE id=?", (tx["book_id"],))

    fine_amount = 0
    if overdue_days > 0:
        amount = overdue_days * 5
        con.execute("INSERT INTO fines (transaction_id,amount,status) VALUES (?,?,?)", (tid, amount, "Unpaid"))
        fine_amount = amount
        flash(f"Book returned. Fine: {amount}", "warning")
    else:
        flash("Book returned on time.", "success")

    # get user email and send return confirmation
    u = con.execute("SELECT email,name FROM users WHERE id=?", (tx["user_id"],)).fetchone()

    con.commit()
    con.close()

    if u:
        body = f"Hi {u['name']},\n\nYour return for transaction #{tid} is processed on {today.isoformat()}."
        if fine_amount > 0:
            body += f"\nFine amount: {fine_amount}. Please pay via the library payment page."
        pdf = generate_return_pdf(tid)
        attachments = []
        if pdf:
            attachments.append((f'return_receipt_{tid}.pdf', pdf, 'application/pdf'))
        send_email(u['email'], "Return processed - Library", body, attachments=attachments)

    return redirect(url_for("dashboard"))

# ---------- FINES ----------
@app.route("/fines")
@login_required
def fines():
    con = db_connect()
    if session.get("user_role") == "admin":
        fines = con.execute("SELECT f.*, t.user_id, u.name as user_name FROM fines f JOIN transactions t ON f.transaction_id=t.id JOIN users u ON t.user_id=u.id").fetchall()
        con.close()
        return render_template("fines_admin.html", fines=fines)
    else:
        fines = con.execute("SELECT f.* FROM fines f JOIN transactions t ON f.transaction_id=t.id WHERE t.user_id=?", (session["user_id"],)).fetchall()
        con.close()
        return render_template("fines.html", fines=fines)

# ---------- PAYMENT ----------
@app.route("/pay", methods=["POST"])
@login_required
def pay():
    amount = int(request.form.get("amount"))
    method = request.form.get("method")
    # collect optional card details (do NOT store full card data)
    card_holder = request.form.get('card_holder') if method == 'Card' else None
    card_number = request.form.get('card_number') if method == 'Card' else None
    card_expiry = request.form.get('card_expiry') if method == 'Card' else None
    # mask card number for receipt (keep only last 4 if present)
    card_mask = None
    if card_number:
        s = ''.join(ch for ch in (card_number or '') if ch.isdigit())
        if len(s) >= 4:
            card_mask = '**** **** **** ' + s[-4:]
        else:
            card_mask = '****'

    con = db_connect()
    # record payment
    con.execute("INSERT INTO payments (user_id,amount,method,date) VALUES (?,?,?,?)",
                (session["user_id"], amount, method, date.today().isoformat()))

    # fetch unpaid fines for this user to include in receipt
    unpaid = con.execute("SELECT f.id,f.amount,f.transaction_id,t.book_id,t.issue_date,t.due_date FROM fines f JOIN transactions t ON f.transaction_id=t.id WHERE f.status='Unpaid' AND t.user_id=?", (session['user_id'],)).fetchall()

    # mark all unpaid fines for user as Paid (simple approach)
    con.execute("UPDATE fines SET status='Paid' WHERE status='Unpaid' AND transaction_id IN (SELECT id FROM transactions WHERE user_id=?)", (session["user_id"],))
    con.commit()

    # send payment receipt email with details and optional PDF
    u = con.execute('SELECT email,name FROM users WHERE id=?', (session['user_id'],)).fetchone()
    # build receipt body
    lines = [f"Hi {u['name']},","","We received your payment.",f"Amount: {amount}",f"Method: {method}",""]
    if unpaid:
        lines.append('The following fines have been marked as Paid:')
        for f in unpaid:
            # try to get book title
            b = con.execute('SELECT title FROM books WHERE id=?', (f['book_id'],)).fetchone()
            title = b['title'] if b else f"transaction {f['transaction_id']}"
            lines.append(f"- {title}: {f['amount']}")
    body = "\n".join(lines)

    # generate a small PDF receipt if reportlab available
    attachments = []
    try:
        from io import BytesIO
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        buf = BytesIO()
        p = canvas.Canvas(buf, pagesize=letter)
        p.setFont('Helvetica', 12)
        y = 750
        p.drawString(50, y, 'Payment Receipt')
        y -= 20
        p.drawString(50, y, f'Name: {u["name"]}')
        y -= 20
        p.drawString(50, y, f'Amount: {amount}')
        y -= 20
        p.drawString(50, y, f'Method: {method}')
        y -= 20
        p.drawString(50, y, f'Date: {date.today().isoformat()}')
        y -= 30
        if unpaid:
            p.drawString(50, y, 'Paid fines:')
            y -= 20
            for f in unpaid:
                b = con.execute('SELECT title FROM books WHERE id=?', (f['book_id'],)).fetchone()
                title = b['title'] if b else f"tx {f['transaction_id']}"
                p.drawString(60, y, f"- {title}: {f['amount']}")
                y -= 15
                if y < 80:
                    p.showPage(); y = 750
        p.showPage()
        p.save()
        buf.seek(0)
        pdfdata = buf.read()
        attachments.append((f'payment_receipt_{date.today().isoformat()}.pdf', pdfdata, 'application/pdf'))
    except Exception:
        attachments = []

    con.close()
    if u:
        send_email(u['email'], 'Payment receipt - Library', body, attachments=attachments)
    flash("Payment successful", "success")
    return redirect(url_for("dashboard"))

# ---------- PAYMENT MOCK PAGE ----------
@app.route("/payment")
@login_required
def payment_page():
    # calculate outstanding fines
    con = db_connect()
    fines = con.execute("SELECT f.* FROM fines f JOIN transactions t ON f.transaction_id=t.id WHERE status='Unpaid' AND t.user_id=?", (session['user_id'],)).fetchall()
    total = sum([f['amount'] for f in fines]) if fines else 0
    con.close()
    return render_template("payment.html", fines=fines, total=total, stripe_key=STRIPE_PUBLISHABLE_KEY)


# Stripe checkout creation (optional, requires STRIPE_SECRET_KEY to be set)
@app.route('/create_checkout_session', methods=['POST'])
@login_required
def create_checkout_session():
    if not STRIPE_SECRET_KEY:
        flash('Stripe not configured', 'warning')
        return redirect(url_for('payment_page'))
    amount = int(request.form.get('amount'))
    # create stripe session
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'product_data': {'name': 'Library fine payment'},
                'unit_amount': amount * 100,
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url=url_for('payment_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=url_for('payment_page', _external=True),
    )
    return redirect(session.url, code=303)

@app.route('/payment_success')
@login_required
def payment_success():
    session_id = request.args.get('session_id')
    if not session_id:
        flash('Invalid payment session', 'warning')
        return redirect(url_for('dashboard'))
    if not STRIPE_SECRET_KEY:
        flash('Stripe not configured', 'warning')
        return redirect(url_for('dashboard'))
    s = stripe.checkout.Session.retrieve(session_id)
    amount = s['amount_total'] // 100
    # record payment and mark fines as paid
    con = db_connect()
    con.execute("INSERT INTO payments (user_id,amount,method,date) VALUES (?,?,?,?)", (session['user_id'], amount, 'stripe', date.today().isoformat()))
    con.execute("UPDATE fines SET status='Paid' WHERE status='Unpaid' AND transaction_id IN (SELECT id FROM transactions WHERE user_id=?)", (session['user_id'],))
    con.commit()
    con.close()
    # send payment receipt
    u = None
    con = db_connect()
    u = con.execute('SELECT email,name FROM users WHERE id=?', (session['user_id'],)).fetchone()
    con.close()
    if u:
        # generate a simple PDF receipt
        from io import BytesIO
        buf = BytesIO()
        p = canvas.Canvas(buf, pagesize=letter)
        p.setFont('Helvetica', 12)
        p.drawString(50, 750, 'Payment Receipt')
        p.drawString(50, 730, f'User: {u["name"]}')
        p.drawString(50, 710, f'Amount: {amount} USD')
        p.drawString(50, 690, f'Date: {date.today().isoformat()}')
        p.drawString(50, 670, 'Thank you.')
        p.showPage()
        p.save()
        buf.seek(0)
        pdfdata = buf.read()
        send_email(u['email'], 'Payment receipt - Library', f"Hi {u['name']},\n\nWe received your payment of {amount} USD. Thank you.", attachments=[(f'payment_receipt_{date.today().isoformat()}.pdf', pdfdata, 'application/pdf')])
    flash('Payment successful. Receipt sent via email.', 'success')
    return redirect(url_for('dashboard'))

# ---------- SCHEDULED JOBS ----------

def check_due_dates():
    con = db_connect()
    cutoff = (date.today() + timedelta(days=DUE_REMINDER_DAYS)).isoformat()
    rows = con.execute("SELECT t.id as txid, t.due_date, t.user_id, u.name as user_name, u.email as user_email, b.title as book_title FROM transactions t JOIN users u ON t.user_id=u.id JOIN books b ON t.book_id=b.id WHERE t.return_date IS NULL AND t.due_date <= ?", (cutoff,)).fetchall()
    con.close()

    # group by user
    users = {}
    for r in rows:
        uid = r['user_id']
        users.setdefault(uid, {'email': r['user_email'], 'name': r['user_name'], 'books': []})
        users[uid]['books'].append({'title': r['book_title'], 'due_date': r['due_date']})

    for u in users.values():
        body_lines = [f"Hi {u['name']},", "", "The following books are due soon:", ""]
        for b in u['books']:
            body_lines.append(f"- {b['title']} (due {b['due_date']})")
        body_lines.append("\nPlease return them on time to avoid fines.")
        send_email(u['email'], "Library due date reminder", "\n".join(body_lines))


def check_low_stock():
    con = db_connect()
    rows = con.execute("SELECT id,title,available,quantity FROM books WHERE available <= ?", (LOW_STOCK_THRESHOLD,)).fetchall()
    con.close()
    if not rows:
        return
    # notify admin(s)
    con = db_connect()
    admins = con.execute("SELECT email,name FROM users WHERE role='admin'").fetchall()
    con.close()
    if not admins:
        return
    lines = ["The following books are low in stock:",""]
    for r in rows:
        lines.append(f"- {r['title']}: available {r['available']} / total {r['quantity']}")

    body = "\n".join(lines)
    for a in admins:
        send_email(a['email'], "Low stock alert - Library", f"Hi {a['name']},\n\n{body}")

# admin route to manually trigger jobs
@app.route('/admin/run_jobs', methods=['POST'])
@login_required
@admin_required
def admin_run_jobs():
    check_due_dates()
    check_low_stock()
    flash('Scheduled jobs executed', 'success')
    return redirect(url_for('dashboard'))

@app.route('/admin/seed_books', methods=['POST'])
@login_required
@admin_required
def admin_seed_books():
    """Idempotent: insert sample books that are missing (quantities randomized 5-10)."""
    sample_books_raw = [
        ("The Quran: Translation and Commentary", "Various", "978-0000000101", "Islamic"),
        ("Introduction to Hadith", "M. Khan", "978-0000000102", "Islamic"),
        ("Islamic History Overview", "A. Rahman", "978-0000000103", "Islamic"),
        ("Contemporary Islamic Thought", "S. Ahmed", "978-0000000104", "Islamic"),
        ("Islamic Jurisprudence", "F. Malik", "978-0000000105", "Islamic"),
        ("Stories of the Prophets", "N. Karim", "978-0000000106", "Islamic"),

        ("Physics: Principles and Problems", "J. Walker", "978-0000000201", "Science"),
        ("Chemistry Essentials", "L. Chang", "978-0000000202", "Science"),
        ("Biology Today", "R. Peters", "978-0000000203", "Science"),
        ("Astronomy Basics", "K. Shah", "978-0000000204", "Science"),
        ("Environmental Science", "H. Gomez", "978-0000000205", "Science"),
        ("Introduction to Geology", "P. Singh", "978-0000000206", "Science"),
        ("Scientific Method and Research", "D. Clark", "978-0000000207", "Science"),

        ("Learning Python", "M. Lutz", "978-0000000301", "Software"),
        ("Clean Architecture", "R. Martin", "978-0000000302", "Software"),
        ("The Pragmatic Programmer", "Andrew Hunt", "978-0000000303", "Software"),
        ("Effective Java", "J. Bloch", "978-0000000304", "Software"),
        ("Fluent Python", "L. Ramalho", "978-0000000305", "Software"),
        ("Design Patterns", "E. Gamma", "978-0000000306", "Software"),
        ("Introduction to Algorithms", "T. Cormen", "978-0000000307", "Software"),
        ("Web Development with Flask", "S. Brown", "978-0000000308", "Software"),

        ("Bangla Grammar and Usage", "M. Rahman", "978-0000000401", "Bangla"),
        ("Bangla Literature: Classics", "Various", "978-0000000402", "Bangla"),
        ("Modern Bangla Poetry", "A. Islam", "978-0000000403", "Bangla"),
        ("Bangla Prose Anthology", "R. Choudhury", "978-0000000404", "Bangla"),
        ("Teach Yourself Bangla", "S. Banerjee", "978-0000000405", "Bangla"),
        ("Bangla for Beginners", "L. Hasan", "978-0000000406", "Bangla"),

        ("English Grammar in Use", "R. Murphy", "978-0000000501", "English"),
        ("English Literature: An Introduction", "J. Smith", "978-0000000502", "English"),
        ("Oxford Dictionary", "OUP", "978-0000000503", "English"),
        ("Creative Writing Basics", "E. Williams", "978-0000000504", "English"),
        ("English Comprehension", "H. Lewis", "978-0000000505", "English"),
        ("Conversation English", "D. Brown", "978-0000000506", "English"),
        ("English Vocabulary Builder", "S. Clark", "978-0000000507", "English"),

        ("Elementary Algebra", "G. Thomas", "978-0000000601", "Math"),
        ("Calculus I", "J. Stewart", "978-0000000602", "Math"),
        ("Discrete Mathematics", "R. Johnson", "978-0000000603", "Math"),
        ("Statistics and Probability", "L. Evans", "978-0000000604", "Math"),
        ("Linear Algebra", "G. Strang", "978-0000000605", "Math"),
        ("Number Theory Essentials", "A. N. Khan", "978-0000000606", "Math"),

        ("Art History Overview", "P. Miller", "978-0000000701", "Arts"),
        ("Drawing Techniques", "A. Lopez", "978-0000000702", "Arts"),
        ("Painting for Beginners", "C. Moore", "978-0000000703", "Arts"),
        ("Sculpture Essentials", "V. Rossi", "978-0000000704", "Arts"),
        ("Graphic Design Principles", "K. Hunter", "978-0000000705", "Arts"),
        ("Photography Basics", "L. Carter", "978-0000000706", "Arts"),

        ("Business Management", "P. Drucker", "978-0000000801", "Business"),
        ("Marketing 101", "S. Kotler", "978-0000000802", "Business"),
        ("Finance for Non-Finance", "R. Patel", "978-0000000803", "Business"),
        ("Entrepreneurship Guide", "M. Khan", "978-0000000804", "Business"),
    ]
    sample_books = []
    for t,a,isbn,cat in sample_books_raw:
        q = random.randint(5,10)
        sample_books.append((t,a,isbn,cat,q,q))
    con = db_connect()
    existing = set([r['title'] for r in con.execute("SELECT title FROM books").fetchall()])
    to_add = [b for b in sample_books if b[0] not in existing]
    if to_add:
        con.executemany("INSERT INTO books (title,author,isbn,category,quantity,available) VALUES (?,?,?,?,?,?)", to_add)
        con.commit()
        flash(f'Added {len(to_add)} sample books', 'success')
    else:
        flash('Sample books already present', 'info')
    con.close()
    return redirect(url_for('dashboard'))
# template helper for low stock
@app.context_processor
def utility_processor():
    def get_low_stock():
        con = db_connect()
        rows = con.execute("SELECT id,title,available,quantity FROM books WHERE available <= ?", (LOW_STOCK_THRESHOLD,)).fetchall()
        con.close()
        return rows
    def get_user_transactions():
        # returns active transactions for current user with computed days and estimated fine
        uid = session.get('user_id')
        if not uid:
            return []
        con = db_connect()
        rows = con.execute("SELECT t.id as txid, b.title as book_title, t.issue_date, t.due_date FROM transactions t JOIN books b ON t.book_id=b.id WHERE t.user_id=?", (uid,)).fetchall()
        con.close()
        out = []
        today = date.today()
        for r in rows:
            try:
                issue = date.fromisoformat(r['issue_date']) if r['issue_date'] else today
            except Exception:
                issue = today
            try:
                due = date.fromisoformat(r['due_date']) if r['due_date'] else today
            except Exception:
                due = today
            days = (today - issue).days
            overdue = (today - due).days if today > due else 0
            fine = overdue * 5 if overdue > 0 else 0
            out.append({'txid': r['txid'], 'book_title': r['book_title'], 'issue_date': str(issue), 'due_date': str(due), 'days_borrowed': days, 'overdue_days': overdue, 'estimated_fine': fine})
        return out
    return dict(get_low_stock=get_low_stock, get_user_transactions=get_user_transactions)

# start scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(check_due_dates, 'interval', days=1, id='check_due_dates')
scheduler.add_job(check_low_stock, 'interval', days=1, id='check_low_stock')
scheduler.start()

# health endpoint for load balancers and checks
@app.route('/health')
def health():
    return "OK", 200

if __name__ == "__main__":
    # Respect environment variables for production
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host=host, port=port, debug=debug)
