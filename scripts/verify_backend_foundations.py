import os
import sys
from pathlib import Path
import pandas as pd
import uuid

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from shared.registry import MetadataRegistry
from shared.clickhouse import ClickHouseStorage, ClickHouseIOManager

def verify_backend_foundations():
    registry = MetadataRegistry()
    storage = ClickHouseStorage()
    io_manager = ClickHouseIOManager()
    
    symbol = f"test.foundations_{uuid.uuid4().hex[:8]}"
    library = "bronze"
    batch_id = str(uuid.uuid4())
    
    # 1. Setup - Register and Write
    print(f"Setting up ClickHouse test data for {symbol} in {library}...")
    asset_id = registry.register_asset(symbol, library, "Test description")
    lineage_id = registry.start_lineage(asset_id, "test_run", batch_id)
    
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0], "timestamp": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])})
    df_serialized = io_manager._serialize_df(df, symbol, batch_id)
    storage.insert_df(f"{library}_data", df_serialized)
    registry.commit_lineage(lineage_id, version_id=lineage_id, batch_id=batch_id)
    
    # 2. Verify existence
    assets = registry.get_all_assets()
    assert any(a['symbol'] == symbol and a['library'] == library for a in assets)
    
    info = storage.get_symbol_info(library, symbol)
    assert info['row_count'] == 3
    print(f"Verified existence in ClickHouse: {info}")
    
    # 3. Test Deletion
    print(f"Triggering ClickHouse deletion...")
    storage.delete_symbol(library, symbol)
    registry.delete_asset_metadata(symbol, library)
    
    # 4. Final Verification
    # Note: ClickHouse DELETE is asynchronous, so we might still see rows for a moment
    # but the Registry entry should be gone immediately.
    assets_after = registry.get_all_assets()
    assert not any(a['symbol'] == symbol and a['library'] == library for a in assets_after)
    
    print("Backend foundations verified successfully!")

if __name__ == "__main__":
    try:
        verify_backend_foundations()
    except Exception as e:
        print(f"Verification Failed: {e}")
        sys.exit(1)
