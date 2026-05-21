import psycopg2
conn = psycopg2.connect('host=localhost port=5432 dbname=postgres user=postgres password=root')
c = conn.cursor()
c.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='sessions'")
for row in c.fetchall():
    print(row)
