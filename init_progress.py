#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import requests
import time

# Initialize progress columns via API
print("🔄 Initializing progress columns...")

try:
    response = requests.post(
        'http://localhost:5005/api/admin/init-progress',
        json={'email': 'admin@inetum.com'}
    )
    
    if response.status_code == 200:
        print("✅ Progress columns initialized successfully!")
        print(response.json())
    else:
        print(f"⚠ Response: {response.status_code}")
        print(response.text)
        
except Exception as e:
    print(f"❌ Error: {e}")
    print("Make sure Flask server is running on port 5005")
