import requests
import json
import pandas as pd
from datetime import datetime

def verify():
    print("🚀 Starting LIVE God Query API Verification...")
    
    url = "http://localhost:28000/v1/data/query"
    
    # 1. Test Legacy Fallback (FRED)
    # CPILFESL exists in the 'fred' monolithic symbol in our silver library
    payload = {
        "requests": [
            {
                "symbol": "CPILFESL",
                "adapter_type": "fred",
                "params": {}
            }
        ],
        "start_date": "2024-01-01"
    }
    
    print(f"\n📡 Sending Legacy Fallback request to {url}...")
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        result = response.json()
        
        # Validation
        meta = result["metadata"].get("CPILFESL", {})
        data = result["data"].get("CPILFESL", [])
        
        print(f"✅ Response received for CPILFESL")
        print(f"📊 Status: {meta.get('status')}")
        print(f"📦 Storage Pattern: {meta.get('storage_pattern')}")
        print(f"🔑 Internal Key: {meta.get('internal_key')}")
        print(f"📈 Rows: {len(data)}")
        
        if meta.get("status") == "SUCCESS" and meta.get("storage_pattern") == "legacy":
            print("\n✨ SUCCESS: Legacy fallback verified for FRED!")
        else:
            print(f"\n❌ FAILURE: Unexpected response metadata: {meta}")
            
    except Exception as e:
        print(f"\n❌ ERROR: Request failed: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Detail: {e.response.text}")

    # 2. Test Interval Mismatch (Expected Failure)
    payload_fail = {
        "requests": [
            {
                "symbol": "CPILFESL",
                "adapter_type": "fred",
                "params": {"interval": "1h"} # Legacy fred doesn't have 1h
            }
        ]
    }
    
    print(f"\n📡 Testing Interval Mismatch (Expect Failure)...")
    try:
        response = requests.post(url, json=payload_fail)
        result = response.json()
        meta = result["metadata"].get("CPILFESL", {})
        
        if meta.get("status") == "FAILED" and "does not support requested interval" in meta.get("error", ""):
            print("✅ SUCCESS: Correctly rejected interval mismatch.")
        else:
            print(f"❌ FAILURE: Did not reject interval mismatch as expected: {meta}")
    except Exception as e:
        print(f"❌ ERROR during mismatch test: {e}")

if __name__ == "__main__":
    verify()
