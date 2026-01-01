"""Run this to send a quick test email using the app's send_email helper.

Usage:
  python send_test_email.py [recipient]

If no recipient is provided, the script will prompt for one.
"""
import sys
import os
from app import send_email

if len(sys.argv) > 1:
    recipient = sys.argv[1]
else:
    recipient = os.environ.get('TEST_EMAIL') or input('Send test email to (email): ')

ok = send_email(recipient, 'LMS test email', 'This is a test email from your Library Management System.')
print('Email sent:', ok)