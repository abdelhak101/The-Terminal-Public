import pytest
from unittest.mock import MagicMock, patch
from shared.arctic import ArcticIOManager
from dagster import OutputContext, AssetKey

def test_arctic_io_manager_otel_tracing():
    """Verify that ArcticIOManager creates OTel spans during handle_output."""
    with patch('shared.arctic.MetadataRegistry'), \
         patch('shared.arctic.Arctic'), \
         patch('shared.arctic.tracer') as mock_tracer:
        
        # Setup mock span
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
        
        manager = ArcticIOManager(uri="memory://")
        
        # Mock Dagster context
        context = MagicMock(spec=OutputContext)
        context.asset_key = AssetKey(["bronze", "AAPL"])
        context.run_id = "test_run_123"
        context.metadata = {"description": "test"}
        
        # Mock data object
        import pandas as pd
        df = pd.DataFrame({'price': [150.0]})
        
        # Execute
        manager.handle_output(context, df)
        
        # Verify span was started with correct attributes
        mock_tracer.start_as_current_span.assert_called_once()
        args, kwargs = mock_tracer.start_as_current_span.call_args
        assert args[0] == "arctic_write"
        assert kwargs['attributes']['asset.symbol'] == "AAPL"
        assert kwargs['attributes']['asset.library'] == "bronze"
        assert kwargs['attributes']['dagster.run_id'] == "test_run_123"
        
        # Verify attributes set on span
        mock_span.set_attribute.assert_any_call("lineage.id", pytest.any)
