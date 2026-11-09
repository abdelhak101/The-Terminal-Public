import pytest
import json
from unittest.mock import MagicMock, patch
import pandas as pd
import requests

from adapters.market.yahoo import YahooAdapter
from shared.models import BronzePayload
from shared.cache import AdapterCacheManager

@pytest.fixture
def mock_history_data():
    df = pd.DataFrame({
        "Open": [100.0, 101.0],
        "High": [105.0, 106.0],
        "Low": [95.0, 96.0],
        "Close": [102.0, 103.0],
        "Volume": [1000, 1100]
    }, index=pd.to_datetime(["2023-01-01", "2023-01-02"]))
    df.index.name = "Date"
    return df

@pytest.fixture
def yahoo_adapter(tmp_path):
    cache_mgr = AdapterCacheManager(cache_dir=str(tmp_path))
    with patch("adapters.market.yahoo.KafkaProducer"):
        adapter = YahooAdapter(ticker="AAPL", cache_manager=cache_mgr)
        adapter.producer = MagicMock()
        return adapter

def test_yahoo_adapter_fetch_raw_success(yahoo_adapter, mock_history_data):
    with patch("adapters.market.yahoo.yf.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_history_data
        mock_ticker_cls.return_value = mock_ticker

        payload = yahoo_adapter.fetch_raw()
        assert isinstance(payload, BronzePayload)
        assert payload.origin_metadata["is_fallback"] is False
        assert yahoo_adapter.cache_manager.has_cached_payload("Yahoo Finance", "AAPL")

def test_yahoo_adapter_fetch_raw_fallback_on_exception(yahoo_adapter, mock_history_data):
    # Seed cache
    raw_json = mock_history_data.reset_index().to_json(orient="records", date_format="iso")
    yahoo_adapter.cache_manager.save_payload(
        source="Yahoo Finance",
        identifier="AAPL",
        raw_payload=raw_json,
        metadata={"ticker": "AAPL"}
    )

    with patch("adapters.market.yahoo.yf.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = requests.exceptions.ConnectionError("curl (28) Connection timed out")
        mock_ticker_cls.return_value = mock_ticker

        payload = yahoo_adapter.fetch_raw()
        assert isinstance(payload, BronzePayload)
        assert payload.origin_metadata["is_fallback"] is True
        assert payload.origin_metadata["cache_source"] == "local_disk"
        assert "Connection timed out" in payload.execution_metadata["fallback_reason"]

def test_yahoo_adapter_fetch_raw_fallback_on_empty(yahoo_adapter, mock_history_data):
    # Seed cache
    raw_json = mock_history_data.reset_index().to_json(orient="records", date_format="iso")
    yahoo_adapter.cache_manager.save_payload(
        source="Yahoo Finance",
        identifier="AAPL",
        raw_payload=raw_json,
        metadata={"ticker": "AAPL"}
    )

    with patch("adapters.market.yahoo.yf.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        payload = yahoo_adapter.fetch_raw(period="max")
        assert isinstance(payload, BronzePayload)
        assert payload.origin_metadata["is_fallback"] is True
        assert payload.execution_metadata["fallback_reason"] == "EMPTY_OR_UNREACHABLE"

def test_yahoo_adapter_metadata(yahoo_adapter):
    meta = yahoo_adapter.get_metadata()
    assert meta.source == "Yahoo Finance"
    assert "columns" in meta.metadata

def test_yahoo_adapter_fetch_raw_sanitizes_extraneous_kwargs(yahoo_adapter, mock_history_data):
    with patch("adapters.market.yahoo.yf.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_history_data
        mock_ticker_cls.return_value = mock_ticker

        payload = yahoo_adapter.fetch_raw(
            interval="1d",
            period="max",
            auto_adjust=True,
            description="United States Dollar Index (DX-Y.NYB)",
            label="main",
            arbitrary_extra_arg="should_be_filtered"
        )
        assert isinstance(payload, BronzePayload)
        mock_ticker.history.assert_called_once()
        called_kwargs = mock_ticker.history.call_args[1]
        assert "description" not in called_kwargs
        assert "label" not in called_kwargs
        assert "arbitrary_extra_arg" not in called_kwargs
        assert called_kwargs["interval"] == "1d"
        assert called_kwargs["period"] == "max"
        assert called_kwargs["auto_adjust"] is True
