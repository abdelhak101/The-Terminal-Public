import json
import logging
import pytest
import pandas as pd
from unittest.mock import MagicMock

# Import the adapters
from adapters.market.yahoo import YahooAdapter
from adapters.macro.fred import FREDAdapter
from adapters.macro.census import CensusAdapter
from shared.models import BronzePayload

def test_yahoo_to_silver_success_and_observability(caplog):
    adapter = YahooAdapter("AAPL")
    
    # 1. Test data: 1 valid record, 1 invalid record (missing close)
    raw_payload_data = [
        {
            "Date": "2026-08-15T00:00:00Z",
            "Open": 150.0,
            "High": 155.0,
            "Low": 149.0,
            "Close": 152.0,
            "Volume": 1000000,
            "Dividends": 0.0,
            "Stock Splits": 0.0
        },
        {
            "Date": "2026-08-16T00:00:00Z",
            "Open": 151.0,
            "High": 156.0,
            "Low": 150.0,
            # Missing Close field -> should fail validation
            "Volume": 2000000,
            "Dividends": 0.0,
            "Stock Splits": 0.0
        }
    ]
    
    payload = BronzePayload(
        protocol="yfinance",
        origin_metadata={"ticker": "AAPL"},
        execution_metadata={},
        payload_format="json",
        raw_payload=json.dumps(raw_payload_data),
        payload_checksum="test_checksum"
    )
    
    caplog.set_level(logging.INFO)
    
    # Call to_silver
    silver_df = adapter.to_silver(payload, batch_id="test_batch_123")
    
    # Assertions
    # 1. Market record transforms successfully and returns only the 1 valid record
    assert len(silver_df) == 1
    
    # 2. bronze_record_id is populated exactly once
    assert silver_df.iloc[0]["bronze_record_id"] == "test_checksum"
    
    # 3. Validation failure warning is observable in logs
    warning_logs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_logs) == 1
    assert "Validation failed for record" in warning_logs[0]
    assert "test_batch_123" in warning_logs[0]
    assert "test_checksum" in warning_logs[0]
    assert "ValueError" in warning_logs[0] or "ValidationError" in warning_logs[0]

    # 4. Summary log is present
    info_logs = [r.message for r in caplog.records if r.levelno == logging.INFO]
    assert len(info_logs) == 1
    assert "Transformation summary for Yahoo Finance" in info_logs[0]
    assert "Read: 2" in info_logs[0]
    assert "Transformed: 1" in info_logs[0]
    assert "Rejected: 1" in info_logs[0]


def test_fred_to_silver_success_and_observability(caplog):
    adapter = FREDAdapter("MEHOINUSA672N")
    
    raw_payload_data = {
        "observations": [
            {
                "date": "2026-08-01",
                "value": "100.5",
                "realtime_start": "2026-08-15",
                "realtime_end": "2026-08-15"
            },
            {
                "date": "2026-08-02",
                "value": ".",  # Invalid numeric value -> should fail validation
                "realtime_start": "2026-08-15",
                "realtime_end": "2026-08-15"
            }
        ]
    }
    
    payload = BronzePayload(
        protocol="http",
        origin_metadata={"url": "http://example.com"},
        execution_metadata={},
        payload_format="json",
        raw_payload=json.dumps(raw_payload_data),
        payload_checksum="fred_checksum"
    )
    
    caplog.set_level(logging.INFO)
    
    silver_df = adapter.to_silver(payload, batch_id="fred_batch")
    
    # 1. Macro record transforms successfully
    assert len(silver_df) == 1
    
    # 2. bronze_record_id is populated exactly once
    assert silver_df.iloc[0]["bronze_record_id"] == "fred_checksum"
    
    # 3. Validation failure warning is observable
    warning_logs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_logs) == 1
    assert "Validation failed for record" in warning_logs[0]
    assert "fred_batch" in warning_logs[0]
    assert "fred_checksum" in warning_logs[0]

    # 4. Summary log is present
    info_logs = [r.message for r in caplog.records if r.levelno == logging.INFO]
    assert len(info_logs) == 1
    assert "Transformation summary for FRED" in info_logs[0]
    assert "Read: 2" in info_logs[0]
    assert "Transformed: 1" in info_logs[0]
    assert "Rejected: 1" in info_logs[0]


def test_census_to_silver_success_and_observability(caplog):
    adapter = CensusAdapter("EITS")
    
    raw_payload_data = [
        ["cell_value", "time", "category_code", "data_type_code", "seasonally_adj"],
        ["12345.6", "2026-08", "44000", "TOTAL", "yes"],
        [".", "2026-09", "44000", "TOTAL", "yes"]  # Invalid value
    ]
    
    payload = BronzePayload(
        protocol="http",
        origin_metadata={"url": "http://example.com/census"},
        execution_metadata={},
        payload_format="json",
        raw_payload=json.dumps(raw_payload_data),
        payload_checksum="census_checksum"
    )
    
    caplog.set_level(logging.INFO)
    
    silver_df = adapter.to_silver(payload, batch_id="census_batch")
    
    # 1. Census record transforms successfully
    assert len(silver_df) == 1
    
    # 2. bronze_record_id populated exactly once
    assert silver_df.iloc[0]["bronze_record_id"] == "census_checksum"
    
    # 3. Warning observable
    warning_logs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_logs) == 1
    assert "Validation failed for record" in warning_logs[0]
    
    # 4. Summary printed
    info_logs = [r.message for r in caplog.records if r.levelno == logging.INFO]
    assert len(info_logs) == 1
    assert "Transformation summary for Census Bureau" in info_logs[0]
    assert "Read: 2" in info_logs[0]
    assert "Transformed: 1" in info_logs[0]
    assert "Rejected: 1" in info_logs[0]
