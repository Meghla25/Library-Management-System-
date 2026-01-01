# Library Management System

A simple Library Management System (LMS) built with Flask and SQLite. This project includes admin and member features for borrowing books, managing fines, mock and card payments (mocked on server), email receipts, and PDF receipts.

---

## 🚀 Key features

- User registration, email verification, and secure password storage (Werkzeug hash).
- Admin dashboard: add/edit/delete books, view users, transactions, fines, and payments.
- Member dashboard: view borrowed books, outstanding fines, and a payments UI (mock card fields included).
- Fines automatically created for overdue returns and can be paid from member UI (or via Stripe if configured).
- Email notifications: verification, password resets, payment receipts (email + PDF attachment using ReportLab when available).
- Scheduled jobs (APScheduler) to notify due dates and low-stock alerts.
- Health endpoint (`/health`) for load balancers.

---

## 🔧 Local setup

1. Copy the example config and fill secrets (or export env vars):

```powershell
Copy-Item .\config.example.py .\config.py
# or set env vars: SECRET_KEY, MAIL_EMAIL, MAIL_PASSWORD, STRIPE_* etc.
```

> IMPORTANT: Do NOT commit `config.py` to version control. Keep secrets in environment variables for production.

2. Create and activate a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # (PowerShell)
pip install -r requirements.txt
```

3. Initialize the database (creates `database.db` and seeds admin & sample books):

```powershell
python init_db.py
```

4. Run the app locally (development):

```powershell
$env:FLASK_DEBUG='1'; $env:HOST='127.0.0.1'; $env:PORT='5000'
& ".\.venv\Scripts\python.exe" .\app.py
```

Open: http://127.0.0.1:5000

---

## 📋 Important environment variables

- SECRET_KEY — application secret (required)
- MAIL_EMAIL, MAIL_PASSWORD — SMTP sender credentials (App password recommended for Gmail)
- FLASK_DEBUG — set `0` in production
- STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY — optional for Stripe integration
- DATABASE_URL — optional (Postgres) for production (recommended instead of SQLite)
- DUE_REMINDER_DAYS, LOW_STOCK_THRESHOLD — scheduler settings

The app will fall back and warn if email/stripe credentials are not configured.

---

## 🧾 Payment & receipts

- Member Payment UI (`/payment`) supports mock payments and a simple card form used only for demo (card fields are NOT stored).
- Server marks unpaid fines as **Paid** when payment is processed and sends a receipt email. If ReportLab is installed, a PDF receipt attachment is generated.
- For production card processing, integrate Stripe and set `STRIPE_SECRET_KEY` and `STRIPE_PUBLISHABLE_KEY`.

Security note: Do not send or store raw card data in production — use a PCI-compliant gateway.

---

## 🧑‍💻 Admin & Member views

- Admin dashboard (`/dashboard` as admin): shows counts, recent books, active borrows with member name, book title, quantities, issue and due dates, and links to payments and fines.
- Member dashboard (`/dashboard` as member): shows borrowed books, days borrowed, overdue days, and estimated fines (5 currency units per overdue day).

## 🖼️ Design & assets

- Login/Register pages use a background image (placed at `static/auth_bg.png`) and an auth card for readability.
- Books show a cover image if present, otherwise `static/book_images/default.png` is used as fallback.

---

## ▶️ Deployment to Render

Render is a good option for simple hosting. The repository includes `render.yaml` and a `Procfile`.

1. Push your repo to GitHub and update `render.yaml` with your repository URL.
2. On Render dashboard: create a new **Web Service** → connect your GitHub repo.
3. Build command:

```text
pip install -r requirements.txt
```

4. Start command:

```text
gunicorn --preload --bind 0.0.0.0:$PORT app:app
```

5. Add environment variables in the Render service settings (see the list above).

6. (Recommended) Use Render Managed Postgres and set `DATABASE_URL` — update `db_connect()` in `app.py` to use Postgres or request my help to migrate (I can modify the app to read `DATABASE_URL` and use `psycopg2` or SQLAlchemy).

7. Deploy and check the service URL and `/health` endpoint.

**Important**: SQLite is ephemeral on many PaaS platforms. Use managed Postgres for persistent data.

---

## ✅ Troubleshooting

- ERR_CONNECTION_REFUSED: Ensure the Flask server is running and listening on correct host/port. On Windows PowerShell make sure you run with `& "path\to\python.exe" .\app.py` or use the run scripts.
- TemplateSyntaxError (Jinja): This commonly occurs if templates contain unescaped quotes inside expressions. Example fixed: `onclick="return confirm('Delete book {{ b.title }}?')"`.
- Email not sending: Verify `MAIL_EMAIL` and `MAIL_PASSWORD`. For Gmail, create and use an App Password.

---

## ⚙️ Next recommendations

- Replace SQLite with Postgres for production (I can implement this and add migrations)
- Add admin file uploads for per-book cover images (or bulk import images)
- Add improved receipt templates (`templates/email/receipt.html`) for nicer emails
- Consider a background worker (Celery/RQ) for sending emails asynchronously in production

---

If you want, I can proceed to:
- Add Postgres support and migrations, or
- Implement Stripe checkout for real payments, or
- Add per-book image upload UI and file storage handling.

Tell me which you'd like next and I’ll implement it.
- Register / Login (passwords hashed)
- Admin dashboard to add books
- Borrow / Return books
- Fines and mock payment
- Email helper (configure SMTP to send emails)
- Email verification (users must confirm their email to activate their account)
- Scheduled jobs (due reminders, low-stock alerts) using APScheduler (configure `DUE_REMINDER_DAYS` and `LOW_STOCK_THRESHOLD` in `config.py` or env vars)
- Optional Stripe integration for real payments (set `STRIPE_SECRET_KEY` and `STRIPE_PUBLISHABLE_KEY` in env or `config.py`)
- Printable/downloadable PDF receipts are available for issue, return, and payments (generated with ReportLab).
- Password reset via email: users can request a reset link from the login page (link expires in 1 hour).

Setup
1. Copy `config.example.py` to `config.py` and fill values (or export environment variables `MAIL_EMAIL`, `MAIL_PASSWORD`, `SECRET_KEY`).
2. Create virtualenv and install requirements:

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

3. Run locally:

```
# initialize or reseed DB (creates database.db)
python init_db.py

