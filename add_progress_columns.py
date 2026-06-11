#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import psycopg2
import sys

conn = None
try:
    conn = psycopg2.connect(
        host='localhost',
        user='root',
        password='root',
        dbname='chronobrain_db',
        client_encoding='utf-8'
    )
    c = conn.cursor()
    
    # Ajouter colonnes progress
    c.execute('''ALTER TABLE documents 
                 ADD COLUMN IF NOT EXISTS progress_step VARCHAR(100) DEFAULT 'En attente',
                 ADD COLUMN IF NOT EXISTS progress_percentage INTEGER DEFAULT 0
    ''')
    conn.commit()
    print('✅ Colonnes progress ajoutées à la table documents')
    
except Exception as e:
    print(f'⚠ Erreur: {str(e)}')
    sys.exit(1)

finally:
    if conn:
        try:
            conn.close()
        except:
            pass
