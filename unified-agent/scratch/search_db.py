import psycopg2
import sys

sys.stdout.reconfigure(encoding='utf-8')

def search():
    conn = psycopg2.connect('host=localhost port=5432 dbname=postgres user=postgres password=root')
    c = conn.cursor()
    c.execute("""
        SELECT chunk_number, text 
        FROM document_chunks 
        WHERE document_id = 65 AND chunk_number IN (5, 6)
        ORDER BY chunk_number
    """)
    for row in c.fetchall():
        print(f"Chunk Number: {row[0]}")
        print(row[1])
        print("="*60)
    conn.close()

if __name__ == '__main__':
    search()
