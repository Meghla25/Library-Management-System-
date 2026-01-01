# Activity Diagram — Annotations & Implementation Mapping ✅

This document maps each activity node from your diagram to the current implementation status and where the functionality lives in the codebase. Use this as a checklist to finish remaining items.

---

## Legend
- ✅ Implemented
- ⚠️ Partially implemented / needs improvement
- ❌ Not implemented

---

## Top-level flow (User registration & verification)
- Open Library Management System — UI: `templates/login.html`, `templates/register.html` ✅
- New User? — decision node: handled by `register` route in `app.py` ✅
- Fill registration form — `templates/register.html` ✅
- Validate inputs — basic validation via `required` in form and DB constraint; could add server-side validation (⚠️)
- Create user (PENDING) — implemented as user row with `is_active=0` and `verify_token` in `app.py` ✅
- Send verification email — `send_email(...)` in `app.py` and `register` sends verification link ✅
- Email verified? decision: `/verify/<token>` route implemented, activates account ✅
- Activate account & send welcome email — implemented in `verify` route ✅
- Notify Admin (New User) — implemented (admin notification on register/resend) ✅

Notes / Improvements:
- Server-side input validation could be hardened (e.g., email format, password strength). (Recommended) ⚠️

---

## Login / Dashboard
- Login — `login` route (`app.py`) ✅
- Credentials valid? decision — implemented; also checks `is_active` and prompts for resend link ✅
- Display Dashboard — `dashboard` route; admin/member split renders `admin.html` and `member.html` ✅

---

## Search / Browse
- Select action / Search Book — `books` route and `templates/books.html` (query param `q`) ✅
- Enter search criteria / Display results — implemented ✅
- Edge case: No results — currently flash and show empty list (could show improved message) ⚠️

---

## Issue Book Flow
- Choose to Issue — `borrow/<book_id>` route (`app.py`) ✅
- Enter book & member details — uses session user and book ID (works) ✅
- Book available? decision — checks `available` field and blocks if not available ✅
- Update book status (`available`) — implemented ✅
- Generate issue receipt — an email receipt is sent (`send_email` called) ✅
- Send issue confirmation email — implemented ✅

Notes:
- No PDF/downloadable receipt generated (email only). If you want a printable receipt, add a route/template for a printable receipt (optional). ❌

---

## Return Book Flow
- Return? — `return/<transaction_id>` route (`app.py`) ✅
- Enter return details / Update book status — implemented ✅
- Calculate overdue days & fine — implemented (rate: 5 per day) ✅
- Update fines table — implemented ✅
- Send return confirmation email — implemented ✅
- Generate return receipt — email only; same as issue receipt (no printable receipt template) ⚠️

Notes:
- Fine policy is hard-coded (5 per day). Consider making configurable in `config.py` or DB. (Recommended) ⚠️

---

## Fines & Payments
- Display fines: `/fines` route and templates `fines.html`, `fines_admin.html` ✅
- Pay fines: `/pay` route (mock payment stored in `payments` table and marks fines Paid) ✅ (simple stub)
- Payment gateway integration: currently a mock page (`/payment` and `payment.html`). ❌
- Payment receipts: not emailed; you can add send_email after successful payment. ❌

Recommended next steps:
- Integrate real gateway (Stripe/PayPal) or a provider (SendGrid) for receipts. Add email receipts for successful payments. (Planned task) ❌

---

## Admin Functions
- Manage Books: `add_book` route & form (admin only) ✅
- Manage Members: `admin_users` and `promote_user` ✅
- View Transactions: `/admin/transactions` ✅
- Mark fines paid: `/admin/fine/<fid>/pay` ✅
- Low stock alerts: Not implemented (only seed books and an admin view) ❌

Recommended:
- Add low-stock check (on add/borrow/return and/or a scheduled job) and alert via email to admin or show in `admin.html`. ❌

---

## Scheduled Background Jobs (Not implemented)
- System checks due dates — Not implemented (needed for daily reminders) ❌
- Send due reminder emails — Not implemented ❌
- Send low-stock alerts — Not implemented ❌

Options to implement:
- Use a scheduler like `APScheduler`, `celery` + `celery beat`, or a simple cron job that calls an endpoint to run checks. (Preferred: `APScheduler` for single-process deployments; `celery` for scalable deployments)

---

## Notifications & Emails
- Email helper `send_email` in `app.py` exists and supports Gmail SMTP ✅
- Verification, registration admin notify, borrow/return emails implemented ✅
- Payment email receipts not implemented ❌
- Resend verification implemented (`/resend`) ✅

---

## Tests & CI
- No automated tests found. Add unit tests for routes and DB logic (pytest) and a simple GitHub Action to run tests on PRs. ❌

---

## Security & Production Notes
- `config.py` is in `.gitignore` (good). Use environment variables in production. ✅
- Gmail is configured (works with an App Password). Consider moving to a transactional email provider for production (SendGrid/Mailgun). ⚠️
- DB is SQLite; for production use a managed DB (Postgres) and set `DATABASE_URL`. ✅ (not currently implemented) 

---

## Implementation Checklist (Suggested priority)
1. (High) Add scheduled jobs: due reminders & low-stock alerts — implement using `APScheduler` or similar. (2–4 hours) ❌
2. (High) Payment gateway integration + send payment receipt emails (Stripe or PayPal) (3–6 hours) ❌
3. (Medium) Add printable receipt templates & download route for issue/return receipts (1–2 hours) ⚠️
4. (Medium) Improve server-side validation & password policy (1–2 hours) ⚠️
5. (Medium) Add low-stock alerts in admin dashboard and automatic email when low (1–2 hours) ❌
6. (Low) Add unit tests and CI (2–4 hours) ❌
7. (Low) Make fine rate configurable (`config.py` or DB) (0.5–1 hour) ⚠️

---

If you'd like, I can:
- Create an **annotated image** (SVG overlay of your diagram) showing implemented vs missing nodes, or
- Start implementing the top priority (scheduled jobs for due reminders and low-stock). 

Tell me which you prefer and I’ll proceed. 🙌
