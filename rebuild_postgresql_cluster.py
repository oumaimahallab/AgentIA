#!/usr/bin/env python3
"""
Script to rebuild PostgreSQL cluster with UTF-8 encoding
This is necessary because the current cluster is using a non-UTF-8 locale (likely LATIN1)
and causing Unicode decoding errors when psycopg2 tries to connect
"""
import os
import subprocess
import shutil
import time

PG_BIN = r"C:\Program Files\PostgreSQL\17\bin"
PG_DATA = r"C:\Program Files\PostgreSQL\17\data"
PG_SERVICE = "postgresql-x64-17"

print("⚠️  This will rebuild the PostgreSQL cluster with UTF-8 encoding")
print("✅ A backup has already been created at: C:\\Users\\maup10458\\Desktop\\AG\\pg_backup_full.sql")

# Stop PostgreSQL service
print("\n1️⃣ Stopping PostgreSQL service...")
try:
    subprocess.run(["net", "stop", PG_SERVICE], capture_output=True, check=False)
    time.sleep(2)
    print("   ✅ Service stopped")
except Exception as e:
    print(f"   ⚠️  Error stopping service: {e}")

# Backup current data directory
print("\n2️⃣ Backing up current data directory...")
backup_dir = f"{PG_DATA}_backup_{int(time.time())}"
try:
    shutil.move(PG_DATA, backup_dir)
    print(f"   ✅ Old data backed up to: {backup_dir}")
except Exception as e:
    print(f"   ❌ Error: {e}")
    exit(1)

# Remove old data directory if exists
if os.path.exists(PG_DATA):
    try:
        shutil.rmtree(PG_DATA)
        print(f"   ✅ Removed old {PG_DATA}")
    except:
        pass

# Create new data directory
print("\n3️⃣ Creating new data directory...")
os.makedirs(PG_DATA, exist_ok=True)
print(f"   ✅ Created {PG_DATA}")

# Run initdb with UTF-8 encoding and C locale
print("\n4️⃣ Initializing PostgreSQL cluster with UTF-8 and C locale...")
initdb_cmd = [
    os.path.join(PG_BIN, "initdb.exe"),
    "-D", PG_DATA,
    "-E", "UTF8",
    "--locale=C",
    "-U", "postgres",
    "-A", "md5",
    "-w"
]

try:
    result = subprocess.run(initdb_cmd, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        print("   ✅ Cluster initialized successfully with UTF-8!")
    else:
        print(f"   ⚠️  initdb output: {result.stdout}")
        print(f"   ❌ Error: {result.stderr}")
except Exception as e:
    print(f"   ❌ Error running initdb: {e}")
    exit(1)

# Start PostgreSQL service
print("\n5️⃣ Starting PostgreSQL service...")
try:
    subprocess.run(["net", "start", PG_SERVICE], capture_output=True, check=False)
    time.sleep(3)
    print("   ✅ Service started")
except Exception as e:
    print(f"   ⚠️  Error starting service: {e}")

print("\n✅ Cluster rebuild complete!")
print("\nNext steps:")
print("1. Set password for postgres user:")
print("   psql -U postgres -c \"ALTER USER postgres WITH PASSWORD 'root';\"")
print("2. Restore from backup:")
print("   psql -U postgres < C:\\Users\\maup10458\\Desktop\\AG\\pg_backup_full.sql")
print("3. Test connection with psycopg2")
