from datetime import datetime
from typing import Optional
from pydantic import Field
from shared.models import SilverBase

class SilverMacroObservations(SilverBase):
    """Domain schema for macroeconomic observations."""
    series_id: str = Field(..., description="The unique identifier for the statistical/economic series.")
    observation_date: datetime = Field(..., description="The temporal representation of the observation period.")
    
    value: float = Field(..., description="The numerical value of the observation.")
    unit: Optional[str] = Field(None, description="The unit of measurement.")
    frequency: Optional[str] = Field(None, description="The frequency of the series (e.g. Monthly).")
    seasonal_adjustment: Optional[str] = Field(None, description="Seasonal adjustment metadata.")
    
    realtime_start: Optional[datetime] = Field(None, description="The start of the vintage/revision period.")
    realtime_end: Optional[datetime] = Field(None, description="The end of the vintage/revision period.")
    
    batch_id: Optional[str] = Field(None, description="Batch execution identifier for lineage.")
    bronze_record_id: str = Field(..., description="Reference to the exact Bronze payload.")
