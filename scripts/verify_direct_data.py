import requests
import pandas as pd
from arcticdb import Arctic
import os
import sys

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
ARCTIC_URI = os.getenv("ARCTIC_URI", "lmdb:///tmp/arctic_data")

def test_direct_access():
    print("--- Starting Direct Data Access API Verification ---")
    
    # 1. Find a symbol to test with
    ac = Arctic(ARCTIC_URI)
    if "silver" not in ac.list_libraries():
        print("Error: 'silver' library not found. Please run ingestion first.")
        sys.exit(1)
        
    lib = ac["silver"]
    symbols = lib.list_symbols()
    if not symbols:
        print("Error: No symbols found in 'silver' library.")
        sys.exit(1)
        
    test_symbol = symbols[0]
    print(f"Testing with symbol: {test_symbol}")

    # 2. Basic Retrieval
    print(f"\n1. Testing basic retrieval: GET /v1/data/silver/{test_symbol}")
    resp = requests.get(f"{GATEWAY_URL}/v1/data/silver/{test_symbol}")
    if resp.status_code != 200:
        print(f"FAILED: Expected 200, got {resp.status_code}")
        print(resp.text)
        sys.exit(1)
    
    data = resp.json()
    print(f"SUCCESS: Retrieved {len(data)} records")
    if len(data) > 0:
        print(f"First record keys: {list(data[0].keys())}")

    # 3. Temporal Slicing
    if len(data) > 2:
        df_full = pd.DataFrame(data)
        df_full['timestamp'] = pd.to_datetime(df_full['timestamp'])
        start_date = df_full['timestamp'].iloc[1].isoformat()
        end_date = df_full['timestamp'].iloc[-2].isoformat()
        
        print(f"\n2. Testing temporal slicing: start_date={start_date}, end_date={end_date}")
        resp = requests.get(
            f"{GATEWAY_URL}/v1/data/silver/{test_symbol}",
            params={"start_date": start_date, "end_date": end_date}
        )
        sliced_data = resp.json()
        print(f"SUCCESS: Retrieved {len(sliced_data)} records (Full: {len(data)})")
        
        # Verify slicing
        df_sliced = pd.DataFrame(sliced_data)
        df_sliced['timestamp'] = pd.to_datetime(df_sliced['timestamp'])
        if df_sliced['timestamp'].min() < pd.Timestamp(start_date) or df_sliced['timestamp'].max() > pd.Timestamp(end_date):
             print(f"FAILED: Slicing logic incorrect. Min: {df_sliced['timestamp'].min()}, Max: {df_sliced['timestamp'].max()}")
             sys.exit(1)
        print("Slicing verified.")

    # 4. Column Filtering
    if len(data) > 0:
        all_cols = list(data[0].keys())
        if len(all_cols) > 1:
            target_col = [c for c in all_cols if c != "timestamp"][0]
            print(f"\n3. Testing column filtering: columns=timestamp,{target_col}")
            resp = requests.get(
                f"{GATEWAY_URL}/v1/data/silver/{test_symbol}",
                params={"columns": f"timestamp,{target_col}"}
            )
            col_data = resp.json()
            if len(col_data) > 0:
                keys = set(col_data[0].keys())
                expected = {"timestamp", target_col}
                if keys != expected:
                    print(f"FAILED: Expected columns {expected}, got {keys}")
                    sys.exit(1)
                print(f"SUCCESS: Only requested columns returned: {keys}")

    # 5. Pagination
    print("\n4. Testing pagination: limit=2, offset=1")
    resp = requests.get(
        f"{GATEWAY_URL}/v1/data/silver/{test_symbol}",
        params={"limit": 2, "offset": 1}
    )
    paged_data = resp.json()
    if len(paged_data) != 2:
        print(f"FAILED: Expected 2 records, got {len(paged_data)}")
        # Note: could be less if test_symbol only has 1-2 records total
        if len(data) >= 3:
            sys.exit(1)
    
    if len(data) >= 3:
        # Check if it actually skipped the first one and took 2 and 3
        if paged_data[0] != data[1] or paged_data[1] != data[2]:
            print("FAILED: Pagination data mismatch")
            sys.exit(1)
    print(f"SUCCESS: Pagination verified (limit=2, offset=1)")

    # 6. Error Cases
    print("\n5. Testing Error Case: Non-existent symbol")
    resp = requests.get(f"{GATEWAY_URL}/v1/data/silver/non_existent_symbol_12345")
    if resp.status_code != 404:
        print(f"FAILED: Expected 404, got {resp.status_code}")
        sys.exit(1)
    print("SUCCESS: 404 returned for non-existent symbol")

    print("\n6. Testing Error Case: Invalid library")
    resp = requests.get(f"{GATEWAY_URL}/v1/data/invalid_lib_name/{test_symbol}")
    if resp.status_code != 400:
        print(f"FAILED: Expected 400, got {resp.status_code}")
        sys.exit(1)
    print("SUCCESS: 400 returned for invalid library")

    print("\n--- All Direct Data Access API Verifications Passed ---")

if __name__ == "__main__":
    test_direct_access()
