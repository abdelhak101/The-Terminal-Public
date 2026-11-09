from typing import Any, Dict
from shared.transformers import normalize_numeric, normalize_timestamp, attach_lineage
from domains.census.models import SilverCensusObservations

def normalize_census_data(raw: Dict[str, Any], lineage: Dict[str, str]) -> SilverCensusObservations:
    """
    Transforms a raw dictionary into a strictly validated SilverCensusObservations schema.
    Applies shared normalization primitives and constructs a multidimensional dimensions payload.
    """
    # 1. Normalize Numeric Value
    value = normalize_numeric(raw.get("value"))
    
    # 2. Normalize Temporal Data (Never invent timestamps for periods)
    observation_date = None
    date_val = raw.get("observation_date") or raw.get("date")
    if date_val:
        observation_date = normalize_timestamp(date_val)
        
    reference_period = raw.get("reference_period") or raw.get("year") or raw.get("period")
    if reference_period:
        reference_period = str(reference_period)
        
    if not observation_date and not reference_period:
        raise ValueError("Census observation must provide either an observation_date or a reference_period.")

    # 3. Build Lineage & Versioning
    base_lineage = attach_lineage(
        schema_version="v1",
        transformation_version="v1",
        bronze_record_id=lineage.get("bronze_reference", "unknown"),
        source_version=lineage.get("source_version", "unknown")
    )
    
    # 4. Sweep unstructured multidimensional attributes into the `dimensions` JSON dict
    known_first_class_fields = {
        "dataset_id", "value", "observation_date", "date", "reference_period", "year", "period",
        "category_code", "data_type_code", "batch_id", "bronze_reference", "source_version", "dimensions"
    }
    
    dimensions = raw.get("dimensions", {})
    if not isinstance(dimensions, dict):
        dimensions = {}
        
    for k, v in raw.items():
        if k not in known_first_class_fields and k not in base_lineage:
            dimensions[k] = v
            
    dataset_id = raw.get("dataset_id") or lineage.get("source_version", "unknown")
    
    return SilverCensusObservations(
        **base_lineage,
        dataset_id=dataset_id,
        observation_date=observation_date,
        reference_period=reference_period,
        value=value,
        category_code=raw.get("category_code") and str(raw.get("category_code")),
        data_type_code=raw.get("data_type_code") and str(raw.get("data_type_code")),
        dimensions=dimensions,
        batch_id=lineage.get("batch_id")
    )
