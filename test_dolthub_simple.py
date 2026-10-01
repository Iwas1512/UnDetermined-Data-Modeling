"""Simple test to see if DoltHub options API works"""

import requests

API_URL = "https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master"

print("Testing DoltHub API...")

# Test 1: SHOW TABLES
print("\n1. Testing SHOW TABLES:")
try:
    response = requests.get(API_URL, params={"q": "SHOW TABLES"}, timeout=30)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")

    if response.status_code == 200:
        data = response.json()
        print(f"Success! Found {len(data.get('rows', []))} tables")
        print(data)
    else:
        print(f"ERROR: {response.text}")
except Exception as e:
    print(f"ERROR: {e}")
