import sys
from unittest.mock import MagicMock

# Mock dependencies
sys.modules["yfinance"] = MagicMock()
sys.modules["dagster"] = MagicMock()
sys.modules["opentelemetry"] = MagicMock()
sys.modules["opentelemetry.trace"] = MagicMock()
sys.modules["prometheus_client"] = MagicMock()
sys.modules["confluent_kafka"] = MagicMock()

import pytest
from adapters.market.yahoo import YahooAdapter

def test_yahoo_config_hashing():
    adapter = YahooAdapter("AAPL")
    
    config1 = {"interval": "1d", "auto_adjust": True}
    config2 = {"interval": "1d", "auto_adjust": True, "irrelevant": "secret"}
    config3 = {"interval": "1h", "auto_adjust": True}
    
    hash1 = adapter.get_config_hash(config1)
    hash2 = adapter.get_config_hash(config2)
    hash3 = adapter.get_config_hash(config3)
    
    # Same parameters should yield same hash
    assert hash1 == hash2
    
    # Different parameters should yield different hash
    assert hash1 != hash3
    
    # Hash should be 5 characters
    assert len(hash1) == 5

def test_yahoo_schema_validation():
    schema = YahooAdapter.get_parameter_schema()
    assert "interval" in schema
    assert "auto_adjust" in schema
    assert schema["interval"]["default"] == "1d"

def test_fred_config_hashing_normalization():
    from adapters.macro.fred import FREDAdapter
    adapter = FREDAdapter("CPIAUCSL")
    
    config_descriptive = {"frequency": "Monthly", "units": "lin", "aggregation_method": "avg"}
    config_short = {"frequency": "m", "units": "lin", "aggregation_method": "avg"}
    config_quarterly = {"frequency": "Quarterly", "units": "lin", "aggregation_method": "avg"}
    
    hash_desc = adapter.get_config_hash(config_descriptive)
    hash_short = adapter.get_config_hash(config_short)
    hash_q = adapter.get_config_hash(config_quarterly)
    
    # "Monthly" and "m" must produce identical hash
    assert hash_desc == hash_short
    assert hash_desc != hash_q
