import os
import pandas as pd
from typing import Any, Dict, List, Optional
import json
from shared.adapters import SearchableAdapter, SearchResult
from shared.models import TerminalDataFrameMetadata, BronzePayload
from shared.http_client import HttpClient
from shared.cache import AdapterCacheManager
from shared.metrics import TERMINAL_ADAPTER_MESSAGES_TOTAL, TERMINAL_ADAPTER_FALLBACK_TOTAL

class FREDAdapter(SearchableAdapter[Dict[str, Any]]):
    """
    Adapter for Federal Reserve Economic Data (FRED).
    """

    def __init__(self, series_id: str = "CPILFESL", cache_manager: Optional[AdapterCacheManager] = None):
        self.series_id = series_id
        self.api_key = os.getenv("FRED_API_KEY", "abcdefghijklmnopqrstuvwxyz123456")
        self.client = HttpClient(base_url="https://api.stlouisfed.org/fred/")
        self.cache_manager = cache_manager or AdapterCacheManager()

    @property
    def source_name(self) -> str:
        return "FRED"

    @property
    def identifier(self) -> str:
        return self.series_id

    FREQUENCY_MAP = {
        "daily": "d",
        "d": "d",
        "weekly": "w",
        "w": "w",
        "biweekly": "bw",
        "bw": "bw",
        "monthly": "m",
        "m": "m",
        "quarterly": "q",
        "q": "q",
        "semiannual": "sa",
        "sa": "sa",
        "annual": "a",
        "a": "a",
        "weekly, ending friday": "wef",
        "wef": "wef",
        "weekly, ending thursday": "weth",
        "weth": "weth",
        "weekly, ending wednesday": "wew",
        "wew": "wew",
        "weekly, ending tuesday": "wetu",
        "wetu": "wetu",
        "weekly, ending monday": "wem",
        "wem": "wem",
        "weekly, ending sunday": "wsu",
        "wsu": "wsu",
        "weekly, ending saturday": "wsa",
        "wsa": "wsa",
        "weekly, as of wednesday": "wew",
        "biweekly, ending wednesday": "bwew",
        "bwew": "bwew",
        "biweekly, ending monday": "bwem",
        "bwem": "bwem",
        "annual, fiscal year": "a",
        "annually": "a",
        "monthly, end of period": "m",
    }

    @classmethod
    def get_parameter_schema(cls) -> Dict[str, Any]:
        return {
            "frequency": {"type": str, "default": None},
            "units": {"type": str, "default": "lin"},
            "aggregation_method": {"type": str, "default": "avg"},
        }

    def get_config_hash(self, config: Dict[str, Any]) -> str:
        """Normalize frequency in config before hashing to maintain deterministic hashes."""
        normalized = dict(config or {})
        if "frequency" in normalized and normalized["frequency"] is not None:
            raw_freq = str(normalized["frequency"]).lower().strip()
            normalized["frequency"] = self.FREQUENCY_MAP.get(raw_freq, raw_freq)
        return super().get_config_hash(normalized)

    def fetch_raw(self, **kwargs) -> BronzePayload:
        allowed_keys = set(self.get_parameter_schema().keys()) | {"observation_start", "observation_end", "start", "end"}
        clean_kwargs = {k: v for k, v in kwargs.items() if k in allowed_keys}

        params = {
            "series_id": self.series_id,
            "api_key": self.api_key,
            "file_type": "json",
            **clean_kwargs
        }
        
        # Merge defaults from schema if not provided (skip None defaults)
        schema_defaults = {k: v.get("default") for k, v in self.get_parameter_schema().items()}
        for k, v in schema_defaults.items():
            if k not in params and v is not None:
                params[k] = v

        # Normalize or remove frequency parameter
        if "frequency" in params:
            if params["frequency"] is not None and str(params["frequency"]).strip():
                raw_freq = str(params["frequency"]).lower().strip()
                params["frequency"] = self.FREQUENCY_MAP.get(raw_freq, raw_freq)
            else:
                params.pop("frequency", None)

        # Omit aggregation_method if frequency is not specified
        if "frequency" not in params:
            params.pop("aggregation_method", None)

        try:
            response = self.client.get("series/observations", params=params)
            raw_text = response.text
            
            # Increment ingestion counter
            try:
                data = response.json()
                observations = data.get("observations", [])
                TERMINAL_ADAPTER_MESSAGES_TOTAL.labels(source=self.source_name, entity_id=self.series_id).inc(len(observations))
            except Exception:
                pass
                
            # Save to local cache on success
            self.cache_manager.save_payload(
                source=self.source_name,
                identifier=self.identifier,
                raw_payload=raw_text,
                metadata={"url": str(response.url), "status_code": response.status_code}
            )

            return BronzePayload(
                protocol="http",
                origin_metadata={"url": str(response.url), "method": response.request.method, "is_fallback": False},
                execution_metadata={"status_code": response.status_code, "headers": dict(response.headers)},
                payload_format="json",
                raw_payload=raw_text
            )
        except Exception as e:
            # Fallback to local cache if available
            cached = self.cache_manager.get_payload(self.source_name, self.identifier)
            if cached is not None:
                raw_cached, cached_meta = cached
                TERMINAL_ADAPTER_FALLBACK_TOTAL.labels(source=self.source_name, entity_id=self.series_id).inc()
                return BronzePayload(
                    protocol="http",
                    origin_metadata={
                        "url": cached_meta.get("url", "https://api.stlouisfed.org/fred/series/observations"),
                        "is_fallback": True,
                        "cache_source": "local_disk"
                    },
                    execution_metadata={
                        "status_code": 200,
                        "fallback_reason": str(e),
                        "cached_at": cached_meta.get("cached_at")
                    },
                    payload_format="json",
                    raw_payload=raw_cached
                )
            raise

    def to_silver(self, payload: BronzePayload, batch_id: Optional[str] = None) -> pd.DataFrame:
        """
        Normalize FRED raw data into the canonical Silver layer format.
        Preserves full revision history (Point-in-Time).
        """
        import json
        import logging
        from domains.macro.transformers import normalize_macro_data
        from domains.macro.models import SilverMacroObservations
        
        logger = logging.getLogger("adapters.macro.fred")
        
        raw_data = json.loads(payload.raw_payload)
        observations = raw_data.get("observations", [])
        
        if not observations:
            return pd.DataFrame(columns=list(SilverMacroObservations.model_fields.keys()))
            
        bronze_ref = payload.payload_checksum or "unknown"
        lineage = {
            "source_version": payload.origin_metadata.get("url", "unknown"),
            "bronze_reference": bronze_ref,
            "batch_id": batch_id
        }
        
        records_read = len(observations)
        records_transformed = 0
        records_rejected = 0
        rejection_reasons = {}
        
        validated_records = []
        for row in observations:
            # Map specific FRED keys
            transformed_row = {
                "series_id": self.series_id,
                "observation_date": row.get("date"),
                "value": row.get("value"),
                "realtime_start": row.get("realtime_start"),
                "realtime_end": row.get("realtime_end"),
                "unit": "INDEX"
            }
            
            try:
                validated_model = normalize_macro_data(transformed_row, lineage)
                validated_records.append(validated_model.model_dump())
                records_transformed += 1
            except Exception as e:
                records_rejected += 1
                exc_type = type(e).__name__
                rejection_reasons[exc_type] = rejection_reasons.get(exc_type, 0) + 1
                logger.warning(
                    "Validation failed for record. Source: %s, Domain: %s, Batch ID: %s, Bronze Record ID: %s, Exception Type: %s, Message: %s",
                    self.source_name, "macro", batch_id or "N/A", bronze_ref, exc_type, str(e)
                )
                continue
                
        logger.info(
            "Transformation summary for %s (%s) - Read: %d, Transformed: %d, Rejected: %d, Rejection Reasons: %s, Written: %d",
            self.source_name, self.series_id, records_read, records_transformed, records_rejected, json.dumps(rejection_reasons), records_transformed
        )
        
        silver_df = pd.DataFrame(validated_records)
        
        if not silver_df.empty:
            silver_df = silver_df.set_index("observation_date", drop=False)
            silver_df.index.name = "timestamp"
            
        return silver_df

    def get_metadata(self) -> TerminalDataFrameMetadata:
        metadata = TerminalDataFrameMetadata(
            name=f"FRED - {self.series_id}",
            description="Macroeconomic data series with full Point-in-Time revision history.",
            frequency="monthly",
            source=self.source_name,
            is_seasonally_adjusted=True
        )
        # Register column schema for PIT transparency
        metadata.metadata["columns"] = [
            {"name": "value", "unit": "INDEX", "semantic_type": "value", "description": "Numeric observation"},
            {"name": "realtime_start", "unit": "DATE", "semantic_type": "vintage_start", "description": "Date version was published"},
            {"name": "realtime_end", "unit": "DATE", "semantic_type": "vintage_end", "description": "Date version was superseded"}
        ]
        return metadata

    @classmethod
    def get_search_parameter_schema(cls) -> Dict[str, Any]:
        return {
            "search_type": {"type": str, "default": "full_text"},
            "order_by": {"type": str, "default": "search_rank"},
            "sort_order": {"type": str, "default": "desc"},
        }

    def search(self, query: str, limit: int = 10, **kwargs) -> List[SearchResult]:
        params = {
            "search_text": query,
            "api_key": self.api_key,
            "file_type": "json",
            "limit": limit,
            **kwargs
        }
        # Merge defaults from search schema
        schema_defaults = {k: v.get("default") for k, v in self.get_search_parameter_schema().items()}
        for k, v in schema_defaults.items():
            if k not in params:
                params[k] = v

        response = self.client.get("series/search", params=params)
        data = response.json()
        seriess = data.get("seriess", [])

        results = []
        for series in seriess:
            results.append(SearchResult(
                identifier=series["id"],
                name=series["title"],
                description=series.get("notes"),
                source=self.source_name,
                metadata={
                    "frequency": series.get("frequency"),
                    "units": series.get("units"),
                    "last_updated": series.get("last_updated"),
                }
            ))
        return results
