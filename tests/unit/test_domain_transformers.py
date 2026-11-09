import pytest
from datetime import datetime, timezone
from domains.market.transformers import normalize_market_data
from domains.macro.transformers import normalize_macro_data
from domains.census.transformers import normalize_census_data

# Common lineage
DUMMY_LINEAGE = {
    "source_version": "test_src",
    "bronze_reference": "abc123hash",
    "batch_id": "test_batch"
}

def test_market_happy_path():
    raw = {
        "symbol": "AAPL",
        "timestamp": "2026-08-11T12:00:00Z",
        "open": "150.5",
        "high": 151.0,
        "low": 149.0,
        "close": "150.0",
        "volume": "10000.5",
        "currency": "USD"
    }
    model = normalize_market_data(raw, DUMMY_LINEAGE)
    assert model.symbol == "AAPL"
    assert model.close == 150.0
    assert model.open == 150.5
    assert model.volume == 10000  # Cast to int correctly
    assert model.currency == "USD"
    assert model.bronze_record_id == "abc123hash"

def test_market_missing_required():
    raw = {
        "symbol": "AAPL",
        # Missing timestamp
        "close": 150.0
    }
    with pytest.raises(ValueError, match="Missing required field: timestamp"):
        normalize_market_data(raw, DUMMY_LINEAGE)

def test_macro_happy_path():
    raw = {
        "series_id": "US_CPI",
        "observation_date": "2026-08-01",
        "value": "298.5",
        "unit": "INDEX",
        "realtime_start": "2026-08-15"
    }
    model = normalize_macro_data(raw, DUMMY_LINEAGE)
    assert model.series_id == "US_CPI"
    assert model.value == 298.5
    assert model.unit == "INDEX"
    assert model.realtime_start.day == 15

def test_census_happy_path_with_dimensions():
    raw = {
        "dataset_id": "ACS5Y",
        "reference_period": "2026",
        "value": 150000,
        "category_code": "POPULATION",
        # Unstructured dimensions
        "state_id": "CA",
        "county_id": "001",
        "age_group": "25-34"
    }
    model = normalize_census_data(raw, DUMMY_LINEAGE)
    assert model.dataset_id == "ACS5Y"
    assert model.reference_period == "2026"
    assert model.value == 150000.0
    assert model.category_code == "POPULATION"
    assert "state_id" in model.dimensions
    assert model.dimensions["age_group"] == "25-34"

def test_census_missing_period():
    raw = {
        "dataset_id": "ACS5Y",
        "value": 150000
        # Missing date/period
    }
    with pytest.raises(ValueError, match="must provide either an observation_date or a reference_period"):
        normalize_census_data(raw, DUMMY_LINEAGE)
