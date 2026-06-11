#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Monitor document #53 transcription progress"""

import os
import sys
import time
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv()

def check_status():
    """Check document #53 status"""
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
        cur.execute('SELECT status, error_msg FROM documents WHERE id = 53')
        result = cur.fetchone()
        
        cur.close()
        conn.close()
        
        return result
    except Exception as e:
        return None

print("\n📋 MONITORING Document #53 Transcription")
print("=" * 60)

last_status = None
check_count = 0
max_checks = 60  # Check for up to 60 times (with 5 sec delay = 5 minutes)

while check_count < max_checks:
    status, error = check_status()
    
    if status and (status != last_status or check_count == 0):
        timestamp = time.strftime("%H:%M:%S")
        print(f"\n[{timestamp}] Status: {status}")
        if error:
            print(f"  Error: {error}")
        last_status = status
        
        if status == "Ingéré":
            print("\n✅ TRAITEMENT COMPLÉTÉ!")
            break
        elif status == "Erreur":
            print("\n❌ ERREUR DÉTECTÉE!")
            break
    
    check_count += 1
    time.sleep(5)

print("\n" + "=" * 60)
print("Fin du monitoring.")
