from typing import Any, Dict
from shared.transformers import normalize_numeric, normalize_timestamp, normalize_missing, attach_lineage
from domains.macro.models import SilverMacroObservations

def normalize_macro_data(raw: Dict[str, Any], lineage: Dict[str, str]) -> SilverMacroObservations:
    """
    Transforms a raw dictionary into a strictly validated SilverMacroObservations schema.
    Applies shared normalization primitives while preserving macroeconomic semantics.
    """
    # 1. Normalize Observation Date (Not Intraday Timestamp)
    # Allows "observation_date", "date", or "timestamp" keys from raw
    date_val = raw.get("observation_date") or raw.get("date") or raw.get("timestamp")
    if not date_val:
        raise ValueError("Missing required field: observation_date")
    normalized_date = normalize_timestamp(date_val)
    
    # 2. Normalize Numeric Value
    value = normalize_numeric(raw.get("value"))
    
    # 3. Normalize Point-in-Time (Vintage) Metadata
    realtime_start = raw.get("realtime_start")
    if realtime_start is not None:
        realtime_start = normalize_timestamp(realtime_start)
        
    realtime_end = raw.get("realtime_end")
    if realtime_end is not None:
        realtime_end = normalize_timestamp(realtime_end)

    # 4. Build Lineage & Versioning
    base_lineage = attach_lineage(
        schema_version="v1",
        transformation_version="v1",
        bronze_record_id=lineage.get("bronze_reference", "unknown"),
        source_version=lineage.get("source_version", "unknown")
    )
    
    return SilverMacroObservations(
        **base_lineage,
        series_id=raw.get("series_id") or raw.get("symbol", lineage.get("source_version", "unknown")),
        observation_date=normalized_date,
        value=value,
        unit=normalize_missing(raw.get("unit")),
        frequency=normalize_missing(raw.get("frequency")),
        seasonal_adjustment=normalize_missing(raw.get("seasonal_adjustment")),
        realtime_start=realtime_start,
        realtime_end=realtime_end,
        batch_id=lineage.get("batch_id")
    )
