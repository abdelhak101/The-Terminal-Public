import os
import pandas as pd
from arcticdb import Arctic
from services.gateway.src.query_engine import QueryEngine
import logging

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reproduce")

def reproduce():
    # Use the same URI as manifest
    arctic_uri = "lmdb:///tmp/arctic_data"
    qe = QueryEngine(arctic_uri=arctic_uri)
    
    library = "silver"
    symbol = "fred.cpilfesl_percent_change_default_6fdc9"
    
    print(f"--- Reproducing Data Retrieval for {library}/{symbol} ---")
    
    # 1. Check if library exists
    try:
        ac = Arctic(arctic_uri)
        libs = ac.list_libraries()
        print(f"Libraries: {libs}")
        if library not in libs:
            print(f"FAILED: Library {library} not found")
            return
        
        lib = ac[library]
        symbols = lib.list_symbols()
        print(f"Symbols in {library}: {symbols[:10]}... (Total: {len(symbols)})")
        
        if symbol not in symbols:
            print(f"FAILED: Symbol {symbol} not found in {library}")
            # Try to see if there's something similar
            matches = [s for s in symbols if "cpilfesl" in s.lower()]
            print(f"Similar symbols: {matches}")
            return
        
        # 2. Try direct read (like in Gateway)
        print(f"Attempting lib.read('{symbol}')")
        item = lib.read(symbol)
        df = item.data
        print(f"Read successful. Type: {type(df)}")
        if isinstance(df, pd.DataFrame):
            print(f"Columns: {df.columns.tolist()}")
            print(f"Index name: {df.index.name}")
            print(f"Row count: {len(df)}")
        
        # 3. Try QueryEngine.read_direct
        print(f"\nAttempting QueryEngine.read_direct('{library}', '{symbol}')")
        try:
            data = qe.read_direct(library, symbol)
            print(f"SUCCESS: Retrieved {len(data)} records")
        except Exception as e:
            print(f"FAILED: read_direct raised {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    reproduce()
