import json
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd

from adapters.macro.moneycontrol import MoneycontrolAdapter
from adapters.factory import create_adapter_assets
from shared.models import BronzePayload


SAMPLE_URL = "https://api.moneycontrol.com/mcapi/v1/ecalendar/get-stats-data?calendarId=1414914&duration="

SAMPLE_RAW_RESPONSE = {
    "success": 1,
    "data": [
        {"date": "2026-01-31", "value": "52.60", "displayLock": "N"},
        {"date": "2026-02-28", "value": "52.40", "displayLock": "N"},
        {"date": "2026-03-31", "value": "52.70", "displayLock": "N"}
    ]
}


class TestMoneycontrolAdapter:

    def test_init_url_parsing(self):
        adapter = MoneycontrolAdapter(SAMPLE_URL)
        assert adapter.identifier == "1414914"
        assert adapter.source_name == "Moneycontrol"
        assert adapter.default_params["calendarId"] == "1414914"
        assert adapter.default_params["duration"] == ""

    def test_init_numeric_id(self):
        adapter = MoneycontrolAdapter("1414914")
        assert adapter.identifier == "1414914"
        assert adapter.default_params["calendarId"] == "1414914"

    def test_init_missing_calendar_id(self):
        with pytest.raises(ValueError, match="Could not extract 'calendarId'"):
            MoneycontrolAdapter("https://api.moneycontrol.com/mcapi/v1/ecalendar/get-stats-data?duration=1y")

    def test_init_empty_url(self):
        with pytest.raises(ValueError, match="Moneycontrol URL or calendarId must be provided"):
            MoneycontrolAdapter("")

    @patch("shared.http_client.HttpClient.get")
    def test_fetch_raw(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = json.dumps(SAMPLE_RAW_RESPONSE)
        mock_response.json.return_value = SAMPLE_RAW_RESPONSE
        mock_response.url = SAMPLE_URL
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.request.method = "GET"
        mock_get.return_value = mock_response

        adapter = MoneycontrolAdapter(SAMPLE_URL)
        payload = adapter.fetch_raw()

        assert isinstance(payload, BronzePayload)
        assert payload.payload_format == "json"
        assert payload.protocol == "http"
        assert payload.execution_metadata["status_code"] == 200
        assert json.loads(payload.raw_payload) == SAMPLE_RAW_RESPONSE

    def test_to_silver_valid(self):
        adapter = MoneycontrolAdapter(SAMPLE_URL)
        payload = BronzePayload(
            protocol="http",
            origin_metadata={"url": SAMPLE_URL, "method": "GET"},
            execution_metadata={"status_code": 200, "headers": {}},
            payload_format="json",
            raw_payload=json.dumps(SAMPLE_RAW_RESPONSE),
        )

        df = adapter.to_silver(payload, batch_id="test_batch_123")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert "series_id" in df.columns
        assert "observation_date" in df.columns
        assert "value" in df.columns
        assert df["series_id"].iloc[0] == "1414914"
        assert float(df["value"].iloc[0]) == 52.60
        assert df.index.name == "timestamp"

    def test_to_silver_empty(self):
        adapter = MoneycontrolAdapter(SAMPLE_URL)
        payload = BronzePayload(
            protocol="http",
            origin_metadata={"url": SAMPLE_URL, "method": "GET"},
            execution_metadata={"status_code": 200, "headers": {}},
            payload_format="json",
            raw_payload=json.dumps({"success": 1, "data": []}),
        )

        df = adapter.to_silver(payload)
        assert isinstance(df, pd.DataFrame)
        assert df.empty
        assert "series_id" in df.columns

    def test_to_silver_malformed_json(self):
        adapter = MoneycontrolAdapter(SAMPLE_URL)
        payload = BronzePayload(
            protocol="http",
            origin_metadata={"url": SAMPLE_URL, "method": "GET"},
            execution_metadata={"status_code": 200, "headers": {}},
            payload_format="json",
            raw_payload="NOT_JSON",
        )

        df = adapter.to_silver(payload)
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_get_metadata(self):
        adapter = MoneycontrolAdapter(SAMPLE_URL)
        metadata = adapter.get_metadata()
        assert metadata.source == "Moneycontrol"
        assert metadata.name == "Moneycontrol - 1414914"
        assert metadata.frequency == "monthly"

    def test_create_adapter_assets_factory(self):
        adapter = MoneycontrolAdapter(SAMPLE_URL)
        assets = create_adapter_assets(adapter)
        assert len(assets) == 1
        asset_def = assets[0]
        # Check target table metadata
        assert asset_def.keys_by_output_name["silver_asset"].path[0] == "silver"
        assert asset_def.keys_by_output_name["silver_asset"].path[1] == "moneycontrol"
