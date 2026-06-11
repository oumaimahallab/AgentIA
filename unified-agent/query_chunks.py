import os,psycopg2
conn=psycopg2.connect(host=os.getenv('DB_HOST','localhost'),port=os.getenv('DB_PORT','5432'),database=os.getenv('DB_NAME','postgres'),user=os.getenv('DB_USER','postgres'),password=os.getenv('DB_PASSWORD','root'))
cur=conn.cursor()
cur.execute("SELECT id, document_id, chunk_number, left(text,60), created_at FROM document_chunks ORDER BY id DESC LIMIT 20")
rows=cur.fetchall()
print('document_chunks (latest):')
for r in rows:
    print(r)
cur.execute("SELECT id, filename, status, total_chunks FROM documents ORDER BY id DESC LIMIT 20")
rows=cur.fetchall()
print('\ndocuments (latest):')
for r in rows:
    print(r)
cur.execute("SELECT id, filename, status FROM user_documents ORDER BY id DESC LIMIT 20")
rows=cur.fetchall()
print('\nuser_documents (latest):')
for r in rows:
    print(r)
cur.close(); conn.close()
