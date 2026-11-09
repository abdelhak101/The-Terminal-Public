
import os
import logging
import pandas as pd
from shared.registry import MetadataRegistry
from shared.arctic import ArcticStorage

logging.basicConfig(level=logging.INFO)

def check():
    print("Initializing Metadata Registry...")
    reg = MetadataRegistry()
    print("Initializing Arctic Storage...")
    storage = ArcticStorage()
    
    symbol = "yahoo_finance.aapl_daily_main2_1d_e92df"
    library = "silver"
    label = "main"
    
    print(f"\n--- Checking Symbol: {symbol} in {library} ({label}) ---")
    
    # Check Registry
    assets = reg.get_all_assets()
    found_in_reg = False
    for a in assets:
        if a['symbol'] == symbol and a['library'] == library and a['label'] == label:
            print(f"FOUND in Metadata Registry: {a}")
            found_in_reg = True
            break
    if not found_in_reg:
        print("NOT FOUND in Metadata Registry.")

    # Check ArcticDB
    lib = storage.get_library(library)
    storage_symbol = storage._get_storage_symbol(symbol, label)
    print(f"Storage symbol: {storage_symbol}")
    
    if storage_symbol in lib.list_symbols():
        print(f"FOUND in ArcticDB.")
        desc = lib.get_description(storage_symbol)
        print(f"Row count: {desc.row_count}")
        print(f"Last updated: {desc.last_update_time}")
        
        # Fetch data slice
        print("\nFetching data slice (page 1, size 5)...")
        data_res = storage.get_symbol_data_slice(library, symbol, label=label, page=1, size=5)
        print(f"Data rows: {len(data_res['rows'])}")
        if data_res['rows']:
            print("First row sample:")
            print(data_res['rows'][0])
            
        # Fetch snapshot
        print("\nFetching snapshot...")
        snapshot = storage.get_symbol_snapshot(library, symbol, label=label)
        print(f"Snapshot points: {len(snapshot)}")
        if snapshot:
            print("First snapshot point sample:")
            print(snapshot[0])
    else:
        print("NOT FOUND in ArcticDB.")
        print(f"Available symbols in {library}: {lib.list_symbols()}")

if __name__ == "__main__":
    check()
