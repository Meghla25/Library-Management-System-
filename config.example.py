# Copy this file to config.py and fill in your secrets. Do NOT commit config.py to source control.

# Security
SECRET_KEY = "change_me"

# Email (Gmail recommended - use App Password)
MAIL_EMAIL = "your-email@gmail.com"
MAIL_PASSWORD = "your-gmail-app-password"

# Optional: Stripe (for payments)
STRIPE_SECRET_KEY = "sk_test_..."
STRIPE_PUBLISHABLE_KEY = "pk_test_..."

# Scheduler settings
DUE_REMINDER_DAYS = 2
LOW_STOCK_THRESHOLD = 1

# Notes:
# - Keep this file out of source control. Use environment variables in production.
# - If you prefer, create a .env file and export vars or set them in your host environment.