#!/usr/bin/env python3
import os
import sys

# Set LANG=C BEFORE importing psycopg2
os.environ['LANG'] = 'C'
os.environ['LC_ALL'] = 'C'
os.environ['PGCLIENTENCODING'] = 'UTF8'

import psycopg2

# Utiliser la variable d'environnement PGPASSWORD au lieu de la passer directement
os.environ['PGPASSWORD'] = 'root'

dsn = 'dbname=chronobrain user=postgres host=localhost port=5432'
print('Test avec PGPASSWORD environment variable et LANG=C...')

try:
    # Don't pass password in DSN, use environment variable instead
    conn = psycopg2.connect(dsn)
    print('✅✅✅ CONNEXION RÉUSSIE!')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM documents')
    count = c.fetchone()[0]
    print(f'📊 Documents: {count}')
    
    # Show server encoding
    c.execute('SHOW server_encoding')
    enc = c.fetchone()[0]
    print(f'📝 Server encoding: {enc}')
    
    c.execute('SHOW client_encoding')
    client_enc = c.fetchone()[0]
    print(f'📝 Client encoding: {client_enc}')
    
    conn.close()
except Exception as e:
    print(f'❌ ERREUR: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()
