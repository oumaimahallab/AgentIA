import psycopg2
conn = psycopg2.connect('host=localhost port=5432 dbname=postgres user=postgres password=root')
c = conn.cursor()
c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
for row in c.fetchall():
    print(row[0])
