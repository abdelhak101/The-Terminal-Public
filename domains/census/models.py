from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import Field
from shared.models import SilverBase

class SilverCensusObservations(SilverBase):
    """Domain schema for Census and multidimensional demographic observations."""
    dataset_id: str = Field(..., description="The unique identifier for the dataset (e.g. ACS 5-year).")
    
    observation_date: Optional[datetime] = Field(None, description="The precise temporal representation, if applicable.")
    reference_period: Optional[str] = Field(None, description="The period description (e.g. '2026', 'Q1-2026') if exact date is not provided.")
    
    value: float = Field(..., description="The numerical value of the observation.")
    
    category_code: Optional[str] = Field(None, description="The specific classification or category code (e.g. NAICS).")
    data_type_code: Optional[str] = Field(None, description="The data type indicator.")
    
    dimensions: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary multidimensional attributes (state, county, sex, age, etc.).")
    
    batch_id: Optional[str] = Field(None, description="Batch execution identifier for lineage.")
    bronze_record_id: str = Field(..., description="Reference to the exact Bronze payload.")
