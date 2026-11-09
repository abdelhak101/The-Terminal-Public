import httpx
from typing import List, Dict, Any, Optional, Union
from arcticdb import Arctic
from .models import AnnotatedDataContainer, FeatureRequest, FeatureResponse
import logging

logger = logging.getLogger("terminal-sdk")

class FeatureProxy:
    """Proxy class for feature-related operations."""
    def __init__(self, client: 'TerminalClient'):
        self.client = client

    def get(self, features: List[str], symbols: List[str], timestamp: str = "latest") -> Union[pd.DataFrame, Dict[str, Any]]:
        """
        Retrieve features for given symbols.
        
        Args:
            features: List of feature names.
            symbols: List of asset symbols.
            timestamp: "latest" for real-time, or ISO timestamp for historical.
            
        Returns:
            A dictionary or DataFrame containing the results.
        """
        with httpx.Client(base_url=self.client.gateway_url) as client:
            payload = {
                "features": features,
                "symbols": symbols,
                "timestamp": timestamp
            }
            resp = client.post("/v1/features/retrieve", json=payload, headers=self.client.headers)
            resp.raise_for_status()
            data = resp.json()
            
            if timestamp == "latest":
                # For latest, we often want a simple dict or a small DF
                return data["results"]
            else:
                # For historical, we'd ideally return an AnnotatedDataContainer
                # but for now we return the raw results
                return data["results"]

class TerminalClient:
    def __init__(self, gateway_url: str = "http://localhost:28000", api_key: Optional[str] = None):
        self.gateway_url = gateway_url
        self.api_key = api_key
        self.headers = {"X-API-Key": api_key} if api_key else {}
        self.features = FeatureProxy(self)

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search for assets in the registry."""
        with httpx.Client(base_url=self.gateway_url) as client:
            resp = client.get("/v1/assets/search", params={"q": query}, headers=self.headers)
            resp.raise_for_status()
            return resp.json()["results"]

    def load(self, symbol: str, lineage_id: Optional[int] = None) -> AnnotatedDataContainer:
        """
        Load an asset by symbol and optional lineage_id.
        Fetches manifest from Gateway and data directly from ArcticDB.
        """
        # 1. Get Manifest from Gateway
        with httpx.Client(base_url=self.gateway_url) as client:
            params = {}
            if lineage_id:
                params["lineage_id"] = lineage_id
            
            resp = client.get(f"/v1/assets/{symbol}/manifest", params=params, headers=self.headers)
            if resp.status_code == 404:
                raise ValueError(f"Asset '{symbol}' not found or has no committed data.")
            resp.raise_for_status()
            manifest = resp.json()

        # 2. Connect to ArcticDB and read data
        try:
            ac = Arctic(manifest["storage_uri"])
            lib = ac[manifest["library"]]
            # ArcticDB versioning uses version_id from the manifest
            data = lib.read(symbol, as_of=manifest["version_id"]).data
            
            # 3. Wrap in AnnotatedDataContainer
            return AnnotatedDataContainer(data, metadata=manifest)
        except Exception as e:
            logger.error(f"Failed to load data from storage: {e}")
            raise RuntimeError(f"Storage access failed: {e}")

# Global instance for easier notebook usage
_client: Optional[TerminalClient] = None

def connect(gateway_url: str = "http://localhost:28000", api_key: Optional[str] = None):
    global _client
    _client = TerminalClient(gateway_url, api_key)
    return _client

def load(symbol: str, lineage_id: Optional[int] = None) -> AnnotatedDataContainer:
    if not _client:
        raise RuntimeError("SDK not connected. Call terminal.connect() first.")
    return _client.load(symbol, lineage_id)

def search(query: str) -> List[Dict[str, Any]]:
    if not _client:
        raise RuntimeError("SDK not connected. Call terminal.connect() first.")
    return _client.search(query)
