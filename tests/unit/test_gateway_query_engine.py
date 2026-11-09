import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from services.gateway.src.query_engine import QueryEngine

@pytest.fixture
def mock_arctic():
    with patch("services.gateway.src.query_engine.Arctic") as mock:
        yield mock

@pytest.fixture
def mock_registry():
    with patch("services.gateway.src.query_engine.MetadataRegistry") as mock:
        yield mock

def test_resolve_asset_key():
    engine = QueryEngine(arctic_uri="lmdb://test")
    
    # Test Yahoo resolution
    params = {"interval": "1d"}
    key = engine._resolve_asset_key("yahoo", "AAPL", params)
    assert key.startswith("aapl_1d_")
    assert len(key.split("_")[-1]) == 5
    
    # Test FRED resolution
    params = {"units": "pc1"}
    key = engine._resolve_asset_key("fred", "CPI", params)
    assert key.startswith("cpi_default_") # default interval

def test_execute_query_success(mock_arctic, mock_registry):
    engine = QueryEngine(arctic_uri="lmdb://test")
    
    # Mock ArcticDB structure
    mock_lib = MagicMock()
    mock_arctic.return_value.__getitem__.return_value = mock_lib
    mock_arctic.return_value.list_libraries.return_value = ["silver"]
    
    # Mock data
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "value": [100.0, 101.0],
        "volume": [1000, 1100]
    })
    mock_lib.read.return_value.data = df
    mock_lib.has_symbol.return_value = True

    requests = [
        {"symbol": "AAPL", "adapter_type": "yahoo", "params": {"interval": "1d"}}
    ]
    
    result = engine.execute_query(requests)
    
    assert "AAPL" in result["data"]
    assert result["metadata"]["AAPL"]["status"] == "SUCCESS"
    assert len(result["data"]["AAPL"]) == 2
    assert result["data"]["AAPL"][0]["value"] == 100.0

def test_execute_query_partial_failure(mock_arctic, mock_registry):
    engine = QueryEngine(arctic_uri="lmdb://test")
    
    mock_lib = MagicMock()
    mock_arctic.return_value.__getitem__.return_value = mock_lib
    mock_arctic.return_value.list_libraries.return_value = ["silver"]
    
    # AAPL exists, MSFT does not
    def has_symbol_side_effect(symbol):
        return "aapl" in symbol
    
    mock_lib.has_symbol.side_effect = has_symbol_side_effect
    mock_lib.read.return_value.data = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01"]),
        "value": [150.0]
    })

    requests = [
        {"symbol": "AAPL", "adapter_type": "yahoo", "params": {"interval": "1d"}},
        {"symbol": "MSFT", "adapter_type": "yahoo", "params": {"interval": "1d"}}
    ]
    
    result = engine.execute_query(requests)
    
    assert result["metadata"]["AAPL"]["status"] == "SUCCESS"
    assert result["metadata"]["MSFT"]["status"] == "FAILED"
    assert "not found in ArcticDB" in result["metadata"]["MSFT"]["error"]
    assert len(result["data"]["AAPL"]) == 1
    assert len(result["data"]["MSFT"]) == 0

def test_execute_query_temporal_slicing(mock_arctic, mock_registry):
    engine = QueryEngine(arctic_uri="lmdb://test")
    
    mock_lib = MagicMock()
    mock_arctic.return_value.__getitem__.return_value = mock_lib
    mock_arctic.return_value.list_libraries.return_value = ["silver"]
    mock_lib.has_symbol.return_value = True
    
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
        "value": [10, 20, 30]
    })
    mock_lib.read.return_value.data = df

    requests = [
        {"symbol": "AAPL", "adapter_type": "yahoo", "params": {"interval": "1d"}}
    ]
    
    # Global slice
    result = engine.execute_query(requests, global_start="2024-01-02", global_end="2024-01-02")
    assert len(result["data"]["AAPL"]) == 1
    assert result["data"]["AAPL"][0]["value"] == 20

def test_execute_query_legacy_fallback(mock_arctic, mock_registry):
    engine = QueryEngine(arctic_uri="lmdb://test")
    
    mock_lib = MagicMock()
    mock_arctic.return_value.__getitem__.return_value = mock_lib
    mock_arctic.return_value.list_libraries.return_value = ["silver"]
    
    # Granular key NOT present, but 'fred' legacy symbol IS present
    def has_symbol_side_effect(symbol):
        return symbol == "fred"
    mock_lib.has_symbol.side_effect = has_symbol_side_effect
    
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-01"]),
        "entity_id": ["UNRATE", "CPILFESL"],
        "value": [5.0, 200.0]
    })
    mock_lib.read.return_value.data = df

    requests = [
        {"symbol": "UNRATE", "adapter_type": "fred", "params": {}}
    ]
    
    result = engine.execute_query(requests)
    
    assert result["metadata"]["UNRATE"]["status"] == "SUCCESS"
    assert result["metadata"]["UNRATE"]["storage_pattern"] == "legacy"
    assert result["metadata"]["UNRATE"]["internal_key"] == "fred"
    assert len(result["data"]["UNRATE"]) == 1
    assert result["data"]["UNRATE"][0]["value"] == 5.0

def test_execute_query_legacy_interval_mismatch(mock_arctic, mock_registry):
    engine = QueryEngine(arctic_uri="lmdb://test")
    
    mock_lib = MagicMock()
    mock_arctic.return_value.__getitem__.return_value = mock_lib
    mock_arctic.return_value.list_libraries.return_value = ["silver"]
    
    # granular NOT present, 'fred' legacy IS present
    mock_lib.has_symbol.side_effect = lambda s: s == "fred"
    
    # Legacy data has NO interval column
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01"]),
        "entity_id": ["UNRATE"],
        "value": [5.0]
    })
    mock_lib.read.return_value.data = df

    # Requesting a specific interval should fail on legacy fallback if col is missing
    requests = [
        {"symbol": "UNRATE", "adapter_type": "fred", "params": {"interval": "1h"}}
    ]
    
    result = engine.execute_query(requests)
    
    assert result["metadata"]["UNRATE"]["status"] == "FAILED"
    assert "does not support requested interval" in result["metadata"]["UNRATE"]["error"]
