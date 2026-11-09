from typing import List, Dict, Any, Optional
from dagster import AssetKey, AssetsDefinition, asset, AssetOut, multi_asset, Output, RetryPolicy
from shared.adapters import BaseAdapter
from shared.registry import MetadataRegistry
import pandas as pd

DEFAULT_RETRY_POLICY = RetryPolicy(max_retries=2, delay=5)

def create_adapter_assets(
    adapter: BaseAdapter,
    config: Dict[str, Any] = None,
    label: str = "main",
    adapter_type: Optional[str] = None
) -> List[AssetsDefinition]:
    """
    Factory function to create Dagster Bronze and Silver assets from a BaseAdapter.
    Supports incremental ingestion and isolated asset keys via hashing.
    """
    config = config or {}
    source = adapter_type or adapter.source_name.lower().replace(" ", "_")
    identifier = adapter.identifier.lower().replace(" ", "_")
    
    # Generate Config Hash
    config_hash = adapter.get_config_hash(config)
    interval = config.get("interval", "default")
    
    # Asset Keys now include the interval, label, and hash for isolation
    bronze_key = AssetKey(["bronze", source, f"{identifier}_{label}_{interval}_{config_hash}"])
    silver_key = AssetKey(["silver", source, f"{identifier}_{label}_{interval}_{config_hash}"])
    
    # Map source to domain-specific silver table
    target_table_map = {
        "fred": "silver_macro_timeseries",
        "bls": "silver_macro_timeseries",
        "yahoo": "silver_market_ohlcv",
        "yahoo_finance": "silver_market_ohlcv",
        "census": "silver_census_demographics",
        "census_bureau": "silver_census_demographics",
        "moneycontrol": "silver_macro_timeseries"
    }
    target_table = target_table_map.get(source, "silver_data")

    import re
    sanitized_id = re.sub(r'[^a-zA-Z0-9_]', '_', identifier)

    @multi_asset(
        outs={
            "bronze_asset": AssetOut(key=bronze_key, metadata={"target_table": "bronze_raw", "label": label}, description="Raw source data. [Learn more](http://localhost:23002/technical/data-layers/)"),
            "silver_asset": AssetOut(key=silver_key, metadata={"target_table": target_table, "label": label}, description="Normalized and validated data. [Learn more](http://localhost:23002/technical/data-layers/)"),
        },
        name=f"{source}_{sanitized_id}_{label}_{config_hash}_pipeline",
        group_name=source,
        compute_kind="python",
        retry_policy=DEFAULT_RETRY_POLICY,
    )
    def adapter_pipeline(context):
        registry = MetadataRegistry()
        
        # 1. Get Last Observed Timestamp (Stateful Ingestion)
        # We align with ClickHouseIOManager symbol path convention (strip layer prefix)
        registry_symbol = ".".join(silver_key.path[1:])
        last_ts = registry.get_last_observed_timestamp(registry_symbol, "silver", label=label)
        
        # 2. Prepare Fetch Params (filtered against adapter schema)
        schema = adapter.get_parameter_schema()
        fetch_params = {k: v for k, v in config.items() if k in schema}
        if last_ts:
            context.log.info(f"Incremental fetch for {identifier} since {last_ts}")
            # Adapters handle 'start' or 'observation_start' appropriately
            if source == "fred":
                fetch_params["observation_start"] = last_ts.strftime("%Y-%m-%d")
            else:
                fetch_params["start"] = last_ts
        else:
            context.log.info(f"Initial bootstrap for {identifier}")

        # 3. Fetch Raw
        context.log.info(f"Fetching data from {adapter.source_name} for {identifier}")
        bronze_payload = adapter.fetch_raw(**fetch_params)
        
        # 4. To Silver & Precision Slicing
        context.log.info(f"Normalizing {adapter.source_name} data to Silver layer")
        silver_df = adapter.to_silver(bronze_payload, batch_id=context.run_id)
        
        # Helper to extract the datetime series from silver_df
        def _get_ts_series(df: pd.DataFrame) -> pd.Series:
            for col_candidate in ["timestamp", "observation_date", "Date", "date"]:
                if col_candidate in df.columns:
                    return pd.to_datetime(df[col_candidate], utc=True)
            return pd.to_datetime(df.index, utc=True)

        if last_ts and not silver_df.empty:
            # Ensure strictly newer data (Precision Slicing) with UTC normalized comparison
            original_count = len(silver_df)
            ts_series_utc = _get_ts_series(silver_df)
            last_ts_utc = pd.to_datetime(last_ts, utc=True)
            silver_df = silver_df[ts_series_utc > last_ts_utc]
            context.log.info(f"Sliced data: {original_count} -> {len(silver_df)} rows (after {last_ts_utc})")

        # 5. Update Registry State
        if not silver_df.empty:
            raw_ts_series = silver_df["timestamp"] if "timestamp" in silver_df.columns else (
                silver_df["observation_date"] if "observation_date" in silver_df.columns else silver_df.index
            )
            new_last_ts = pd.to_datetime(raw_ts_series.max())
            # Ensure the asset row exists in PostgreSQL before updating the timestamp
            registry.register_asset(
                symbol=registry_symbol,
                library="silver",
                label=label,
                description=adapter.get_metadata().description
            )
            registry.update_last_observed_timestamp(registry_symbol, "silver", new_last_ts, label=label)
            context.log.info(f"Updated last_observed_timestamp to {new_last_ts}")

        # Map source to domain-specific silver table
        target_table_map = {
            "fred": "silver_macro_timeseries",
            "bls": "silver_macro_timeseries",
            "yahoo": "silver_market_ohlcv",
            "yahoo_finance": "silver_market_ohlcv",
            "census": "silver_census_demographics",
            "census_bureau": "silver_census_demographics",
            "moneycontrol": "silver_macro_timeseries"
        }
        target_table = target_table_map.get(source, "silver_data")

        # Add metadata for Dagster UI and IO Manager
        metadata = adapter.get_metadata().dict()
        metadata["config_hash"] = config_hash
        metadata["label"] = label
        metadata["target_table"] = target_table
        if not silver_df.empty:
            raw_ts = silver_df["timestamp"] if "timestamp" in silver_df.columns else (
                silver_df["observation_date"] if "observation_date" in silver_df.columns else silver_df.index
            )
            metadata["last_ingested"] = pd.to_datetime(raw_ts.max()).isoformat()
        else:
            metadata["last_ingested"] = None
        
        yield Output(bronze_payload, output_name="bronze_asset", metadata={"label": label})
        yield Output(silver_df, output_name="silver_asset", metadata=metadata)

    return [adapter_pipeline]
