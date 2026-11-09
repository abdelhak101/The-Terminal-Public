import os
import sys
from unittest.mock import MagicMock, patch

# Mock dagster before importing definitions
mock_dagster = MagicMock()
class MockAssetKey:
    def __init__(self, path):
        self.path = path
mock_dagster.AssetKey = MockAssetKey

def mock_multi_asset(outs=None, **kwargs):
    def decorator(fn):
        mock_assets_def = MagicMock()
        mock_assets_def.keys = [out.key for out in outs.values()] if outs else []
        mock_assets_def.node_def.name = kwargs.get("name", "unknown")
        return mock_assets_def
    return decorator

mock_dagster.multi_asset = mock_multi_asset
mock_dagster.AssetOut = lambda key=None: MagicMock(key=key)

sys.modules["dagster"] = mock_dagster

# Mock yfinance
sys.modules["yfinance"] = MagicMock()

# Mock opentelemetry
sys.modules["opentelemetry"] = MagicMock()
sys.modules["opentelemetry.propagate"] = MagicMock()
sys.modules["opentelemetry.trace"] = MagicMock()

# Mock prometheus_client
sys.modules["prometheus_client"] = MagicMock()

# Mock confluent_kafka
sys.modules["confluent_kafka"] = MagicMock()

# Mock arcticdb
sys.modules["arcticdb"] = MagicMock()

# Add project root to path
sys.path.append(os.getcwd())

from shared.registry import MetadataRegistry

# Mock get_active_sources to prevent DB connection on import of definitions
with patch.object(MetadataRegistry, 'get_active_sources', return_value=[]):
    from infrastructure.docker.orchestration.definitions import load_dynamic_assets

from unittest.mock import patch

def verify():
    registry = MetadataRegistry()
    
    print("Step 1: Registering AAPL via Yahoo adapter...")
    # Mocking DB connection for this script since I might not have a live DB reachable from here
    with patch('shared.registry.psycopg2.connect') as mock_connect:
        mock_conn = mock_connect.return_value
        mock_conn.__enter__.return_value = mock_conn
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        
        # Simulate successful insert
        registry.add_source("yahoo", "AAPL")
        print("Source registered in mock DB.")
        
        # Step 2: Simulate loading assets
        print("Step 2: Loading dynamic assets...")
        # Mock get_active_sources to return the registered source
        with patch.object(MetadataRegistry, 'get_active_sources', return_value=[
            {"adapter_type": "yahoo", "identifier": "AAPL", "config": {}}
        ]):
            assets = load_dynamic_assets()
            
            print(f"Loaded {len(assets)} asset definitions.")
            for asset in assets:
                # asset is an AssetsDefinition
                print(f"Asset Name: {asset.node_def.name}")
                # Check keys
                for key in asset.keys:
                    print(f"  Asset Key: {key.path}")
            
            # Validation
            expected_keys = [["bronze", "yahoo_finance", "aapl"], ["silver", "yahoo_finance", "aapl"]]
            found_keys = [list(key.path) for asset in assets for key in asset.keys]
            
            for ek in expected_keys:
                if ek in found_keys:
                    print(f"SUCCESS: Found expected key {ek}")
                else:
                    print(f"FAILURE: Could not find expected key {ek}")
                    sys.exit(1)

if __name__ == "__main__":
    verify()
