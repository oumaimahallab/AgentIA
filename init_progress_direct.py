#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os

# Add parent directories to path
sys.path.insert(0, r'c:\Users\maup10458\Desktop\AG\unified-agent\ui')
sys.path.insert(0, r'c:\Users\maup10458\Desktop\AG\unified-agent')
os.chdir(r'c:\Users\maup10458\Desktop\AG\unified-agent\ui')

# Import the app's database connection function
from app import get_db_connection
import psycopg2

print("🔄 Initializing progress columns via app database...")

conn = get_db_connection()
if not conn:
    print("❌ Failed to connect to database")
    sys.exit(1)

try:
    c = conn.cursor()
    
    # Add progress columns if they don't exist
    c.execute('''
        ALTER TABLE documents 
        ADD COLUMN IF NOT EXISTS progress_step VARCHAR(100) DEFAULT 'En attente',
        ADD COLUMN IF NOT EXISTS progress_percentage INTEGER DEFAULT 0
    ''')
    conn.commit()
    print("✅ Progress columns initialized successfully!")
    
except psycopg2.Error as e:
    print(f"⚠ Database error: {e}")
    conn.rollback()
except Exception as e:
    print(f"❌ Error: {e}")
finally:
    if conn:
        try:
            conn.close()
        except:
            pass
