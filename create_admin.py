"""Run this once locally to create an admin account if missing."""
from werkzeug.security import generate_password_hash
import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), "database.db")
con = sqlite3.connect(DB)
cur = con.cursor()

# ensure users table exists (same schema as app.init_db)
cur.execute("CREATE TABLE IF NOT EXISTS users(\n    id INTEGER PRIMARY KEY,\n    name TEXT,\n    email TEXT UNIQUE,\n    password TEXT,\n    role TEXT\n)")

email = input("Admin email [ahmedrazon58@gmail.com]: ") or "ahmedrazon58@gmail.com"
passwd = input("Admin password [22203142]: ") or "22203142"
name = input("Admin name [Sajib Ahmed Razon]: ") or "Sajib Ahmed Razon"

# check if exists
existing = cur.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
if existing:
    print("Admin already exists:", existing[2])
else:
    cur.execute("INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)", (name, email, generate_password_hash(passwd), "admin"))
    con.commit()
    print("Admin created", email)

con.close()