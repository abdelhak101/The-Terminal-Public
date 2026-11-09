import pytest
from unittest.mock import MagicMock
import pandas as pd
from adapters.macro.census import CensusAdapter

@pytest.fixture
def census_adapter():
    return CensusAdapter(indicator_or_dataset="HOUSING_STARTS")

@pytest.fixture
def mock_census_raw_data():
    return [
        ["cell_value", "time_slot", "category_code", "data_type_code", "seasonally_adj"],
        ["1350.5", "2023-01", "ASTART", "TOTAL", "yes"],
        ["1420.0", "2023-02", "ASTART", "TOTAL", "yes"],
        ["4200.2", "2023-Q1", "ASTART", "TOTAL", "yes"],
        ["15000.0", "2023", "ASTART", "TOTAL", "yes"],
        ["invalid_val", "2023-03", "ASTART", "TOTAL", "yes"], # Invalid numeric value
    ]

def test_census_adapter_to_bronze(census_adapter, mock_census_raw_data):
    bronze = census_adapter.to_bronze(mock_census_raw_data)
    assert bronze["source"] == "Census Bureau"
    assert bronze["identifier"] == "EITS_RESCONST_ASTART"
    assert bronze["payload"] == mock_census_raw_data
    assert "ingested_at" in bronze

def test_census_adapter_to_silver(census_adapter, mock_census_raw_data):
    bronze = census_adapter.to_bronze(mock_census_raw_data)
    silver = census_adapter.to_silver(bronze)
    
    assert isinstance(silver, pd.DataFrame)
    # The invalid numeric row should be dropped, so 4 rows left
    assert len(silver) == 4
    
    # Check index and column structure
    assert list(silver.columns) == ["timestamp", "entity_id", "value", "realtime_start", "realtime_end", "unit"]
    assert silver.index.name == "timestamp"
    
    # Values check
    assert silver.loc[pd.Timestamp("2023-02-01")]["value"] == 1420.0
    
    # Check all observations mapping to 2023-01-01 (monthly, quarterly, yearly)
    records_all = silver[silver["timestamp"] == pd.Timestamp("2023-01-01")]
    assert len(records_all) == 3
    assert set(records_all["value"]) == {1350.5, 4200.2, 15000.0}
    
    # Check unit
    assert silver.iloc[0]["unit"] == "THOUSANDS"

def test_census_adapter_fetch_raw(census_adapter, monkeypatch):
    mock_response = MagicMock()
    mock_response.json.return_value = [
        ["cell_value", "time_slot", "category_code", "data_type_code", "seasonally_adj"],
        ["1350.5", "2023-01", "ASTART", "TOTAL", "yes"]
    ]
    
    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr("shared.http_client.HttpClient.get", mock_get)
    
    raw = census_adapter.fetch_raw()
    assert len(raw) == 2
    assert raw[1][0] == "1350.5"
    mock_get.assert_called_once()
