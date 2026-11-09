import pytest
from datetime import datetime, timezone
from services.streaming_analytics.src.streaming_flow import acc_ohlcv, get_event_time

def test_acc_ohlcv_logic():
    """Verify that OHLCV values are calculated correctly across multiple ticks."""
    acc = None
    ticks = [
        {"price": 100.0, "volume": 10},
        {"price": 105.0, "volume": 5},
        {"price": 95.0, "volume": 20},
        {"price": 102.0, "volume": 15},
    ]
    
    for tick in ticks:
        acc = acc_ohlcv(acc, tick)
        
    assert acc["open"] == 100.0
    assert acc["high"] == 105.0
    assert acc["low"] == 95.0
    assert acc["close"] == 102.0
    assert acc["volume"] == 50
    assert acc["count"] == 4

def test_get_event_time_parsing():
    """Verify that event times are parsed correctly from different formats."""
    # Test float timestamp
    ts_float = 1700000000.0
    dt_float = get_event_time({"timestamp": ts_float})
    assert dt_float == datetime.fromtimestamp(ts_float, tz=timezone.utc)
    
    # Test ISO string
    ts_iso = "2023-11-14T22:13:20+00:00"
    dt_iso = get_event_time({"dt": ts_iso})
    assert dt_iso == datetime.fromisoformat(ts_iso)
