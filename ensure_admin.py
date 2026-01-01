import sqlite3
import os
from werkzeug.security import generate_password_hash

DB = os.path.join(os.path.dirname(__file__), "database.db")
con = sqlite3.connect(DB)
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT,email TEXT UNIQUE,password TEXT,role TEXT)")
admin = cur.execute("SELECT id,email FROM users WHERE role=?", ("admin",)).fetchone()
if admin:
    print("ADMIN_EXISTS", admin[1])
else:
    cur.execute("INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
                ("Sajib Ahmed Razon", "ahmedrazon58@gmail.com", generate_password_hash("22203142"), "admin"))
    con.commit()
    print("ADMIN_CREATED", "ahmedrazon58@gmail.com")
con.close()
