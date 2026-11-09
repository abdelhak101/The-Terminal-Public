from unittest.mock import MagicMock, patch, ANY
from infrastructure.docker.orchestration.definitions import load_dynamic_assets
from adapters.factory import create_adapter_assets
from dagster import AssetKey

@patch('infrastructure.docker.orchestration.definitions.MetadataRegistry')
@patch('infrastructure.docker.orchestration.definitions.ADAPTER_MAP')
@patch('infrastructure.docker.orchestration.definitions.create_adapter_assets')
def test_load_dynamic_assets_passes_label(mock_create, mock_adapter_map, mock_registry_cls):
    # Mock registry
    mock_registry = mock_registry_cls.return_value
    mock_registry.get_active_sources.return_value = [
        {"adapter_type": "yahoo", "identifier": "AAPL", "label": "daily", "config": {}},
        {"adapter_type": "yahoo", "identifier": "AAPL", "label": "intraday", "config": {"interval": "1m"}}
    ]
    
    # Mock adapter map
    mock_adapter_map.__contains__.return_value = True
    mock_adapter_map.__getitem__.return_value = MagicMock()
    
    load_dynamic_assets()
    
    # Verify create_adapter_assets was called with labels and adapter_type
    assert mock_create.call_count == 2
    mock_create.assert_any_call(ANY, {}, label="daily", adapter_type="yahoo")
    mock_create.assert_any_call(ANY, {"interval": "1m"}, label="intraday", adapter_type="yahoo")

def test_create_adapter_assets_canonical_groups():
    mock_adapter = MagicMock()
    mock_adapter.source_name = "Yahoo Finance"
    mock_adapter.identifier = "DX-Y.NYB"
    mock_adapter.get_parameter_schema.return_value = ["interval"]
    mock_adapter.get_config_hash.return_value = "hash1"
    
    # Test Yahoo with adapter_type="yahoo"
    assets_yahoo = create_adapter_assets(mock_adapter, config={"interval": "1d"}, label="main", adapter_type="yahoo")
    assert len(assets_yahoo) == 1
    bronze_k = assets_yahoo[0].keys_by_output_name["bronze_asset"]
    silver_k = assets_yahoo[0].keys_by_output_name["silver_asset"]
    assert assets_yahoo[0].group_names_by_key[bronze_k] == "yahoo"
    assert assets_yahoo[0].group_names_by_key[silver_k] == "yahoo"
    assert bronze_k.path[1] == "yahoo"
    assert silver_k.path[1] == "yahoo"
    
    # Test Census with adapter_type="census"
    mock_census = MagicMock()
    mock_census.source_name = "Census Bureau"
    mock_census.identifier = "HOUSING_PERMITS"
    mock_census.get_parameter_schema.return_value = []
    mock_census.get_config_hash.return_value = "hash2"
    assets_census = create_adapter_assets(mock_census, config={}, label="main", adapter_type="census")
    bronze_c = assets_census[0].keys_by_output_name["bronze_asset"]
    silver_c = assets_census[0].keys_by_output_name["silver_asset"]
    assert assets_census[0].group_names_by_key[bronze_c] == "census"
    assert assets_census[0].group_names_by_key[silver_c] == "census"
    assert bronze_c.path[1] == "census"
    assert silver_c.path[1] == "census"

def test_create_adapter_assets_fallback_group():
    mock_adapter = MagicMock()
    mock_adapter.source_name = "Yahoo Finance"
    mock_adapter.identifier = "AAPL"
    mock_adapter.get_parameter_schema.return_value = ["interval"]
    mock_adapter.get_config_hash.return_value = "hash1"
    
    # Fallback to source_name when adapter_type is None
    assets = create_adapter_assets(mock_adapter, config={"interval": "1d"}, label="main", adapter_type=None)
    bronze_k = assets[0].keys_by_output_name["bronze_asset"]
    silver_k = assets[0].keys_by_output_name["silver_asset"]
    assert assets[0].group_names_by_key[bronze_k] == "yahoo_finance"
    assert assets[0].group_names_by_key[silver_k] == "yahoo_finance"

def test_create_adapter_assets_unique_keys():
    mock_adapter = MagicMock()
    mock_adapter.source_name = "Yahoo Finance"
    mock_adapter.identifier = "AAPL"
    mock_adapter.get_parameter_schema.return_value = ["interval"]
    mock_adapter.get_config_hash.return_value = "hash1"
    
    # Create assets for same adapter but different labels
    assets_daily = create_adapter_assets(mock_adapter, config={"interval": "1d"}, label="daily")
    assets_intraday = create_adapter_assets(mock_adapter, config={"interval": "1d"}, label="intraday")
    
    key_daily = assets_daily[0].keys_by_output_name["silver_asset"]
    key_intraday = assets_intraday[0].keys_by_output_name["silver_asset"]
    
    assert key_daily != key_intraday
    assert "daily" in key_daily.path[-1]
    assert "intraday" in key_intraday.path[-1]

def test_definitions_executor_configured():
    from infrastructure.docker.orchestration.definitions import defs
    assert defs.executor is not None

def test_is_step_worker_detection():
    import sys
    import os
    from infrastructure.docker.orchestration.definitions import is_step_worker

    # Test when execute_step is in sys.argv
    with patch.object(sys, "argv", ["dagster", "api", "execute_step", "run_id_123"]):
        assert is_step_worker() is True

    # Test when DAGSTER_STEP_WORKER is set in env
    with patch.object(sys, "argv", ["dagster-webserver"]):
        with patch.dict(os.environ, {"DAGSTER_STEP_WORKER": "1"}):
            assert is_step_worker() is True

    # Test normal coordinator/webserver process
    with patch.object(sys, "argv", ["dagster-webserver", "-h", "0.0.0.0"]):
        with patch.dict(os.environ, {}, clear=True):
            assert is_step_worker() is False

def test_sync_sources_declarative_advisory_lock():
    from shared.registry import MetadataRegistry

    registry = MetadataRegistry()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    # 1. Test when lock is already held by another process
    mock_cur.fetchone.return_value = [False]
    with patch.object(registry, "_get_connection", return_value=mock_conn):
        result = registry.sync_sources_declarative([{"adapter_type": "fred", "identifier": "GDP"}])
        assert result["status"] == "skipped"
        assert result["synced"] == 0

    # 2. Test when lock is acquired successfully
    mock_cur.fetchone.return_value = [True]
    with patch.object(registry, "_get_connection", return_value=mock_conn):
        result = registry.sync_sources_declarative([
            {"adapter_type": "fred", "identifier": "GDP", "label": "main", "config": {}}
        ])
        assert result["status"] == "success"
        assert result["synced"] == 1
        assert mock_conn.commit.called

def test_create_adapter_assets_retry_policy():
    mock_adapter = MagicMock()
    mock_adapter.source_name = "FRED"
    mock_adapter.identifier = "GDP"
    mock_adapter.get_parameter_schema.return_value = []
    mock_adapter.get_config_hash.return_value = "hash1"

    assets = create_adapter_assets(mock_adapter, config={}, label="main", adapter_type="fred")
    assert len(assets) == 1
    assert assets[0].op.retry_policy is not None
    assert assets[0].op.retry_policy.max_retries == 2
    assert assets[0].op.retry_policy.delay == 5


