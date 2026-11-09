import os
import sys
from unittest.mock import MagicMock, patch

# Mock all dependencies
sys.modules["dagster"] = MagicMock()
class MockAssetKey:
    def __init__(self, path):
        self.path = path
sys.modules["dagster"].AssetKey = MockAssetKey
sys.modules["dagster"].AssetOut = MagicMock
sys.modules["dagster"].multi_asset = lambda **kwargs: lambda fn: MagicMock(node_def=MagicMock(compute_fn=fn), keys=[out.key for out in kwargs.get("outs", {}).values()])
class MockOutput:
    def __init__(self, value, output_name=None, metadata=None):
        self.value = value
        self.output_name = output_name
        self.metadata = metadata
sys.modules["dagster"].Output = MockOutput

sys.modules["yfinance"] = MagicMock()
sys.modules["opentelemetry"] = MagicMock()
sys.modules["opentelemetry.trace"] = MagicMock()
sys.modules["prometheus_client"] = MagicMock()
sys.modules["confluent_kafka"] = MagicMock()
sys.modules["arcticdb"] = MagicMock()

# Add project root to path
sys.path.append(os.getcwd())

import pandas as pd
from shared.registry import MetadataRegistry
from adapters.factory import create_adapter_assets
from adapters.market.yahoo import YahooAdapter

def verify():
    print("--- Starting Incremental Ingestion Verification ---")
    
    adapter = YahooAdapter("MSFT")
    config = {"interval": "1d", "auto_adjust": True, "period": "max"}
    
    # 1. First Run (Bootstrap)
    print("\nStep 1: First Run (Bootstrap)")
    with patch("adapters.factory.MetadataRegistry") as mock_reg_cls:
        mock_reg = mock_reg_cls.return_value
        # No last_ts found
        mock_reg.get_last_observed_timestamp.return_value = None
        
        # Mock fetch returning some history
        bootstrap_df = pd.DataFrame([
            {"Datetime": pd.Timestamp("2024-01-01"), "Close": 300, "Volume": 1000},
            {"Datetime": pd.Timestamp("2024-01-02"), "Close": 305, "Volume": 1100},
        ]).set_index("Datetime")
        
        adapter.fetch_raw = MagicMock(return_value=bootstrap_df)
        
        assets = create_adapter_assets(adapter, config)
        asset_fn = assets[0].node_def.compute_fn
        
        context = MagicMock()
        outputs = list(asset_fn(context))
        
        # Verify fetch was called without start (using period='max')
        adapter.fetch_raw.assert_called()
        fetch_kwargs = adapter.fetch_raw.call_args[1]
        assert "start" not in fetch_kwargs
        assert fetch_kwargs["period"] == "max"
        
        # Verify registry update
        mock_reg.update_last_observed_timestamp.assert_called()
        args = mock_reg.update_last_observed_timestamp.call_args[0]
        assert args[2] == pd.Timestamp("2024-01-02")
        print("SUCCESS: Bootstrap completed and timestamp updated to 2024-01-02.")

    # 2. Second Run (Incremental)
    print("\nStep 2: Second Run (Incremental)")
    with patch("adapters.factory.MetadataRegistry") as mock_reg_cls:
        mock_reg = mock_reg_cls.return_value
        # Found last_ts = 2024-01-02
        last_ts = pd.Timestamp("2024-01-02")
        mock_reg.get_last_observed_timestamp.return_value = last_ts
        
        # Mock fetch returning 2024-01-02 and 2024-01-03 (overlap)
        incremental_df = pd.DataFrame([
            {"Datetime": pd.Timestamp("2024-01-02"), "Close": 305, "Volume": 1100},
            {"Datetime": pd.Timestamp("2024-01-03"), "Close": 310, "Volume": 1200},
        ]).set_index("Datetime")
        
        adapter.fetch_raw = MagicMock(return_value=incremental_df)
        
        outputs = list(asset_fn(context))
        
        # Verify fetch was called WITH start
        adapter.fetch_raw.assert_called()
        fetch_kwargs = adapter.fetch_raw.call_args[1]
        assert fetch_kwargs["start"] == last_ts
        
        # Verify Precision Slicing (only 2024-01-03 should remain)
        silver_output = next(o for o in outputs if o.output_name == "silver_asset")
        result_df = silver_output.value
        assert len(result_df) == 1
        assert result_df["timestamp"].iloc[0] == pd.Timestamp("2024-01-03")
        
        # Verify registry update to Jan 3rd
        mock_reg.update_last_observed_timestamp.assert_called()
        args = mock_reg.update_last_observed_timestamp.call_args[0]
        assert args[2] == pd.Timestamp("2024-01-03")
        print("SUCCESS: Incremental fetch performed with precision slicing.")

    # 3. Config Change (Isolation)
    print("\nStep 3: Config Change (Isolation)")
    new_config = {"interval": "1h", "auto_adjust": True}
    new_assets = create_adapter_assets(adapter, new_config)
    
    old_silver_key = assets[0].keys[1].path
    new_silver_key = new_assets[0].keys[1].path
    
    print(f"Old Key: {old_silver_key}")
    print(f"New Key: {new_silver_key}")
    
    assert old_silver_key != new_silver_key
    assert "_1d_" in old_silver_key[-1]
    assert "_1h_" in new_silver_key[-1]
    print("SUCCESS: Config change resulted in a new isolated Asset Key.")

if __name__ == "__main__":
    verify()

