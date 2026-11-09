import pandas as pd
from typing import Dict, Any, Optional

from pydantic import BaseModel, Field

class AssetMetadata:
    """Container for asset-level metadata."""
    def __init__(self, metadata: Dict[str, Any]):
        self.symbol = metadata.get('symbol')
        self.library = metadata.get('library')
        self.lineage_id = metadata.get('lineage_id')
        self.dagster_run_id = metadata.get('dagster_run_id')
        self.version_id = metadata.get('version_id')
        self.columns = metadata.get('columns', {})

    def __repr__(self):
        return f"<AssetMetadata symbol={self.symbol} lineage_id={self.lineage_id}>"

class FeatureRequest(BaseModel):
    """Request for feature retrieval."""
    features: List[str]
    symbols: List[str]
    timestamp: Optional[str] = "latest"  # "latest" or ISO timestamp

class FeatureResponse(BaseModel):
    """Response containing feature values."""
    results: List[Dict[str, Any]]
    source: str  # "redis" or "arcticdb"

class AnnotatedDataContainer(pd.DataFrame):
    """
    A Pandas DataFrame wrapper that carries asset metadata.
    """
    _metadata = ["metadata"]

    def __init__(self, *args, metadata: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(*args, **kwargs)
        if metadata:
            self.metadata = AssetMetadata(metadata)
        else:
            self.metadata = None

    @property
    def _constructor(self):
        return AnnotatedDataContainer

    def to_lineage_report(self) -> Dict[str, Any]:
        """Generate a lineage report for this dataset."""
        if not self.metadata:
            return {"error": "No metadata available"}
        return {
            "symbol": self.metadata.symbol,
            "lineage_id": self.metadata.lineage_id,
            "dagster_run_id": self.metadata.dagster_run_id,
            "version_id": self.metadata.version_id,
            "library": self.metadata.library
        }
