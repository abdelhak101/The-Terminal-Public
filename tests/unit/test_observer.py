import pytest
from unittest.mock import MagicMock, patch
from services.observer.src.main import ObserverService

def test_observer_freshness_calculation():
    """Test that freshness metrics are calculated correctly."""
    with patch('services.observer.src.main.MetadataRegistry'), \
         patch('services.observer.src.main.ArcticStorage'), \
         patch('services.observer.src.main.FRESHNESS_GAUGE') as mock_gauge:
        
        service = ObserverService()
        
        # Mock asset with updated_at in the past
        import datetime
        from unittest.mock import PropertyMock
        
        mock_time = 1700000000.0
        asset = {
            'symbol': 'AAPL',
            'library': 'bronze',
            'updated_at': datetime.datetime.fromtimestamp(mock_time - 3600, tz=datetime.timezone.utc)
        }
        
        with patch('time.time', return_value=mock_time):
            service.evaluate_freshness(asset)
            
        # Should be 3600 seconds stale
        mock_gauge.labels.assert_called_with(symbol='AAPL', library='bronze')
        mock_gauge.labels().set.assert_called_with(3600.0)

def test_observer_get_assets():
    """Test asset fetching logic."""
    with patch('services.observer.src.main.MetadataRegistry') as mock_registry_cls:
        mock_registry = mock_registry_cls.return_value
        mock_conn = MagicMock()
        mock_registry._get_connection.return_value.__enter__.return_value = mock_conn
        mock_cur = mock_conn.cursor.return_value.__enter__.return_value
        
        mock_cur.fetchall.return_value = [{'id': 1, 'symbol': 'TSLA'}]
        
        service = ObserverService()
        assets = service.get_all_assets_with_rules()
        
        assert len(assets) == 1
        assert assets[0]['symbol'] == 'TSLA'
