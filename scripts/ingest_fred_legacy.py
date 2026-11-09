import os
import pandas as pd
from arcticdb import Arctic
from adapters.macro.fred import FREDAdapter
from dotenv import load_dotenv

load_dotenv()

def ingest_legacy():
    print("📥 Ingesting legacy FRED data for verification...")
    
    # Use the same URI as the Gateway
    uri = os.getenv("ARCTIC_URI", "lmdb:///tmp/arctic_data")
    ac = Arctic(uri)
    
    # Ensure silver library exists
    if "silver" not in ac.list_libraries():
        ac.create_library("silver")
    
    lib = ac["silver"]
    
    # Fetch some data
    adapter = FREDAdapter("CPILFESL")
    # Small range for speed
    raw = adapter.fetch_raw(observation_start="2024-01-01")
    bronze = adapter.to_bronze(raw)
    df = adapter.to_silver(bronze)
    
    print(f"📊 Fetched {len(df)} rows. Saving to 'fred' symbol...")
    lib.write("fred", df)
    
    print("✨ Legacy ingestion complete!")
    print(f"Verified symbols: {lib.list_symbols()}")

if __name__ == "__main__":
    ingest_legacy()
