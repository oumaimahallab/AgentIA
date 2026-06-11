import os
import sys
import psycopg2

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'postgres'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'root'),
        connect_timeout=5
    )

def print_error(doc_id: int):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT id, filename, status, error_msg, created_at, progress_step, progress_percentage FROM documents WHERE id=%s",
                (doc_id,)
            )
            row = cur.fetchone()
            has_progress = True
        except Exception:
            conn.rollback()
            cur.execute("SELECT id, filename, status, error_msg, created_at FROM documents WHERE id=%s", (doc_id,))
            row = cur.fetchone()
            has_progress = False
        if not row:
            print(f"Document id={doc_id} non trouvé")
            return
        if has_progress:
            doc_id, filename, status, error_msg, created_at, progress_step, progress_percentage = row
            print(
                f"ID: {doc_id}\n"
                f"Filename: {filename}\n"
                f"Status: {status}\n"
                f"Created at: {created_at}\n"
                f"Progress step: {progress_step}\n"
                f"Progress %: {progress_percentage}\n"
                f"Error msg: {error_msg}"
            )
        else:
            doc_id, filename, status, error_msg, created_at = row
            print(f"ID: {doc_id}\nFilename: {filename}\nStatus: {status}\nCreated at: {created_at}\nError msg: {error_msg}")
    except Exception as e:
        print(f"Erreur accès BD: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python print_doc_error.py <doc_id>')
        sys.exit(1)
    try:
        doc_id = int(sys.argv[1])
    except ValueError:
        print('doc_id must be an integer')
        sys.exit(1)
    print_error(doc_id)
