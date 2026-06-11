#!/usr/bin/env python3
import sys
print(f"Python: {sys.executable}")
print(f"Version: {sys.version}")

try:
    import psycopg2
    print("[OK] psycopg2 installed")
except ImportError as e:
    print(f"[ERROR] psycopg2 error: {e}")

try:
    import flask
    print("[OK] flask installed")
except ImportError as e:
    print(f"[ERROR] flask error: {e}")

try:
    import groq
    print("[OK] groq installed")
except ImportError as e:
    print(f"[ERROR] groq error: {e}")

print("\n--- Attempting to import app.py ---")
sys.path.insert(0, 'unified-agent/ui')
try:
    import app
    print("[OK] app.py loaded successfully")
except Exception as e:
    print(f"[ERROR] app.py error: {e}")
    import traceback
    traceback.print_exc()
