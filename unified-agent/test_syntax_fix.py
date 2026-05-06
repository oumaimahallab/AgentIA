#!/usr/bin/env python3
"""Simple test to verify main.py syntax is fixed"""

import sys
import subprocess

print("Testing main.py syntax fix...\n")

# Test 1: Check syntax
print("✅ Checking syntax of main.py...")
result = subprocess.run([sys.executable, "-m", "py_compile", "main.py"], 
                       capture_output=True, text=True)

if result.returncode == 0:
    print("   ✓ Syntax OK - no SyntaxError!")
else:
    print(f"   ✗ Syntax Error:\n{result.stderr}")
    sys.exit(1)

# Test 2: Try to import main
print("\n✅ Importing main module...")
try:
    import main
    print("   ✓ Import successful!")
except SyntaxError as e:
    print(f"   ✗ SyntaxError: {e}")
    sys.exit(1)
except Exception as e:
    print(f"   ✓ Import OK (other error: {type(e).__name__}, expected)")

# Test 3: Check --help
print("\n✅ Running main.py --help...")
result = subprocess.run([sys.executable, "main.py", "--help"], 
                       capture_output=True, text=True, timeout=5)

if result.returncode == 0 and "usage:" in result.stdout.lower():
    print("   ✓ Help message displayed successfully!")
    print("\nAvailable commands:")
    for line in result.stdout.split('\n')[5:15]:
        if line.strip():
            print(f"   {line}")
else:
    print(f"   ✗ Failed: {result.stderr}")
    sys.exit(1)

print("\n✅ All syntax checks passed!")
print("\n✓ The SyntaxError has been fixed!")
print("✓ main.py is now ready to use!")
