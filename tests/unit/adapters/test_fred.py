import pytest
import json
from unittest.mock import MagicMock
import pandas as pd
import requests

from adapters.macro.fred import FREDAdapter
from shared.adapters import SearchResult
from shared.models import BronzePayload
from shared.cache import AdapterCacheManager

@pytest.fixture
def fred_adapter(tmp_path):
    cache_mgr = AdapterCacheManager(cache_dir=str(tmp_path))
    return FREDAdapter(series_id="TEST_SERIES", cache_manager=cache_mgr)

@pytest.fixture
def mock_raw_data():
    return {
        "observations": [
            {"date": "2023-01-01", "value": "100.5", "realtime_start": "2023-01-01", "realtime_end": "9999-12-31"},
            {"date": "2023-02-01", "value": "101.2", "realtime_start": "2023-01-01", "realtime_end": "9999-12-31"},
            {"date": "2023-03-01", "value": ".", "realtime_start": "2023-01-01", "realtime_end": "9999-12-31"},  # Missing data
        ]
    }

def test_fred_adapter_to_silver(fred_adapter, mock_raw_data):
    payload = BronzePayload(
        protocol="http",
        origin_metadata={"url": "https://api.stlouisfed.org/fred/series/observations"},
        execution_metadata={"status_code": 200},
        payload_format="json",
        raw_payload=json.dumps(mock_raw_data)
    )
    silver = fred_adapter.to_silver(payload)
    
    assert isinstance(silver, pd.DataFrame)
    assert len(silver) == 2  # One row rejected due to "."
    assert silver.iloc[0]["value"] == 100.5
    assert silver.iloc[0]["series_id"] == "TEST_SERIES"
    assert silver.iloc[0]["unit"] == "INDEX"
    assert silver.index.name == "timestamp"

def test_fred_adapter_fetch_raw_success(fred_adapter, mock_raw_data, monkeypatch):
    mock_response = MagicMock()
    mock_response.url = "https://api.stlouisfed.org/fred/series/observations?series_id=TEST_SERIES"
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.text = json.dumps(mock_raw_data)
    mock_response.json.return_value = mock_raw_data
    mock_response.request.method = "GET"

    monkeypatch.setattr(fred_adapter.client.session, "get", MagicMock(return_value=mock_response))

    bronze = fred_adapter.fetch_raw()
    assert isinstance(bronze, BronzePayload)
    assert bronze.execution_metadata["status_code"] == 200
    assert bronze.origin_metadata["is_fallback"] is False
    assert fred_adapter.cache_manager.has_cached_payload("FRED", "TEST_SERIES")

def test_fred_adapter_fetch_raw_fallback(fred_adapter, mock_raw_data, monkeypatch):
    # Pre-populate cache
    fred_adapter.cache_manager.save_payload(
        source="FRED",
        identifier="TEST_SERIES",
        raw_payload=json.dumps(mock_raw_data),
        metadata={"status_code": 200, "url": "https://api.stlouisfed.org/fred/series/observations"}
    )

    # Simulate network failure
    def mock_get_fail(*args, **kwargs):
        raise requests.exceptions.ConnectionError("Network is unreachable [Errno 101]")

    monkeypatch.setattr(fred_adapter.client.session, "get", mock_get_fail)

    bronze = fred_adapter.fetch_raw()
    assert isinstance(bronze, BronzePayload)
    assert bronze.origin_metadata["is_fallback"] is True
    assert bronze.origin_metadata["cache_source"] == "local_disk"
    assert "Network is unreachable" in bronze.execution_metadata["fallback_reason"]

def test_fred_adapter_search(fred_adapter, monkeypatch):
    mock_search_response = MagicMock()
    mock_search_response.status_code = 200
    mock_search_response.json.return_value = {
        "seriess": [
            {"id": "CPI", "title": "Consumer Price Index", "notes": "Inflation measure", 
             "frequency": "Monthly", "units": "Index", "last_updated": "2023-01-01"}
        ]
    }
    mock_get = MagicMock(return_value=mock_search_response)
    monkeypatch.setattr(fred_adapter.client, "get", mock_get)

    results = fred_adapter.search("inflation")
    assert len(results) == 1
    assert isinstance(results[0], SearchResult)
    assert results[0].identifier == "CPI"
    assert results[0].name == "Consumer Price Index"
    assert results[0].source == "FRED"
    assert results[0].metadata["frequency"] == "Monthly"
    
    call_args = mock_get.call_args
    assert "series/search" in call_args[0][0]
    assert call_args[1]["params"]["search_text"] == "inflation"

def test_fred_adapter_fetch_raw_sanitizes_extraneous_kwargs(fred_adapter, mock_raw_data, monkeypatch):
    mock_get = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = json.dumps(mock_raw_data)
    mock_response.url = "https://api.stlouisfed.org/fred/series/observations"
    mock_response.request.method = "GET"
    mock_response.headers = {}
    mock_get.return_value = mock_response
    monkeypatch.setattr(fred_adapter.client, "get", mock_get)

    fred_adapter.fetch_raw(
        frequency="Monthly",
        description="United States Real GDP",
        label="main",
        target_table="silver_macro_timeseries",
        arbitrary_kwarg="filtered"
    )

    mock_get.assert_called_once()
    called_params = mock_get.call_args[1]["params"]
    assert "description" not in called_params
    assert "label" not in called_params
    assert "target_table" not in called_params
    assert "arbitrary_kwarg" not in called_params
    assert called_params["frequency"] == "m"
    assert called_params["series_id"] == "TEST_SERIES"

@pytest.mark.parametrize("input_freq,expected_freq", [
    ("Monthly", "m"),
    ("Quarterly", "q"),
    ("Annual, Fiscal Year", "a"),
    ("Weekly, Ending Friday", "wef"),
    ("Weekly, As of Wednesday", "wew"),
    ("Daily", "d"),
    ("m", "m"),
    ("q", "q"),
])
def test_fred_adapter_fetch_raw_normalizes_frequencies(fred_adapter, mock_raw_data, monkeypatch, input_freq, expected_freq):
    mock_get = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = json.dumps(mock_raw_data)
    mock_response.url = "https://api.stlouisfed.org/fred/series/observations"
    mock_response.request.method = "GET"
    mock_response.headers = {}
    mock_get.return_value = mock_response
    monkeypatch.setattr(fred_adapter.client, "get", mock_get)

    fred_adapter.fetch_raw(frequency=input_freq)

    called_params = mock_get.call_args[1]["params"]
    assert called_params["frequency"] == expected_freq

def test_fred_adapter_fetch_raw_omits_empty_frequency(fred_adapter, mock_raw_data, monkeypatch):
    mock_get = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = json.dumps(mock_raw_data)
    mock_response.url = "https://api.stlouisfed.org/fred/series/observations"
    mock_response.request.method = "GET"
    mock_response.headers = {}
    mock_get.return_value = mock_response
    monkeypatch.setattr(fred_adapter.client, "get", mock_get)

    fred_adapter.fetch_raw(frequency=None)

    called_params = mock_get.call_args[1]["params"]
    assert "frequency" not in called_params
