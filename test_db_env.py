#!/usr/bin/env python
import psycopg2
import os

# Set environment variables
os.environ['PGHOST'] = 'localhost'
os.environ['PGPORT'] = '5432'
os.environ['PGDATABASE'] = 'chronobrain'
os.environ['PGUSER'] = 'postgres'
os.environ['PGPASSWORD'] = 'postgres'

print('Variables d\'environnement libpq:')
for k in ['PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD']:
    print(f'  {k}={os.environ.get(k)}')

print('\nTentative de connexion avec psycopg2.connect()...')
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
