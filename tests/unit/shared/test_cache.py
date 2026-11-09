import pytest
import json
from pathlib import Path
from shared.cache import AdapterCacheManager

def test_cache_save_and_retrieve(tmp_path):
    manager = AdapterCacheManager(cache_dir=str(tmp_path))
    source = "FRED"
    identifier = "M2"
    payload = json.dumps({"observations": [{"date": "2026-01-01", "value": "100.5"}]})
    metadata = {"status_code": 200, "url": "https://api.stlouisfed.org/fred/series/observations"}

    saved_path = manager.save_payload(source, identifier, payload, metadata)
    assert saved_path.exists()
    assert manager.has_cached_payload(source, identifier)

    retrieved_payload, retrieved_meta = manager.get_payload(source, identifier)
    assert retrieved_payload == payload
    assert retrieved_meta["status_code"] == 200
    assert "cached_at" in retrieved_meta

def test_cache_miss_returns_none(tmp_path):
    manager = AdapterCacheManager(cache_dir=str(tmp_path))
    assert manager.get_payload("UNKNOWN", "SYMBOL") is None
    assert not manager.has_cached_payload("UNKNOWN", "SYMBOL")

def test_cache_corrupted_file_recovery(tmp_path):
    manager = AdapterCacheManager(cache_dir=str(tmp_path))
    target_file = tmp_path / "fred" / "corrupt.json"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    with open(target_file, "w") as f:
        f.write("{invalid_json: true")

    result = manager.get_payload("fred", "corrupt")
    assert result is None
