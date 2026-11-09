import pytest
from unittest.mock import MagicMock, patch
from shared.registry import MetadataRegistry
import json

@pytest.fixture
def mock_registry():
    with patch('shared.registry.psycopg2.connect') as mock_connect:
        registry = MetadataRegistry()
        # Mock connection and cursor context managers
        mock_conn = mock_connect.return_value
        mock_conn.__enter__.return_value = mock_conn
        
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_cur.__enter__.return_value = mock_cur
        
        yield registry, mock_connect, mock_cur

def test_add_source(mock_registry):
    registry, mock_connect, mock_cur = mock_registry
    
    registry.add_source("yahoo", "AAPL", label="daily_main", config={"test": "config"})
    
    # Verify the SQL call
    mock_cur.execute.assert_called()
    args, kwargs = mock_cur.execute.call_args
    sql = args[0]
    params = args[1]
    
    assert "INSERT INTO source_inventory" in sql
    assert params == ("yahoo", "AAPL", "daily_main", '{"test": "config"}')

def test_add_source_with_description(mock_registry):
    registry, mock_connect, mock_cur = mock_registry
    
    registry.add_source(
        "fred",
        "GDP",
        label="main",
        config={"frequency": "q"},
        description="Gross Domestic Product",
    )
    
    mock_cur.execute.assert_called()
    args, _ = mock_cur.execute.call_args
    params = args[1]
    
    assert params[0] == "fred"
    assert params[1] == "GDP"
    assert params[2] == "main"
    assert json.loads(params[3]) == {"frequency": "q", "description": "Gross Domestic Product"}

def test_sanitize_label_length_limit():
    registry = MetadataRegistry.__new__(MetadataRegistry)
    long_label = "a" * 150
    sanitized = registry._sanitize_label(long_label)
    assert len(sanitized) == 100
    assert sanitized == "a" * 100

def test_sanitize_label_special_chars_and_defaults():
    registry = MetadataRegistry.__new__(MetadataRegistry)
    
    # None or empty
    assert registry._sanitize_label(None) == "main"
    assert registry._sanitize_label("") == "main"
    assert registry._sanitize_label("   ") == "main"
    
    # Only special characters
    assert registry._sanitize_label("---!@#$%^&*()---") == "main"
    
    # Multiple underscores & non-alphanumerics
    assert registry._sanitize_label("United States: Assets (WALCL)") == "united_states_assets_walcl"
    
    # Truncation with trailing underscore removed
    label_ending_in_underscore_at_100 = ("a" * 99) + "-b"
    sanitized = registry._sanitize_label(label_ending_in_underscore_at_100)
    assert len(sanitized) == 99
    assert sanitized == "a" * 99

def test_get_active_sources(mock_registry):
    registry, mock_connect, mock_cur = mock_registry
    
    mock_cur.fetchall.return_value = [
        {"adapter_type": "yahoo", "identifier": "MSFT", "label": "main", "config": {}},
        {"adapter_type": "fred", "identifier": "CPI", "label": "monthly", "config": {"freq": "M"}}
    ]
    
    sources = registry.get_active_sources()
    
    assert len(sources) == 2
    assert sources[0]["identifier"] == "MSFT"
    assert sources[1]["adapter_type"] == "fred"
    mock_cur.execute.assert_called_with("SELECT adapter_type, identifier, label, config FROM source_inventory WHERE is_active = TRUE")
