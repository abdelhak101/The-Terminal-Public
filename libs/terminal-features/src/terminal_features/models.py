from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel, Field

class FeatureMetadata(BaseModel):
    """Metadata for feature discovery and registry."""
    name: str
    description: str
    owner: str
    version: str = "1.0.0"
    tags: List[str] = Field(default_factory=list)

class FeatureLineage(BaseModel):
    """Tracks source data and transformation history."""
    feature_name: str
    version: str
    input_features: List[str] = Field(default_factory=list)
    input_datasets: List[str] = Field(default_factory=list)
    transformation_id: str
