import os
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Tuple

from bytewax.dataflow import Dataflow
from bytewax.connectors.kafka import KafkaSource, KafkaSink
from bytewax.operators.windowing import EventClock, TumblingWindower, fold_window
import bytewax.operators as op
from .sinks import ClickHouseSink, RedisSink

# Configuration
BROKERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
IN_TOPIC = os.getenv("IN_TOPIC", "market.yahoo")
OUT_TOPIC = os.getenv("OUT_TOPIC", "market.bars.1m")
DLQ_TOPIC = os.getenv("DLQ_TOPIC", "market.dlq.silver")

def parse_tick(raw) -> Tuple[str, Dict[str, Any]]:
    """Parse JSON tick and return (symbol, data)"""
    # KafkaSource in 0.17 yields KafkaSourceMessage; extract the value.
    payload = raw.value if hasattr(raw, "value") else raw
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    data = json.loads(payload)
    return data["symbol"], data

def get_event_time(data: Dict[str, Any]) -> datetime:
    """Extract event time from tick data"""
    ts = data.get("timestamp") or data.get("dt")
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)

def acc_ohlcv(acc: Dict[str, Any], tick: Dict[str, Any]) -> Dict[str, Any]:
    """Reducer for OHLCV aggregation"""
    price = tick["price"]
    volume = tick.get("volume", 0)

    if not acc:
        return {
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": volume,
            "count": 1
        }

    acc["high"] = max(acc["high"], price)
    acc["low"] = min(acc["low"], price)
    acc["close"] = price
    acc["volume"] += volume
    acc["count"] += 1
    return acc

def merge_ohlcv(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """Merge two OHLCV accumulators (required by fold_window in 0.17+)."""
    if not left:
        return right
    if not right:
        return left
    return {
        "open": left["open"],
        "high": max(left["high"], right["high"]),
        "low": min(left["low"], right["low"]),
        "close": right["close"],
        "volume": left["volume"] + right["volume"],
        "count": left["count"] + right["count"],
    }

def format_bar(key_window_ohlcv):
    """Format the finalized window for the sinks"""
    symbol, (window_meta, ohlcv) = key_window_ohlcv
    start = window_meta.open_time if hasattr(window_meta, "open_time") else window_meta[0]
    bar = {
        "symbol": symbol,
        "timestamp": start.isoformat() if isinstance(start, datetime) else str(start),
        **ohlcv
    }
    return symbol, window_meta, bar

def format_kafka_msg(symbol_meta_bar):
    """Format the bar for Redpanda egress"""
    symbol, _, bar = symbol_meta_bar
    return symbol, json.dumps(bar)

def validate_bar(symbol_meta_bar):
    """Validate aggregated bar against domain schema and return (is_valid, (symbol, meta, data))"""
    symbol, meta, bar = symbol_meta_bar
    lineage = {
        "schema_version": "v1",
        "transformation_version": "v1",
        "source_version": "live_stream",
        "bronze_reference": "kafka_stream"
    }
    try:
        from domains.market.transformers import normalize_market_data
        model = normalize_market_data(bar, lineage)
        return (True, (symbol, meta, model.model_dump()))
    except Exception as e:
        bar["_error_reason"] = str(e)
        return (False, (symbol, meta, bar))

def compute_features(symbol_meta_bar):
    """Computes real-time features from the 1m bar."""
    symbol, meta, bar = symbol_meta_bar
    features = {
        "symbol": symbol,
        "timestamp": bar["timestamp"],
        "range_pct": (bar["high"] - bar["low"]) / bar["low"] if bar["low"] > 0 else 0,
        "hlc3": (bar["high"] + bar["low"] + bar["close"]) / 3
    }
    return symbol, meta, features

# ── Define Dataflow (Bytewax 0.17+ operator API) ──

flow = Dataflow("streaming-analytics")

# 1. Input: Consume from Redpanda
kafka_stream = op.input("redpanda-in", flow, KafkaSource(brokers=[BROKERS], topics=[IN_TOPIC]))

# 2. Parse ticks and key by symbol
keyed_stream = op.map("parse-tick", kafka_stream, parse_tick)

# 3. Windowed OHLCV aggregation
clock = EventClock(
    ts_getter=get_event_time,
    wait_for_system_duration=timedelta(seconds=5),
)
windower = TumblingWindower(length=timedelta(seconds=60))

windowed = fold_window(
    "aggregate",
    keyed_stream,
    clock,
    windower,
    builder=lambda: {},
    folder=acc_ohlcv,
    merger=merge_ohlcv,
)

# 4. Format bars
bars = op.map("format-bar", windowed.down, format_bar)

# 5. Validate bars against domain schema (DLQ pattern)
validated_split = op.map("validate-bar", bars, validate_bar)

good_bars_stream = op.filter("good-bars", validated_split, lambda x: x[0])
good_bars = op.map("extract-good", good_bars_stream, lambda x: x[1])

bad_bars_stream = op.filter("bad-bars", validated_split, lambda x: not x[0])
bad_bars = op.map("extract-bad", bad_bars_stream, lambda x: x[1])

# Output A: ClickHouse (Silver Storage)
op.output("clickhouse-out", good_bars, ClickHouseSink(library_name="silver"))

# Feature Computation & Online Storage
features = op.map("compute-features", good_bars, compute_features)
op.output("redis-out", features, RedisSink())

# Output B: Redpanda (Live Events)
kafka_msgs = op.map("format-kafka", good_bars, format_kafka_msg)
op.output("redpanda-out", kafka_msgs, KafkaSink(brokers=[BROKERS], topic=OUT_TOPIC))

# Output C: Redpanda DLQ (Invalid Events)
dlq_msgs = op.map("format-dlq", bad_bars, format_kafka_msg)
op.output("redpanda-dlq", dlq_msgs, KafkaSink(brokers=[BROKERS], topic=DLQ_TOPIC))
