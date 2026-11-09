from typing import Any, Dict
from shared.transformers import normalize_numeric, normalize_timestamp, normalize_missing, attach_lineage
from domains.market.models import SilverMarketOHLCV

def normalize_market_data(raw: Dict[str, Any], lineage: Dict[str, str]) -> SilverMarketOHLCV:
    """
    Transforms a raw dictionary into a strictly validated SilverMarketOHLCV schema.
    Applies shared normalization primitives without losing meaningful source data.
    """
    # 1. Normalize Timestamp
    timestamp_val = raw.get("timestamp")
    if not timestamp_val:
        raise ValueError("Missing required field: timestamp")
    normalized_ts = normalize_timestamp(timestamp_val)
    
    # 2. Normalize Numeric OHLC
    # Required field
    close_val = normalize_numeric(raw.get("close"))
    
    # Optional fields
    open_val = raw.get("open")
    if open_val is not None:
        open_val = normalize_numeric(open_val)
        
    high_val = raw.get("high")
    if high_val is not None:
        high_val = normalize_numeric(high_val)
        
    low_val = raw.get("low")
    if low_val is not None:
        low_val = normalize_numeric(low_val)

    # 3. Normalize Volume (integer-compatible)
    volume_val = raw.get("volume")
    if volume_val is not None:
        vol_float = normalize_numeric(volume_val)
        volume_val = int(vol_float)
        
    # 4. Dividends & Splits
    dividends_val = raw.get("dividends")
    if dividends_val is not None:
        dividends_val = normalize_numeric(dividends_val)
        
    splits_val = raw.get("stock_splits")
    if splits_val is not None:
        splits_val = normalize_numeric(splits_val)

    # 5. Build Lineage & Versioning
    base_lineage = attach_lineage(
        schema_version="v1",
        transformation_version="v1",
        bronze_record_id=lineage.get("bronze_reference", "unknown"),
        source_version=lineage.get("source_version", "unknown")
    )
    
    return SilverMarketOHLCV(
        **base_lineage,
        symbol=raw.get("symbol", lineage.get("source_version", "unknown")),
        timestamp=normalized_ts,
        open=open_val,
        high=high_val,
        low=low_val,
        close=close_val,
        volume=volume_val,
        dividends=dividends_val,
        stock_splits=splits_val,
        currency=normalize_missing(raw.get("currency")),
        price_unit=normalize_missing(raw.get("price_unit")),
        batch_id=lineage.get("batch_id")
    )
