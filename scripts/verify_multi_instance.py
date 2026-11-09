import os
import sys
from pathlib import Path
import pandas as pd

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from shared.registry import MetadataRegistry
from shared.arctic import ArcticStorage

def verify_multi_instance():
    registry = MetadataRegistry()
    storage = ArcticStorage()
    
    symbol = "MULTI_TEST"
    library = "bronze"
    label_1 = "alpha"
    label_2 = "beta"
    
    print(f"=== Starting Multi-Instance Verification for {symbol} ===")
    
    try:
        # 1. Register two instances of the same symbol
        print(f"Step 1: Registering instances with labels '{label_1}' and '{label_2}'...")
        registry.register_asset(symbol, library, label=label_1, description="First instance")
        registry.register_asset(symbol, library, label=label_2, description="Second instance")
        
        # 2. Write distinct data to both
        print("Step 2: Writing distinct data to both storage paths...")
        lib = storage.get_library(library)
        
        df1 = pd.DataFrame({"instance": ["alpha"], "val": [100]})
        df2 = pd.DataFrame({"instance": ["beta"], "val": [200]})
        
        # Note: ArcticIOManager handles the mapping, but here we test ArcticStorage logic
        # which uses _get_storage_symbol internally for its operations.
        # However, for writing we'll use the mapped names to verify isolation.
        storage_symbol_1 = storage._get_storage_symbol(symbol, label_1)
        storage_symbol_2 = storage._get_storage_symbol(symbol, label_2)
        
        lib.write(storage_symbol_1, df1)
        lib.write(storage_symbol_2, df2)
        
        # 3. Verify existence and isolation
        print("Step 3: Verifying data isolation...")
        assets = registry.get_all_assets()
        matches = [a for a in assets if a['symbol'] == symbol]
        print(f" - Found {len(matches)} matches in registry (expected 2)")
        assert len(matches) == 2
        
        info1 = storage.get_symbol_info(library, symbol, label=label_1)
        info2 = storage.get_symbol_info(library, symbol, label=label_2)
        
        print(f" - Instance '{label_1}': {info1}")
        print(f" - Instance '{label_2}': {info2}")
        
        assert info1['row_count'] == 1
        assert info2['row_count'] == 1
        
        # 4. Test partial deletion
        print(f"Step 4: Deleting instance '{label_1}'...")
        storage.delete_symbol(library, symbol, label=label_1)
        registry.delete_asset_metadata(symbol, library, label=label_1)
        
        # 5. Verify partial deletion
        print("Step 5: Verifying only one instance remains...")
        assets_after = registry.get_all_assets()
        matches_after = [a for a in assets_after if a['symbol'] == symbol]
        print(f" - Found {len(matches_after)} matches in registry (expected 1)")
        assert len(matches_after) == 1
        assert matches_after[0]['label'] == label_2
        
        info1_after = storage.get_symbol_info(library, symbol, label=label_1)
        info2_after = storage.get_symbol_info(library, symbol, label=label_2)
        
        assert info1_after['row_count'] == 0
        assert info2_after['row_count'] == 1
        print(f" - Instance '{label_1}' is GONE")
        print(f" - Instance '{label_2}' is STILL HERE")
        
        print("\n✅ Multi-Instance Verification SUCCESSFUL!")
        
        # Cleanup
        storage.delete_symbol(library, symbol, label=label_2)
        registry.delete_asset_metadata(symbol, library, label=label_2)
        
    except Exception as e:
        print(f"\n❌ Verification FAILED: {e}")
        sys.exit(1)

if __name__ == "__main__":
    verify_multi_instance()
