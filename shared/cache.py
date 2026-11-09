import os
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class AdapterCacheManager:
    """
    File-based local disk cache manager for Adapter Bronze Payloads.
    Provides fallback storage and retrieval when external data providers are unreachable.
    """

    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir:
            self.base_dir = Path(cache_dir)
        else:
            env_dir = os.getenv("TERMINAL_CACHE_DIR")
            if env_dir:
                self.base_dir = Path(env_dir)
            else:
                self.base_dir = Path(".cache") / "adapters"

    def _sanitize_key(self, key: str) -> str:
        """Sanitizes identifier strings for safe filesystem paths."""
        return re.sub(r'[^a-zA-Z0-9_\-]', '_', key)

    def _get_file_path(self, source: str, identifier: str) -> Path:
        source_slug = self._sanitize_key(source.lower())
        id_slug = self._sanitize_key(identifier)
        return self.base_dir / source_slug / f"{id_slug}.json"

    def save_payload(
        self,
        source: str,
        identifier: str,
        raw_payload: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Saves raw payload and metadata to disk cache.
        """
        file_path = self._get_file_path(source, identifier)
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            cache_data = {
                "source": source,
                "identifier": identifier,
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {},
                "raw_payload": raw_payload
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            logger.debug(f"Cached raw payload for {source}:{identifier} at {file_path}")
            return file_path
        except Exception as e:
            logger.warning(f"Failed to cache payload for {source}:{identifier}: {str(e)}")
            return file_path

    def get_payload(self, source: str, identifier: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Retrieves raw payload and cached metadata from disk cache.
        Returns (raw_payload, metadata_dict) or None if cache miss or corrupt.
        """
        file_path = self._get_file_path(source, identifier)
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            raw_payload = data.get("raw_payload")
            if raw_payload is None:
                return None
                
            meta = {
                "cached_at": data.get("cached_at"),
                "cache_file": str(file_path),
                **data.get("metadata", {})
            }
            return raw_payload, meta
        except Exception as e:
            logger.warning(f"Error reading cache file {file_path}: {str(e)}")
            return None

    def has_cached_payload(self, source: str, identifier: str) -> bool:
        """Checks if a valid cache file exists."""
        return self._get_file_path(source, identifier).exists()
