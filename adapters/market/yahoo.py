import pandas as pd
import yfinance as yf
from typing import Any, Dict, Optional, List
import json
from shared.adapters import SearchableAdapter, SearchResult
from shared.models import TerminalDataFrameMetadata, BronzePayload
from shared.kafka import KafkaProducer
from shared.cache import AdapterCacheManager
from shared.metrics import TERMINAL_ADAPTER_MESSAGES_TOTAL, TERMINAL_ADAPTER_FALLBACK_TOTAL

class YahooAdapter(SearchableAdapter[pd.DataFrame]):
    """
    Adapter for Yahoo Finance data.
    """

    def __init__(self, ticker: str = "SPY", cache_manager: Optional[AdapterCacheManager] = None):
        self.ticker = ticker
        # We initialize the producer lazily or here
        self.producer = KafkaProducer()
        self.cache_manager = cache_manager or AdapterCacheManager()
        
        # Avoid SQLite database lock errors in concurrent Dagster execution
        import os
        import tempfile
        yf.set_tz_cache_location(os.path.join(tempfile.gettempdir(), f"yfinance_cache_{os.getpid()}"))

    @property
    def source_name(self) -> str:
        return "Yahoo Finance"

    @property
    def identifier(self) -> str:
        return self.ticker

    @classmethod
    def get_parameter_schema(cls) -> Dict[str, Any]:
        return {
            "period": {"type": str, "default": "max"},
            "interval": {"type": str, "default": "1d"},
            "auto_adjust": {"type": bool, "default": True},
            "actions": {"type": bool, "default": True},
            "repair": {"type": bool, "default": False},
            "keepna": {"type": bool, "default": False},
            "prepost": {"type": bool, "default": False},
            "rounding": {"type": bool, "default": False},
            "timeout": {"type": int, "default": 10},
        }

    def fetch_raw(self, **kwargs) -> BronzePayload:
        """
        Fetch data using yfinance. Supports incremental fetching via 'start'.
        """
        # Filter kwargs strictly against schema keys and allowed runtime parameters
        allowed_keys = set(self.get_parameter_schema().keys()) | {"start", "end"}
        clean_kwargs = {k: v for k, v in kwargs.items() if k in allowed_keys}

        # Merge defaults from schema with sanitized kwargs
        params = {k: v.get("default") for k, v in self.get_parameter_schema().items()}
        params.update(clean_kwargs)
        
        # If 'start' is provided, we ignore 'period' as per yfinance API
        if params.get("start"):
            params.pop("period", None)

        try:
            ticker_obj = yf.Ticker(self.ticker)
            data = ticker_obj.history(**params)
            
            # If empty data returned due to network issue or invalid ticker
            if data is None or (isinstance(data, pd.DataFrame) and data.empty and not params.get("start")):
                # Check if we have a fallback cache
                cached = self.cache_manager.get_payload(self.source_name, self.identifier)
                if cached is not None:
                    raw_cached, cached_meta = cached
                    TERMINAL_ADAPTER_FALLBACK_TOTAL.labels(source=self.source_name, entity_id=self.ticker).inc()
                    return BronzePayload(
                        protocol="yfinance",
                        origin_metadata={"ticker": self.ticker, "params": params, "is_fallback": True, "cache_source": "local_disk"},
                        execution_metadata={"status_code": 200, "fallback_reason": "EMPTY_OR_UNREACHABLE", "cached_at": cached_meta.get("cached_at")},
                        payload_format="json",
                        raw_payload=raw_cached
                    )

            # Increment ingestion counter
            TERMINAL_ADAPTER_MESSAGES_TOTAL.labels(source=self.source_name, entity_id=self.ticker).inc(len(data))
            
            # Publish to Redpanda (streaming path) if it's recent data
            if not data.empty:
                self._publish_to_streaming(data)
                
            raw_json = data.reset_index().to_json(orient="records", date_format="iso")
            
            # Cache successfully fetched payload
            if not data.empty:
                self.cache_manager.save_payload(
                    source=self.source_name,
                    identifier=self.identifier,
                    raw_payload=raw_json,
                    metadata={"ticker": self.ticker, "rows": len(data)}
                )

            return BronzePayload(
                protocol="yfinance",
                origin_metadata={"ticker": self.ticker, "params": params, "is_fallback": False},
                execution_metadata={"status_code": 200},
                payload_format="json",
                raw_payload=raw_json
            )
        except Exception as e:
            # Fallback to local cache if available
            cached = self.cache_manager.get_payload(self.source_name, self.identifier)
            if cached is not None:
                raw_cached, cached_meta = cached
                TERMINAL_ADAPTER_FALLBACK_TOTAL.labels(source=self.source_name, entity_id=self.ticker).inc()
                return BronzePayload(
                    protocol="yfinance",
                    origin_metadata={"ticker": self.ticker, "params": params, "is_fallback": True, "cache_source": "local_disk"},
                    execution_metadata={"status_code": 200, "fallback_reason": str(e), "cached_at": cached_meta.get("cached_at")},
                    payload_format="json",
                    raw_payload=raw_cached
                )
            raise

    def _publish_to_streaming(self, data: pd.DataFrame):
        """
        Publishes the latest data point to Redpanda.
        """
        try:
            latest = data.iloc[-1]
            # Use lowercase internal keys for the streaming payload
            payload = {
                "ticker": self.ticker,
                "timestamp": data.index[-1].isoformat(),
                "open": float(latest["Open"]),
                "high": float(latest["High"]),
                "low": float(latest["Low"]),
                "close": float(latest["Close"]),
                "volume": int(latest["Volume"])
            }
            self.producer.publish(topic="market.yahoo", key=self.ticker, value=payload)
            self.producer.flush()
        except Exception:
            # For now, we don't want streaming failures to break the whole fetch
            pass

    def to_silver(self, payload: BronzePayload, batch_id: Optional[str] = None) -> pd.DataFrame:
        """
        Normalize Yahoo agnostic BronzePayload into domain-specific OHLCV DataFrame
        using shared domain transformers.
        """
        import json
        import logging
        from domains.market.transformers import normalize_market_data
        from domains.market.models import SilverMarketOHLCV
        
        logger = logging.getLogger("adapters.market.yahoo")
        
        raw_data = json.loads(payload.raw_payload)
        if not raw_data:
            return pd.DataFrame(columns=list(SilverMarketOHLCV.model_fields.keys()))
            
        bronze_ref = payload.payload_checksum or "unknown"
        lineage = {
            "source_version": payload.origin_metadata.get("ticker", "unknown"),
            "bronze_reference": bronze_ref,
            "batch_id": batch_id
        }
        
        records_read = len(raw_data)
        records_transformed = 0
        records_rejected = 0
        rejection_reasons = {}
        
        validated_records = []
        for row in raw_data:
            # Map specific Yahoo keys to our domain transformer expectations
            transformed_row = {
                "symbol": self.ticker,
                "timestamp": row.get("Date") or row.get("Datetime"),
                "open": row.get("Open"),
                "high": row.get("High"),
                "low": row.get("Low"),
                "close": row.get("Close"),
                "volume": row.get("Volume"),
                "dividends": row.get("Dividends"),
                "stock_splits": row.get("Stock Splits"),
                "currency": "USD",
                "price_unit": "USD"
            }
            
            try:
                validated_model = normalize_market_data(transformed_row, lineage)
                validated_records.append(validated_model.model_dump())
                records_transformed += 1
            except Exception as e:
                records_rejected += 1
                exc_type = type(e).__name__
                rejection_reasons[exc_type] = rejection_reasons.get(exc_type, 0) + 1
                logger.warning(
                    "Validation failed for record. Source: %s, Domain: %s, Batch ID: %s, Bronze Record ID: %s, Exception Type: %s, Message: %s",
                    self.source_name, "market", batch_id or "N/A", bronze_ref, exc_type, str(e)
                )
                continue
                
        logger.info(
            "Transformation summary for %s (%s) - Read: %d, Transformed: %d, Rejected: %d, Rejection Reasons: %s, Written: %d",
            self.source_name, self.ticker, records_read, records_transformed, records_rejected, json.dumps(rejection_reasons), records_transformed
        )
        
        silver_df = pd.DataFrame(validated_records)
        if not silver_df.empty:
            silver_df = silver_df.set_index("timestamp", drop=False)
            
        return silver_df

    def get_metadata(self) -> TerminalDataFrameMetadata:
        metadata = TerminalDataFrameMetadata(
            name=f"Yahoo - {self.ticker}",
            description=f"Full OHLCV market data for {self.ticker} from Yahoo Finance.",
            frequency="daily",
            source=self.source_name
        )
        # Attach column schema for the Metadata Registry
        metadata.metadata["columns"] = [
            {"name": "open", "unit": "USD", "semantic_type": "price", "description": "Opening price"},
            {"name": "high", "unit": "USD", "semantic_type": "price", "description": "Highest price"},
            {"name": "low", "unit": "USD", "semantic_type": "price", "description": "Lowest price"},
            {"name": "close", "unit": "USD", "semantic_type": "price", "description": "Closing price (primary value)"},
            {"name": "volume", "unit": "SHARES", "semantic_type": "volume", "description": "Trading volume"},
            {"name": "dividends", "unit": "USD", "semantic_type": "dividend", "description": "Dividends paid"},
            {"name": "stock_splits", "unit": "RATIO", "semantic_type": "split", "description": "Stock split ratio"}
        ]
        return metadata

    @classmethod
    def get_search_parameter_schema(cls) -> Dict[str, Any]:
        return {
            "quotes_count": {"type": int, "default": 10},
            "news_count": {"type": int, "default": 0},
        }

    def search(self, query: str, limit: int = 10, **kwargs) -> List[SearchResult]:
        # yf.Search is a class (capital S), not a function
        search_obj = yf.Search(query, **kwargs)
        results = []
        quotes = (search_obj.quotes or [])[:limit]
        for quote in quotes:
            if quote.get("typeDisp") in ["Equity", "ETF", "Index"]:
                results.append(SearchResult(
                    identifier=quote["symbol"],
                    name=quote["shortname"],
                    description=quote.get("longname"),
                    source=self.source_name,
                    metadata={
                        "type": quote.get("typeDisp"),
                        "exchange": quote.get("exchange"),
                        "market": quote.get("market"),
                    }
                ))
        return results
