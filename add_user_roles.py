#!/usr/bin/env python3
"""Migration : ajoute la colonne role aux utilisateurs existants (sans charger Flask)."""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

ROLE_ADMIN = 'admin'
ROLE_USER = 'user'


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'postgres'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'root'),
        connect_timeout=5,
    )


def migrate():
    print("Migration des rôles utilisateurs...")
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS users 
               (id SERIAL PRIMARY KEY, email TEXT UNIQUE, name TEXT, password TEXT,
                role VARCHAR(20) DEFAULT 'user')"""
        )
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user'")
        c.execute("UPDATE users SET role = %s WHERE role IS NULL", (ROLE_USER,))
        c.execute("UPDATE users SET role = %s WHERE email = %s", (ROLE_ADMIN, 'admin@inetum.com'))
        c.execute(
            "SELECT setval(pg_get_serial_sequence('users', 'id'), "
            "(SELECT COALESCE(MAX(id), 1) FROM users), true)"
        )
        conn.commit()

        c.execute("SELECT email, name, COALESCE(role, %s) FROM users ORDER BY email", (ROLE_USER,))
        rows = c.fetchall()
        print("\nUtilisateurs :")
        for email, name, role in rows:
            print(f"  - {email} ({name}) -> role={role}")
        print("\n[OK] Migration terminee.")
        print("\nPour promouvoir un admin :")
        print("  UPDATE users SET role = 'admin' WHERE email = 'nouveau.admin@example.com';")
    finally:
        conn.close()


if __name__ == '__main__':
    migrate()
