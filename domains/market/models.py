from datetime import datetime
from typing import Optional
from pydantic import Field
from shared.models import SilverBase

class SilverMarketOHLCV(SilverBase):
    """Domain schema for market data (Open, High, Low, Close, Volume)."""
    symbol: str = Field(..., description="The financial instrument identifier.")
    timestamp: datetime = Field(..., description="The normalized observation time of the data point.")
    
    open: Optional[float] = Field(None, description="Opening price.")
    high: Optional[float] = Field(None, description="Highest price during the period.")
    low: Optional[float] = Field(None, description="Lowest price during the period.")
    close: float = Field(..., description="Closing price.")
    volume: Optional[int] = Field(None, description="Trading volume.")
    
    dividends: Optional[float] = Field(None, description="Dividends paid.")
    stock_splits: Optional[float] = Field(None, description="Stock splits ratio.")
    
    currency: Optional[str] = Field(None, description="The currency denomination.")
    price_unit: Optional[str] = Field(None, description="The price unit (e.g. USD).")
    
    batch_id: Optional[str] = Field(None, description="Batch execution identifier for lineage.")
    bronze_record_id: str = Field(..., description="Reference to the exact Bronze payload.")
