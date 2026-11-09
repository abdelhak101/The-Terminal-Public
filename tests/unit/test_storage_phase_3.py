from unittest.mock import MagicMock, patch
import sys
import pandas as pd

# Mock dependencies before any imports
sys.modules["psycopg2"] = MagicMock()
sys.modules["psycopg2.extras"] = MagicMock()
# Mocking dagster base classes
dagster_mock = MagicMock()
class ConfigurableIOManager:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
sys.modules["dagster"] = dagster_mock
dagster_mock.ConfigurableIOManager = ConfigurableIOManager

sys.modules["arcticdb"] = MagicMock()

import pytest
from shared.registry import MetadataRegistry
from shared.arctic import ArcticIOManager, GoldSnapshotManager

@pytest.fixture
def mock_db():
    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        yield mock_conn

@pytest.fixture
def registry(mock_db):
    return MetadataRegistry()

def test_registry_register_asset(registry, mock_db):
    mock_cur = mock_db.cursor.return_value.__enter__.return_value
    mock_cur.fetchone.return_value = (1,)
    asset_id = registry.register_asset("test_symbol", "silver", "test description")
    assert asset_id == 1

@pytest.fixture
def mock_arctic():
    with patch("shared.arctic.Arctic") as mock_class:
        mock_instance = mock_class.return_value
        yield mock_instance

def test_arctic_io_manager_handle_output(mock_arctic):
    mock_registry = MagicMock()
    mock_registry.register_asset.return_value = 1
    mock_registry.start_lineage.return_value = 10
    
    manager = ArcticIOManager(uri="lmdb://test")
    # Patch _get_registry directly on the instance
    manager._get_registry = MagicMock(return_value=mock_registry)
    
    mock_lib = MagicMock()
    mock_arctic.__getitem__.return_value = mock_lib
    mock_arctic.list_libraries.return_value = ["silver"]
    
    mock_res = MagicMock()
    mock_res.version = 42
    mock_lib.write.return_value = mock_res
    
    context = MagicMock()
    context.asset_key.path = ["silver", "test_asset"]
    context.run_id = "run_123"
    context.metadata = {}
    
    df = pd.DataFrame({"a": [1, 2]})
    manager.handle_output(context, df)
    
    mock_registry.register_asset.assert_called_once()
    mock_registry.start_lineage.assert_called_once()
    mock_registry.commit_lineage.assert_called_once_with(10, 42)

def test_gold_snapshot_manager(mock_arctic):
    manager = GoldSnapshotManager(uri="lmdb://test")
    mock_lib = MagicMock()
    mock_arctic.__getitem__.return_value = mock_lib
    mock_arctic.list_libraries.return_value = ["gold"]
    
    manager.create_snapshot("test_snapshot")
    mock_lib.snapshot.assert_called_once_with("test_snapshot")
