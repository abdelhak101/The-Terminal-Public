import pytest
from unittest.mock import MagicMock, patch
from infrastructure.docker.orchestration.jobs import register_source_op, RegistrationConfig
from dagster import build_op_context

@patch('infrastructure.docker.orchestration.jobs.MetadataRegistry')
@patch('infrastructure.docker.orchestration.jobs.ADAPTER_MAP')
def test_register_source_op_with_label(mock_adapter_map, mock_registry_cls):
    # Mock adapter
    mock_adapter = MagicMock()
    mock_adapter.get_parameter_schema.return_value = ["interval", "period", "auto_adjust"]
    mock_adapter_map.__contains__.return_value = True
    mock_adapter_map.__getitem__.return_value = mock_adapter
    
    # Mock registry
    mock_registry = mock_registry_cls.return_value
    
    # Config with label
    config = RegistrationConfig(
        adapter_type="yahoo",
        identifier="AAPL",
        label="daily_main",
        config={
            "interval": "1d",
            "period": "max",
            "auto_adjust": True
        }
    )
    
    # Run op
    context = build_op_context()
    register_source_op(config)
    
    # Verify registry call
    mock_registry.add_source.assert_called_once_with(
        adapter_type="yahoo",
        identifier="AAPL",
        label="daily_main",
        config={
            "interval": "1d",
            "period": "max",
            "auto_adjust": True
        }
    )

@patch('infrastructure.docker.orchestration.jobs.MetadataRegistry')
@patch('infrastructure.docker.orchestration.jobs.ADAPTER_MAP')
def test_register_source_op_default_label(mock_adapter_map, mock_registry_cls):
    # Mock adapter
    mock_adapter = MagicMock()
    mock_adapter.get_parameter_schema.return_value = []
    mock_adapter_map.__contains__.return_value = True
    mock_adapter_map.__getitem__.return_value = mock_adapter
    
    # Mock registry
    mock_registry = mock_registry_cls.return_value
    
    # Config without label (should default to "main")
    config = RegistrationConfig(
        adapter_type="yahoo",
        identifier="AAPL"
    )
    
    # Run op
    register_source_op(config)
    
    # Verify registry call
    mock_registry.add_source.assert_called_once_with(
        adapter_type="yahoo",
        identifier="AAPL",
        label="main",
        config={}
    )
