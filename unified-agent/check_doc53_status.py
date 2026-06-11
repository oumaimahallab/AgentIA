#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check status of document #53"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()

import psycopg2

try:
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'postgres'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'root'),
        client_encoding='utf8'
    )
    
    cur = conn.cursor()
    cur.execute('SELECT id, filename, status, error_msg FROM documents WHERE id = 53')
    result = cur.fetchone()
    
    if result:
        doc_id, filename, status, error_msg = result
        print(f"\n📄 Document #53 Status:")
        print(f"   ID: {doc_id}")
        print(f"   Filename: {filename}")
        print(f"   Status: {status}")
        print(f"   Error: {error_msg}")
    else:
        print("Document #53 not found")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
