from abc import ABC, abstractmethod
from typing import Any, Dict, List, Generic, TypeVar, Optional
from dataclasses import dataclass
import pandas as pd
from .models import TerminalDataFrameMetadata, BronzePayload

R = TypeVar("R")  # Search result type

@dataclass
class SearchResult:
    """Standardized search result structure."""
    identifier: str  # Unique identifier for the dataset (e.g., FRED series ID, Yahoo ticker)
    name: str  # Human-readable name
    source: str  # Source name (from adapter.source_name)
    description: Optional[str] = None  # Optional description
    metadata: Dict[str, Any] = None  # Source-specific metadata

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class BaseAdapter(ABC):
    """
    Abstract base class for all data adapters.
    Ensures a standardized interface for fetching, storing raw data,
    and normalizing into the canonical Silver layer.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Name of the data provider (e.g., 'FRED')."""
        pass

    @property
    @abstractmethod
    def identifier(self) -> str:
        """Unique identifier for this source (e.g., 'AAPL', 'CPI')."""
        pass

    @abstractmethod
    def fetch_raw(self, **kwargs) -> BronzePayload:
        """
        Connect to the external source and retrieve the raw data.
        Returns the data packaged in a BronzePayload for agnostic storage.
        """
        pass

    @abstractmethod
    def to_silver(self, payload: BronzePayload) -> pd.DataFrame:
        """
        Normalize the agnostic BronzePayload into the domain-specific Silver DataFrame.
        """
        pass

    @abstractmethod
    def get_metadata(self) -> TerminalDataFrameMetadata:
        """
        Return the AI-native metadata for this adapter's primary dataset.
        """
        pass

    @classmethod
    @abstractmethod
    def get_parameter_schema(cls) -> Dict[str, Any]:
        """
        Returns a dictionary defining valid parameters and their types/defaults.
        """
        pass

    def get_config_hash(self, config: Dict[str, Any]) -> str:
        """
        Generates a deterministic 5-char hash from the adapter configuration.
        """
        import hashlib
        import json
        
        schema = self.get_parameter_schema()
        # Only include keys that are in the schema to ensure stability
        filtered_config = {k: v for k, v in config.items() if k in schema}
        
        # Sort keys to ensure deterministic output
        config_json = json.dumps(filtered_config, sort_keys=True)
        return hashlib.md5(config_json.encode()).hexdigest()[:5]

class SearchableAdapter(BaseAdapter, ABC, Generic[R]):
    """
    Abstract base class for adapters that support searching for available datasets.
    """
    
    @abstractmethod
    def search(self, query: str, limit: int = 10, **kwargs) -> List[SearchResult]:
        """
        Search for available datasets from this adapter's source.
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
            **kwargs: Source-specific search parameters
            
        Returns:
            List of SearchResult objects
        """
        pass
    
    @classmethod
    @abstractmethod
    def get_search_parameter_schema(cls) -> Dict[str, Any]:
        """
        Return schema for search-specific parameters.
        """
        pass
