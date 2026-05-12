import os
import psycopg2
from dotenv import load_dotenv

# Path to the global .env
env_path = r'c:\Users\maup10458\Desktop\AG\.env'
load_dotenv(env_path)

print(f"Connecting to {os.getenv('DB_NAME')} on {os.getenv('DB_HOST')}...")

try:
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'postgres'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'root')
    )
    print("Connection successful!")
    c = conn.cursor()
    c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    tables = c.fetchall()
    print("Tables found:", [t[0] for t in tables])
    
    # Try to select from users
    try:
        c.execute("SELECT email, name FROM users")
        users = c.fetchall()
        print("Users in DB:", users)
    except Exception as inner_e:
        print(f"Error reading users: {inner_e}")
    
    conn.close()
except Exception as e:
    print(f"Error: {e}")
