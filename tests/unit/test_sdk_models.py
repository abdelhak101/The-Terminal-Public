import pytest
from unittest.mock import MagicMock, patch
from terminal_sdk.models import AnnotatedDataContainer, AssetMetadata
import pandas as pd

def test_annotated_datacontainer_metadata_preservation():
    """Verify that metadata is preserved during pandas operations."""
    metadata = {
        "symbol": "AAPL",
        "library": "gold",
        "lineage_id": 123,
        "columns": {"price": {"unit": "USD"}}
    }
    
    df = AnnotatedDataContainer({"price": [150.0, 151.0]}, metadata=metadata)
    
    assert df.metadata.symbol == "AAPL"
    assert df.metadata.lineage_id == 123
    
    # Slice the dataframe
    sliced = df.iloc[:1]
    
    # Metadata should be preserved
    assert isinstance(sliced, AnnotatedDataContainer)
    assert sliced.metadata.symbol == "AAPL"

def test_lineage_report_generation():
    """Test the to_lineage_report method."""
    metadata = {
        "symbol": "TSLA",
        "library": "gold",
        "lineage_id": 456,
        "dagster_run_id": "run_999",
        "version_id": 2
    }
    
    df = AnnotatedDataContainer({"val": [1, 2]}, metadata=metadata)
    report = df.to_lineage_report()
    
    assert report["symbol"] == "TSLA"
    assert report["lineage_id"] == 456
    assert report["dagster_run_id"] == "run_999"
