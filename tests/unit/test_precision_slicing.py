import sys
from unittest.mock import MagicMock

# Mock dependencies before imports
mock_dagster = MagicMock()
class MockOutput:
    def __init__(self, value, output_name=None, metadata=None):
        self.value = value
        self.output_name = output_name
        self.metadata = metadata
mock_dagster.Output = MockOutput
class MockAssetKey:
    def __init__(self, path):
        self.path = path
mock_dagster.AssetKey = MockAssetKey
mock_dagster.AssetOut = MagicMock
mock_dagster.multi_asset = lambda **kwargs: lambda fn: MagicMock(node_def=MagicMock(compute_fn=fn))

sys.modules["dagster"] = mock_dagster
sys.modules["yfinance"] = MagicMock()
sys.modules["opentelemetry"] = MagicMock()
sys.modules["opentelemetry.trace"] = MagicMock()
sys.modules["prometheus_client"] = MagicMock()
sys.modules["confluent_kafka"] = MagicMock()
sys.modules["arcticdb"] = MagicMock()

import pandas as pd
import pytest
from unittest.mock import MagicMock, patch
from adapters.factory import create_adapter_assets
from adapters.market.yahoo import YahooAdapter

def test_precision_slicing_logic():
    adapter = YahooAdapter("AAPL")
    config = {"interval": "1d"}
    
    # Mock data with 3 days
    df = pd.DataFrame([
        {"timestamp": pd.Timestamp("2024-01-01"), "value": 100},
        {"timestamp": pd.Timestamp("2024-01-02"), "value": 101},
        {"timestamp": pd.Timestamp("2024-01-03"), "value": 102},
    ])
    
    # Create the assets
    assets = create_adapter_assets(adapter, config)
    asset_fn = assets[0].node_def.compute_fn
    
    # Last observed is Jan 1st
    last_ts = pd.Timestamp("2024-01-01")
    
    with patch("adapters.factory.MetadataRegistry") as mock_reg_cls:
        mock_reg = mock_reg_cls.return_value
        mock_reg.get_last_observed_timestamp.return_value = last_ts
        
        # Mock fetch_raw and to_silver
        adapter.fetch_raw = MagicMock(return_value=df)
        adapter.to_silver = MagicMock(return_value=df.copy())
        
        context = MagicMock()
        outputs = list(asset_fn(context))
        
        # Find silver output
        silver_output = next(o for o in outputs if o.output_name == "silver_asset")
        result_df = silver_output.value
        
        # Result should only have Jan 2nd and 3rd
        assert len(result_df) == 2
        assert result_df["timestamp"].min() == pd.Timestamp("2024-01-02")
        
        # Registry should have been updated with Jan 3rd
        mock_reg.update_last_observed_timestamp.assert_called()
        args = mock_reg.update_last_observed_timestamp.call_args[0]
        assert args[2] == pd.Timestamp("2024-01-03")
