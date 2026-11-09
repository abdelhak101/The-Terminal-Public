from typing import List, Optional, Callable, Dict, Any, Union
from pydantic import BaseModel, Field, ConfigDict
from .models import FeatureMetadata

class FeatureInput(BaseModel):
    """Defines an input required by a feature."""
    name: str
    source_type: str = Field(..., description="Type of source: 'arcticdb', 'postgres', or 'feature'")
    source_key: str = Field(..., description="The identifier for the source (e.g., table name or feature name)")
    columns: List[str] = Field(default_factory=list, description="Specific columns needed from the source")

class Transformation(BaseModel):
    """Encapsulates the logic to compute a feature."""
    name: str
    logic: Callable[[Any], Any] = Field(..., description="The python function performing the transformation")
    params: Dict[str, Any] = Field(default_factory=dict, description="Hyperparameters for the transformation")

    model_config = ConfigDict(arbitrary_types_allowed=True)

class Feature(BaseModel):
    """The core DSL class for defining a feature."""
    metadata: FeatureMetadata
    inputs: List[FeatureInput]
    transformation: Transformation
    
    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def version(self) -> str:
        return self.metadata.version

    def __repr__(self) -> str:
        return f"<Feature {self.name} v{self.version}>"
