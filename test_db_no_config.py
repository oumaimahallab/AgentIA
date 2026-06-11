#!/usr/bin/env python
import psycopg2
import os

# Désactiver les fichiers de configuration libpq
os.environ['PGPASSFILE'] = '/dev/null'
os.environ['PGSYSCONFDIR'] = '/dev/null'
os.environ['PGLOCALEDIR'] = ''

# Set environment variables
os.environ['PGHOST'] = 'localhost'
os.environ['PGPORT'] = '5432'
os.environ['PGDATABASE'] = 'chronobrain'
os.environ['PGUSER'] = 'postgres'
os.environ['PGPASSWORD'] = 'postgres'

print('Tentative de connexion AVEC désactiver des fichiers de config...')
try:
    conn = psycopg2.connect()
    print('✅ Connexion réussie!')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM documents')
    count = c.fetchone()[0]
    print(f'📊 Documents: {count}')
    conn.close()
except Exception as e:
    print(f'❌ ERREUR: {e}')
    import traceback
    traceback.print_exc()
