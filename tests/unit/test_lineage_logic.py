import pytest
from unittest.mock import MagicMock, patch
from shared.registry import MetadataRegistry

def test_get_lineage_pairs():
    registry = MetadataRegistry()
    
    # Mock get_all_assets to return mixed assets
    mock_assets = [
        {"symbol": "AAPL", "library": "bronze", "label": "daily", "id": 1},
        {"symbol": "AAPL", "library": "silver", "label": "daily", "id": 2},
        {"symbol": "MSFT", "library": "bronze", "label": "main", "id": 3},
        {"symbol": "FRED.CPI", "library": "silver", "label": "monthly", "id": 4},
        {"symbol": "OTHER", "library": "gold", "label": "main", "id": 5}
    ]
    
    with patch.object(MetadataRegistry, 'get_all_assets', return_value=mock_assets):
        pairs = registry.get_lineage_pairs()
        
        # We expect 4 unique (symbol, label) tuples:
        # (AAPL, daily), (MSFT, main), (FRED.CPI, monthly), (OTHER, main)
        assert len(pairs) == 4
        
        # Check AAPL daily (both bronze and silver)
        aapl = next(p for p in pairs if p['symbol'] == "AAPL" and p['label'] == "daily")
        assert aapl['bronze'] is not None
        assert aapl['silver'] is not None
        
        # Check MSFT (only bronze)
        msft = next(p for p in pairs if p['symbol'] == "MSFT")
        assert msft['bronze'] is not None
        assert msft['silver'] is None
        
        # Check CPI (only silver)
        cpi = next(p for p in pairs if p['symbol'] == "FRED.CPI")
        assert cpi['bronze'] is None
        assert cpi['silver'] is not None

        # Check OTHER (ignored in grouping but entry exists)
        other = next(p for p in pairs if p['symbol'] == "OTHER")
        assert other['bronze'] is None
        assert other['silver'] is None
