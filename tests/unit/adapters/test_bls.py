import pytest
from unittest.mock import MagicMock
import pandas as pd
from adapters.macro.bls import BLSAdapter

@pytest.fixture
def bls_adapter():
    return BLSAdapter(series_id="TEST_BLS_SERIES")

@pytest.fixture
def mock_bls_raw_data():
    return {
        "status": "REQUEST_SUCCEEDED",
        "Results": {
            "series": [
                {
                    "seriesID": "TEST_BLS_SERIES",
                    "data": [
                        {"year": "2023", "period": "M01", "periodName": "January", "value": "120.5", "footnotes": [{}]},
                        {"year": "2023", "period": "M02", "periodName": "February", "value": "121.0", "footnotes": [{}]},
                        {"year": "2023", "period": "Q01", "periodName": "1st Quarter", "value": "120.8", "footnotes": [{}]},
                        {"year": "2023", "period": "M13", "periodName": "Annual Average", "value": "121.2", "footnotes": [{}]},
                        {"year": "2023", "period": "M03", "periodName": "March", "value": "-", "footnotes": [{}]}, # Invalid numeric
                    ]
                }
            ]
        }
    }

def test_bls_adapter_to_bronze(bls_adapter, mock_bls_raw_data):
    bronze = bls_adapter.to_bronze(mock_bls_raw_data)
    assert bronze["source"] == "BLS"
    assert bronze["series_id"] == "TEST_BLS_SERIES"
    assert bronze["payload"] == mock_bls_raw_data
    assert "ingested_at" in bronze

def test_bls_adapter_to_silver(bls_adapter, mock_bls_raw_data):
    bronze = bls_adapter.to_bronze(mock_bls_raw_data)
    silver = bls_adapter.to_silver(bronze)
    
    assert isinstance(silver, pd.DataFrame)
    # The invalid numeric '-' row should be dropped, so 4 rows left
    assert len(silver) == 4
    
    # Check index and column structure
    assert list(silver.columns) == ["timestamp", "entity_id", "value", "realtime_start", "realtime_end", "unit"]
    assert silver.index.name == "timestamp"
    
    # Values check
    assert silver.loc[pd.Timestamp("2023-02-01")]["value"] == 121.0
    # Q01 should resolve to 2023-01-01
    # Note: we have two rows mapping to 2023-01-01 (M01 and Q01)
    # Pandas .loc on duplicated index will return a Series/DataFrame, let's verify both values exist
    records = silver[silver["timestamp"] == pd.Timestamp("2023-01-01")]
    assert len(records) == 2
    assert set(records["value"]) == {120.5, 120.8}
    
    # M13 (Annual Average) resolves to 2023-12-31
    assert silver.loc[pd.Timestamp("2023-12-31")]["value"] == 121.2
    
    # Check unit
    assert silver.iloc[0]["unit"] == "INDEX"

def test_bls_unemployment_unit_percent():
    adapter = BLSAdapter(series_id="LNS14000000") # Unemployment Rate
    mock_data = {
        "status": "REQUEST_SUCCEEDED",
        "Results": {
            "series": [
                {
                    "seriesID": "LNS14000000",
                    "data": [
                        {"year": "2023", "period": "M01", "value": "3.4"}
                    ]
                }
            ]
        }
    }
    bronze = adapter.to_bronze(mock_data)
    silver = adapter.to_silver(bronze)
    assert silver.iloc[0]["unit"] == "PERCENT"

def test_bls_adapter_fetch_raw(bls_adapter, monkeypatch):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "status": "REQUEST_SUCCEEDED",
        "Results": {
            "series": [
                {
                    "seriesID": "TEST_BLS_SERIES",
                    "data": [{"year": "2023", "period": "M01", "value": "120.5"}]
                }
            ]
        }
    }
    
    mock_post = MagicMock(return_value=mock_response)
    monkeypatch.setattr("shared.http_client.HttpClient.post", mock_post)
    
    raw = bls_adapter.fetch_raw(startyear="2023", endyear="2023")
    assert raw["status"] == "REQUEST_SUCCEEDED"
    assert len(raw["Results"]["series"][0]["data"]) == 1
    mock_post.assert_called_once()
