import pandas as pd
import uuid
import time
from shared.clickhouse import ClickHouseStorage
from shared.registry import MetadataRegistry
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify-clickhouse")

def verify_migration():
    storage = ClickHouseStorage()
    registry = MetadataRegistry()

    # 1. Initialize Schema
    logger.info("Initializing ClickHouse Schema...")
    storage.init_schema()

    symbol = f"test.ticker_{uuid.uuid4().hex[:8]}"
    library = "silver"
    
    # 2. Ingest Version 1
    logger.info(f"Ingesting Version 1 for {symbol}...")
    batch1_id = str(uuid.uuid4())
    df1 = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-01-01", "2026-01-02"]),
        "value": [10.0, 11.0]
    })
    
    asset_id = registry.register_asset(symbol, library)
    lineage1 = registry.start_lineage(asset_id, "run_v1", batch1_id)
    
    # Serialize and insert
    from shared.clickhouse import ClickHouseIOManager
    iom = ClickHouseIOManager()
    df1_serialized = iom._serialize_df(df1, symbol, batch1_id)
    storage.insert_df(f"{library}_data", df1_serialized)
    
    registry.commit_lineage(lineage1, version_id=1, batch_id=batch1_id)

    # 3. Ingest Version 2 (New data)
    logger.info(f"Ingesting Version 2 for {symbol}...")
    batch2_id = str(uuid.uuid4())
    df2 = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-01-03"]),
        "value": [12.0]
    })
    
    lineage2 = registry.start_lineage(asset_id, "run_v2", batch2_id)
    df2_serialized = iom._serialize_df(df2, symbol, batch2_id)
    storage.insert_df(f"{library}_data", df2_serialized)
    
    registry.commit_lineage(lineage2, version_id=2, batch_id=batch2_id)

    # 4. Verify PIT Read (Version 1)
    logger.info("Verifying Point-in-Time Read (Version 1)...")
    res1 = storage.get_symbol_data(library, symbol, version_id=1)
    logger.info(f"Version 1 Rows: {len(res1)}")
    assert len(res1) == 2, f"Expected 2 rows for V1, got {len(res1)}"
    assert all(res1["batch_id"].astype(str) == batch1_id), "Data from wrong batch in V1"

    # 5. Verify Latest Read (Version 2)
    logger.info("Verifying Latest Read (Version 2)...")
    res2 = storage.get_symbol_data(library, symbol, version_id=2)
    logger.info(f"Version 2 Rows: {len(res2)}")
    assert len(res2) == 3, f"Expected 3 rows for V2, got {len(res2)}"
    
    # 6. Verify Cleanup/Health
    logger.info("Health Check: " + ("OK" if storage.check_health() else "FAILED"))

    logger.info("✅ ClickHouse Migration Verified Successfully!")

if __name__ == "__main__":
    try:
        verify_migration()
    except Exception as e:
        logger.error(f"Verification Failed: {e}")
        exit(1)
