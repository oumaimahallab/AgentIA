import os
import psycopg2

def get_conn():
    return psycopg2.connect(host=os.getenv('DB_HOST','localhost'), port=os.getenv('DB_PORT','5432'), database=os.getenv('DB_NAME','postgres'), user=os.getenv('DB_USER','postgres'), password=os.getenv('DB_PASSWORD','root'))

def run():
    conn = get_conn()
    cur = conn.cursor()
    print('--- documents row ---')
    try:
        cur.execute("SELECT id, filename, status, progress_step, progress_percentage FROM documents WHERE id=62")
        print(cur.fetchone())
    except Exception as e:
        print('documents query error:', e)
        conn.rollback()
    print('--- user_documents row ---')
    try:
        cur.execute("SELECT id, filename, status, progress_step, progress_percentage FROM user_documents WHERE id=62")
        print(cur.fetchone())
    except Exception as e:
        print('user_documents query error:', e)
        conn.rollback()
    print('--- document_chunks for document_id=62 ---')
    try:
        cur.execute("SELECT id,document_id,chunk_number,length(text) FROM document_chunks WHERE document_id=62 ORDER BY id")
        rows = cur.fetchall()
        print(rows)
    except Exception as e:
        print('document_chunks query error:', e)
        conn.rollback()
    cur.close()
    conn.close()

if __name__ == '__main__':
    run()
