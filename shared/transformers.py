from datetime import datetime, timezone
from typing import Any, Dict, Optional
import math

def normalize_timestamp(value: Any, tz: timezone = timezone.utc) -> datetime:
    """Parse source-specific date and timestamp formats into a timezone-aware datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=tz)
        return value
    if isinstance(value, (int, float)):
        # Assume ms if very large, otherwise s
        if value > 1e11:
            dt = datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
        else:
            dt = datetime.fromtimestamp(value, tz=timezone.utc)
        return dt.astimezone(tz)
    if isinstance(value, str):
        try:
            # Simple ISO parse
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(tz)
        except ValueError:
            pass
    raise ValueError(f"Could not normalize timestamp: {value}")

def normalize_missing(value: Any, default: Any = None) -> Any:
    """Handle missing values according to domain-specific rules."""
    if value is None or value == "":
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    return value

def normalize_numeric(value: Any) -> float:
    """Convert source values into explicit analytical float types. Raises if missing or invalid."""
    val = normalize_missing(value, default=None)
    if val is None:
        raise ValueError("Value is missing and cannot be normalized to numeric.")
    try:
        f = float(val)
    except (ValueError, TypeError):
        raise ValueError(f"Could not cast {val} to float")
    
    if math.isnan(f) or math.isinf(f):
        raise ValueError(f"Value cannot be NaN or Inf, got {f}")
    return f

def normalize_units(value: float, from_unit: str, to_unit: str) -> float:
    """Apply unit conversions if explicitly defined."""
    if from_unit == to_unit:
        return value
    # Basic example for percentage scaling
    if from_unit.lower() == "decimal" and to_unit.lower() == "percent":
        return value * 100.0
    if from_unit.lower() == "percent" and to_unit.lower() == "decimal":
        return value / 100.0
    raise NotImplementedError(f"Conversion from {from_unit} to {to_unit} not implemented.")

def attach_lineage(schema_version: str, transformation_version: str, bronze_record_id: str, source_version: str) -> Dict[str, str]:
    """Helper to populate the SilverBase lineage and versioning fields."""
    return {
        "schema_version": schema_version,
        "transformation_version": transformation_version,
        "bronze_record_id": bronze_record_id,
        "source_version": source_version,
    }
