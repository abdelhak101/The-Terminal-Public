import pandas as pd
import numpy as np
import uuid
from datetime import datetime, timedelta
from shared.clickhouse import ClickHouseStorage

def main():
    storage = ClickHouseStorage()
    if not storage.check_health():
        print("ClickHouse not reachable.")
        return

    symbol = "TEST.LIFECYCLE"
    batch_id = str(uuid.uuid4())
    
    # 1. Inject Fake Historical Data (> 1 year old)
    old_date = datetime.now() - timedelta(days=400)
    print(f"Injecting data for {symbol} dated {old_date}...")
    
    df = pd.DataFrame({
        "timestamp": [old_date],
        "symbol": [symbol],
        "batch_id": [batch_id],
        "value": [100.0],
        "open": [100.0],
        "high": [105.0],
        "low": [95.0],
        "close": [102.0],
        "volume": [1000.0],
        "adjusted_close": [102.0]
    })
    
    # We use Silver layer for testing re-compression
    storage.insert_df("silver_data", df)
    print("Data injected into silver_data.")

    # 2. Inject Recent Data (< 90 days)
    recent_date = datetime.now() - timedelta(days=10)
    print(f"Injecting recent data dated {recent_date}...")
    df_recent = pd.DataFrame({
        "timestamp": [recent_date],
        "symbol": [symbol],
        "batch_id": [batch_id],
        "value": [110.0],
        "open": [110.0],
        "high": [115.0],
        "low": [105.0],
        "close": [112.0],
        "volume": [1200.0],
        "adjusted_close": [112.0]
    })
    storage.insert_df("silver_data", df_recent)
    print("Recent data injected.")

    # 3. Verify System Tables
    print("\nVerifying Storage Policies...")
    
    # Check parts to see if ClickHouse identifies the old data as needing re-compression or having a specific TTL
    # Note: actual re-compression happens on merge, but we can check if the parts are created in the right partitions.
    parts_sql = """
        SELECT 
            partition, 
            name, 
            active, 
            bytes_on_disk, 
            data_compressed_bytes, 
            data_uncompressed_bytes,
            default_compression_codec
        FROM system.parts 
        WHERE table = 'silver_data' AND active
        ORDER BY modification_time DESC
        LIMIT 5
    """
    parts_df = storage.query_df(parts_sql)
    print("Recent parts in silver_data:")
    print(parts_df)

    # Check columns for codecs
    cols_sql = """
        SELECT name, compression_codec 
        FROM system.columns 
        WHERE table = 'silver_data' AND name IN ('timestamp', 'value')
    """
    cols_df = storage.query_df(cols_sql)
    print("\nColumn Codecs:")
    print(cols_df)

    print("\nLifecycle verification script completed.")

if __name__ == "__main__":
    main()