# then run the app
python app.py
```

One-command run scripts (Windows):
- PowerShell: `./run.ps1` (use `-Reinstall` to recreate the venv)
- CMD: `run.bat`

These scripts will create a virtual environment, install dependencies, initialize the DB, and start the app.

Test email helper:
- Quick test: `python send_test_email.py recipient@example.com` (or run without args and enter an email when prompted)

Deployment (Render)

1. Push repo to GitHub.
2. Create a new Web Service on render.com and connect the repo.
3. Set the build command to:

```
pip install -r requirements.txt
```

4. Set the start command to:

```
gunicorn app:app
```

5. In Render, add the environment variables (important):
   - SECRET_KEY (your secret)
   - MAIL_EMAIL (your gmail or sender email)
   - MAIL_PASSWORD (gmail app password or SMTP password)
   - FLASK_DEBUG (set to `0` for production)

Notes on Gmail: Create an App Password for your Google account (recommended) and use it for `MAIL_PASSWORD`.

Important: SQLite stores data on the instance filesystem which is ephemeral on many PaaS providers. For production you should use PostgreSQL or another managed DB and set `DATABASE_URL` and update `db_connect()` accordingly. For small demos you may use SQLite but add regular backups.

Health checks: Render will use `/health` endpoint (returns `OK`) to verify the service is healthy.

Optional: Add a `render.yaml` (included) to configure service metadata and environment variables.

Notes
- `database.db` is created automatically. Don't commit `database.db` or `config.py` to source control.
- The seeded admin user is `Sajib Ahmed Razon` — Email: **Contact Github Account Admin person** / Password: **Contact Github Account** (change after first login).
