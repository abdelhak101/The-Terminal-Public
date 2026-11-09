import os
import logging
import pandas as pd
import clickhouse_connect
import uuid
import threading
from typing import Any, Optional, List, Dict, Union
from opentelemetry import trace
from .metrics import TERMINAL_CLICKHOUSE_QUERY_TOTAL, TERMINAL_CLICKHOUSE_ROWS_TOTAL
from .registry import MetadataRegistry
from shared.models import BronzePayload

# Lazy import for Dagster to support non-Dagster environments
try:
    from dagster import ConfigurableIOManager
except ImportError:
    # Dummy base class for environments without Dagster installed
    class ConfigurableIOManager:
        pass

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

class ClickHouseStorage:
    # ... (rest of ClickHouseStorage methods same as before)
    """
    General purpose ClickHouse wrapper for high-performance storage and analytics.
    Replaces ArcticDB for massive-scale time-series.
    """
    def __init__(
        self, 
        host: str = None, 
        port: int = None, 
        user: str = None, 
        password: str = None, 
        database: str = None
    ):
        self.host = host or os.getenv("TERMINAL_CH_HOST") or os.getenv("CLICKHOUSE_HOST", "localhost")
        self.port = int(port or os.getenv("TERMINAL_CH_PORT") or os.getenv("CLICKHOUSE_PORT", "8123"))
        self.user = user or os.getenv("TERMINAL_CH_USER") or os.getenv("CLICKHOUSE_USER", "admin")
        self.password = password or os.getenv("TERMINAL_CH_PASS") or os.getenv("CLICKHOUSE_PASSWORD", "admin_password")
        self.database = database or os.getenv("TERMINAL_CH_DB") or os.getenv("CLICKHOUSE_DB", "terminal")
        self._thread_local = threading.local()
        self._registry = None

    @property
    def client(self):
        if not hasattr(self._thread_local, "client") or self._thread_local.client is None:
            try:
                client = clickhouse_connect.get_client(
                    host=self.host,
                    port=self.port,
                    username=self.user,
                    password=self.password
                )
                self._ensure_database_exists_for_client(client)
                client.database = self.database
                self._thread_local.client = client
            except Exception as e:
                logger.error(f"Failed to connect to ClickHouse at {self.host}:{self.port}: {e}")
                raise
        return self._thread_local.client

    def _ensure_database_exists_for_client(self, client):
        """Ensures the configured database exists, creates it if necessary."""
        try:
            client.command(f"CREATE DATABASE IF NOT EXISTS {self.database}")
            logger.info(f"Database '{self.database}' is ready")
        except Exception as e:
            logger.warning(f"Note: Could not create/check database '{self.database}': {e}")

    @property
    def registry(self) -> MetadataRegistry:
        if self._registry is None:
            self._registry = MetadataRegistry()
        return self._registry

    def check_health(self) -> bool:
        """Verifies connectivity to ClickHouse."""
        try:
            return self.client.ping()
        except Exception as e:
            logger.warning(f"ClickHouse health check failed: {e}")
            return False

    def init_schema(self):
        """Initializes the decoupled storage layer tables."""
        
        # 1. Bronze Layer - Agnostic Raw Payloads (TTL 90 Days)
        bronze_sql = """
        CREATE TABLE IF NOT EXISTS bronze_raw (
            id UUID,
            symbol LowCardinality(String) CODEC(LZ4),
            batch_id UUID,
            ingested_at DateTime64(3) CODEC(DoubleDelta, LZ4),
            protocol String CODEC(ZSTD(3)),
            origin_metadata String CODEC(ZSTD(3)),
            execution_metadata String CODEC(ZSTD(3)),
            payload_format String CODEC(ZSTD(3)),
            payload_checksum String CODEC(ZSTD(3)),
            raw_payload String CODEC(ZSTD(6))
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(ingested_at)
        ORDER BY (symbol, ingested_at, batch_id)
        TTL toDateTime(ingested_at) + INTERVAL 90 DAY;
        """
        self.execute(bronze_sql)
        logger.info("Initialized ClickHouse table: bronze_raw")
        
        # 2. Silver Layer - Domain Specific Tables (TTL 1 Year Recompress, ReplacingMergeTree for deduplication)
        
        # 2a. Macro Timeseries (FRED, BLS, Moneycontrol)
        macro_sql = """
        CREATE TABLE IF NOT EXISTS silver_macro_timeseries (
            series_id LowCardinality(String) CODEC(LZ4),
            observation_date DateTime64(3) CODEC(DoubleDelta, LZ4),
            batch_id UUID CODEC(LZ4),
            value Float64 CODEC(Gorilla, LZ4),
            realtime_start DateTime64(3) CODEC(LZ4),
            realtime_end DateTime64(3) CODEC(LZ4),
            unit LowCardinality(String) CODEC(LZ4),
            schema_version String CODEC(ZSTD(3)),
            transformation_version String CODEC(ZSTD(3)),
            bronze_record_id String CODEC(ZSTD(3)),
            source_version String CODEC(ZSTD(3))
        ) ENGINE = ReplacingMergeTree()
        PARTITION BY toYYYYMM(observation_date)
        ORDER BY (series_id, observation_date)
        TTL toDateTime(observation_date) + INTERVAL 1 YEAR RECOMPRESS CODEC(ZSTD(6));
        """
        self.execute(macro_sql)
        logger.info("Initialized ClickHouse table: silver_macro_timeseries")

        # 2b. Market OHLCV (Yahoo Finance)
        market_sql = """
        CREATE TABLE IF NOT EXISTS silver_market_ohlcv (
            symbol LowCardinality(String) CODEC(LZ4),
            timestamp DateTime64(3) CODEC(DoubleDelta, LZ4),
            batch_id UUID CODEC(LZ4),
            open Float64 CODEC(Gorilla, LZ4),
            high Float64 CODEC(Gorilla, LZ4),
            low Float64 CODEC(Gorilla, LZ4),
            close Float64 CODEC(Gorilla, LZ4),
            volume Float64 CODEC(Gorilla, LZ4),
            dividends Float64 CODEC(Gorilla, LZ4),
            stock_splits Float64 CODEC(Gorilla, LZ4),
            currency LowCardinality(String) CODEC(LZ4),
            price_unit LowCardinality(String) CODEC(LZ4),
            schema_version String CODEC(ZSTD(3)),
            transformation_version String CODEC(ZSTD(3)),
            bronze_record_id String CODEC(ZSTD(3)),
            source_version String CODEC(ZSTD(3))
        ) ENGINE = ReplacingMergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (symbol, timestamp)
        TTL toDateTime(timestamp) + INTERVAL 1 YEAR RECOMPRESS CODEC(ZSTD(6));
        """
        self.execute(market_sql)
        logger.info("Initialized ClickHouse table: silver_market_ohlcv")

        # 2c. Census Demographics
        census_sql = """
        CREATE TABLE IF NOT EXISTS silver_census_demographics (
            dataset_id LowCardinality(String) CODEC(LZ4),
            observation_date DateTime64(3) CODEC(DoubleDelta, LZ4),
            reference_period String CODEC(ZSTD(3)),
            batch_id UUID CODEC(LZ4),
            value Float64 CODEC(Gorilla, LZ4),
            category_code String CODEC(ZSTD(3)),
            data_type_code String CODEC(ZSTD(3)),
            dimensions Map(String, String) CODEC(ZSTD(3)),
            schema_version String CODEC(ZSTD(3)),
            transformation_version String CODEC(ZSTD(3)),
            bronze_record_id String CODEC(ZSTD(3)),
            source_version String CODEC(ZSTD(3))
        ) ENGINE = ReplacingMergeTree()
        PARTITION BY toYYYYMM(observation_date)
        ORDER BY (dataset_id, observation_date)
        TTL toDateTime(observation_date) + INTERVAL 1 YEAR RECOMPRESS CODEC(ZSTD(6));
        """
        self.execute(census_sql)
        logger.info("Initialized ClickHouse table: silver_census_demographics")

    def execute(self, sql: str, parameters: Optional[Union[Dict, List]] = None):
        """Executes a raw SQL command (DDL or DML)."""
        operation = sql.split()[0].upper() if sql else "UNKNOWN"
        with tracer.start_as_current_span("clickhouse_execute", attributes={"db.statement": sql}) as span:
            try:
                res = self.client.command(sql, parameters=parameters)
                TERMINAL_CLICKHOUSE_QUERY_TOTAL.labels(operation=operation, status="success").inc()
                return res
            except Exception as e:
                TERMINAL_CLICKHOUSE_QUERY_TOTAL.labels(operation=operation, status="error").inc()
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                logger.error(f"ClickHouse execution failed: {sql} | Error: {e}")
                raise

    def query_df(self, sql: str, parameters: Optional[Union[Dict, List]] = None) -> pd.DataFrame:
        """Executes a query and returns results as a Pandas DataFrame."""
        with tracer.start_as_current_span("clickhouse_query_df", attributes={"db.statement": sql}) as span:
            try:
                df = self.client.query_df(sql, parameters=parameters)
                TERMINAL_CLICKHOUSE_QUERY_TOTAL.labels(operation="SELECT", status="success").inc()
                TERMINAL_CLICKHOUSE_ROWS_TOTAL.labels(operation="SELECT", layer="unknown").inc(len(df))
                return df
            except Exception as e:
                TERMINAL_CLICKHOUSE_QUERY_TOTAL.labels(operation="SELECT", status="error").inc()
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                logger.error(f"ClickHouse query failed: {sql} | Error: {e}")
                raise

    def insert_df(self, table: str, df: pd.DataFrame, layer: str = "unknown"):
        """Inserts a DataFrame into the specified table."""
        if df.empty:
            return

        with tracer.start_as_current_span("clickhouse_insert_df", attributes={"db.table": table}) as span:
            try:
                # Fetch valid columns and types for the target table to avoid unrecognized column or null value errors
                columns_df = self.client.query_df(f"DESCRIBE TABLE {table}")
                table_columns = columns_df["name"].tolist()
                column_types = dict(zip(columns_df["name"], columns_df["type"]))
                
                # Filter DataFrame columns to only match ClickHouse table fields
                df_clean = df[[col for col in df.columns if col in table_columns]].copy()
                
                if df_clean.empty:
                    logger.warning(f"No matching columns for table {table}. DataFrame columns: {df.columns.tolist()}")
                    return

                # Coerce None/NaN values for non-nullable columns
                for col in df_clean.columns:
                    col_type = column_types.get(col, "")
                    if "Nullable" not in col_type:
                        if col_type.startswith("String") or col_type.startswith("LowCardinality(String)"):
                            df_clean[col] = df_clean[col].fillna("")
                        elif col_type.startswith("DateTime") or col_type.startswith("Date"):
                            df_clean[col] = df_clean[col].fillna(pd.Timestamp("1970-01-01"))

                # Temporarily increase max partitions per insert block
                settings = {'max_partitions_per_insert_block': 10000}
                
                # If data spans many partitions, split by month and insert in chunks
                if 'timestamp' in df_clean.columns:
                    # Avoid ValueError: 'timestamp' is both an index level and a column label
                    if df_clean.index.name == 'timestamp':
                        df_clean.index.name = None
                    elif df_clean.index.names and 'timestamp' in df_clean.index.names:
                        df_clean.index.names = [None if n == 'timestamp' else n for n in df_clean.index.names]
                        
                    df_sorted = df_clean.sort_values('timestamp')
                    df_sorted['year_month'] = df_sorted['timestamp'].dt.to_period('M')
                    
                    for _, chunk in df_sorted.groupby('year_month'):
                        chunk_clean = chunk.drop(columns=['year_month'])
                        self.client.insert_df(table, chunk_clean, settings=settings)
                else:
                    self.client.insert_df(table, df_clean, settings=settings)
                
                TERMINAL_CLICKHOUSE_QUERY_TOTAL.labels(operation="INSERT", status="success").inc()
                TERMINAL_CLICKHOUSE_ROWS_TOTAL.labels(operation="INSERT", layer=layer).inc(len(df_clean))
            except Exception as e:
                TERMINAL_CLICKHOUSE_QUERY_TOTAL.labels(operation="INSERT", status="error").inc()
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                logger.error(f"ClickHouse insert failed for table {table}: {e}")
                raise

    def _get_table_columns(self, table_name: str) -> tuple[str, str]:
        """Returns the (symbol_col, time_col) for the given table name."""
        if table_name == "bronze_raw":
            return "symbol", "ingested_at"
        elif table_name == "silver_macro_timeseries":
            return "series_id", "observation_date"
        elif table_name == "silver_census_demographics":
            return "dataset_id", "observation_date"
        else:
            return "symbol", "timestamp"

    def _get_db_symbol(self, table_name: str, registry_symbol: str) -> str:
        """
        Maps a registry symbol (e.g. 'yahoo.dx-y.nyb_main_1d_e92df') to the actual
        symbol value stored in the database column (e.g. 'DX-Y.NYB').
        """
        if not registry_symbol:
            return ""
            
        parts = registry_symbol.split(".", 1)
        if len(parts) > 1:
            rest = parts[1]
            suffix_parts = rest.rsplit("_", 3)
            raw_id = suffix_parts[0] if len(suffix_parts) == 4 else rest.split("_")[0]
        else:
            raw_id = registry_symbol

        if table_name == "silver_macro_timeseries":
            return raw_id.upper()
            
        elif table_name == "silver_census_demographics":
            if raw_id.startswith("eits_"):
                sub_parts = raw_id.split("_")
                if len(sub_parts) >= 2:
                    return f"timeseries/{sub_parts[0]}/{sub_parts[1]}"
            return "timeseries/eits/marts"
            
        elif table_name == "silver_market_ohlcv":
            return raw_id.upper()
            
        return registry_symbol

    def get_symbol_data(
        self, 
        symbol: str, 
        library: str, 
        version_id: Optional[int] = None, 
        label: str = "main",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        target_table: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Retrieves symbol data with PIT support.
        Resolves version to batch_ids via Registry.
        """
        batch_ids = self.registry.get_batches_for_version(symbol, library, version_id, label)
        if not batch_ids:
            return pd.DataFrame()

        table_name = target_table or f"{library}_data"
        symbol_col, time_col = self._get_table_columns(table_name)
        db_symbol = self._get_db_symbol(table_name, symbol)
        final_clause = "FINAL" if table_name != "bronze_raw" else ""
        sql = f"SELECT * FROM {table_name} {final_clause} WHERE {symbol_col} = %(symbol)s AND batch_id IN %(batch_ids)s"
        params = {"symbol": db_symbol, "batch_ids": batch_ids}

        if start_date:
            sql += f" AND {time_col} >= %(start_date)s"
            params["start_date"] = start_date
        if end_date:
            sql += f" AND {time_col} <= %(end_date)s"
            params["end_date"] = end_date

        sql += f" ORDER BY {time_col} ASC"
        
        return self.query_df(sql, parameters=params)

    def get_symbol_snapshot(
        self, 
        symbol: str, 
        library: str, 
        version_id: Optional[int] = None, 
        label: str = "main",
        max_points: int = 2000,
        target_table: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Returns a downsampled set of points for visualization."""
        import numpy as np
        
        table_name = target_table or (f"bronze_raw" if library == "bronze" else f"{library}_data")
        symbol_col, time_col = self._get_table_columns(table_name)
        
        # If bronze_raw, just return recent records
        if table_name == "bronze_raw":
            db_symbol = self._get_db_symbol(table_name, symbol)
            sql = f"SELECT * FROM {table_name} WHERE {symbol_col} = %(symbol)s ORDER BY {time_col} DESC LIMIT 100"
            df = self.query_df(sql, parameters={"symbol": db_symbol})
            return df.to_dict(orient="records") if not df.empty else []

        df = self.get_symbol_data(symbol, library, version_id, label, target_table=target_table)
        if df.empty:
            logger.warning(f"No data for snapshot: {symbol} in {library}")
            return []

        # Identify target column - priority: value > close > price > open > high > low > adjusted_close
        target_col = None
        for candidate_col in ["value", "close", "price", "open", "high", "low", "adjusted_close"]:
            if candidate_col in df.columns:
                target_col = candidate_col
                break
        
        if not target_col:
            numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
            if numeric_cols:
                target_col = numeric_cols[0]
        
        if not target_col:
            logger.warning(f"No numeric column for snapshot: {symbol}")
            return []
        
        # Downsample if needed
        total_rows = len(df)
        if total_rows > max_points:
            step = total_rows // max_points
            df = df.iloc[::step]
        
        # Build snapshot - manually handle each row
        snapshot = []
        for _, row in df.iterrows():
            try:
                timestamp_val = row[time_col]
                v = row[target_col]
                
                # Format timestamp
                if isinstance(timestamp_val, pd.Timestamp):
                    t = timestamp_val.isoformat()
                else:
                    t = str(timestamp_val)
                
                # Check value
                if pd.isna(v) or v in [np.inf, -np.inf]:
                    continue
                    
                snapshot.append({"t": t, "v": float(v)})
            except Exception as e:
                continue
        
        logger.info(f"Created snapshot with {len(snapshot)} points for {symbol}")
        return snapshot

    def get_symbol_info(self, library: str, symbol: str, label: str = "main", target_table: Optional[str] = None) -> Dict[str, Any]:
        """Retrieves metadata and storage stats for a symbol."""
        table_name = target_table or (f"bronze_raw" if library == "bronze" else f"{library}_data")
        symbol_col, time_col = self._get_table_columns(table_name)
        db_symbol = self._get_db_symbol(table_name, symbol)
        final_clause = "FINAL" if table_name != "bronze_raw" else ""
        
        try:
            # 1. Get row count and last updated
            sql = f"SELECT count(*) as row_count, max({time_col}) as last_updated FROM {table_name} {final_clause} WHERE {symbol_col} = %(symbol)s"
            stats = self.query_df(sql, parameters={"symbol": db_symbol})
            
            if stats.empty or stats.iloc[0]["row_count"] == 0:
                return {"row_count": 0, "size_bytes": 0, "last_updated": None}

            row_count = int(stats.iloc[0]["row_count"])
            last_updated = stats.iloc[0]["last_updated"]

            # 2. Get storage size from system.parts
            size_sql = "SELECT sum(bytes_on_disk) as size FROM system.parts WHERE table = %(table)s AND active"
            size_df = self.query_df(size_sql, parameters={"table": table_name})
            size_bytes = int(size_df.iloc[0]["size"]) if not size_df.empty else 0

            return {
                "row_count": row_count,
                "size_bytes": size_bytes,
                "last_updated": last_updated
            }
        except Exception as e:
            logger.error(f"Failed to get info for {symbol} in {library}: {e}")
            return {"row_count": 0, "size_bytes": 0, "last_updated": None}

    def get_symbol_data_slice(
        self, 
        library: str, 
        symbol: str, 
        label: str = "main", 
        page: int = 1, 
        size: int = 50,
        reverse: bool = False,
        target_table: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns a paginated slice of data for a symbol.
        """
        import numpy as np
        
        table_name = target_table or (f"bronze_raw" if library == "bronze" else f"{library}_data")
        symbol_col, time_col = self._get_table_columns(table_name)
        db_symbol = self._get_db_symbol(table_name, symbol)
        final_clause = "FINAL" if table_name != "bronze_raw" else ""
            
        offset = (page - 1) * size
        order = "DESC" if reverse else "ASC"
        
        # We query the latest version batches for the slice
        batch_ids = self.registry.get_batches_for_version(symbol, library, label=label)
        if not batch_ids:
            return []

        sql = f"""
            SELECT * FROM {table_name} {final_clause}
            WHERE {symbol_col} = %(symbol)s AND batch_id IN %(batch_ids)s
            ORDER BY {time_col} {order}
            LIMIT %(limit)s OFFSET %(offset)s
        """
        params = {
            "symbol": db_symbol, 
            "batch_ids": batch_ids,
            "limit": size,
            "offset": offset
        }
        
        df = self.query_df(sql, parameters=params)
        
        records = []
        for _, row in df.iterrows():
            record = {}
            for col in df.columns:
                val = row[col]
                
                # Handle timestamp
                if col == time_col and pd.notna(val):
                    record[col] = val.strftime('%Y-%m-%d %H:%M:%S')
                # Handle batch_id UUID
                elif col == 'batch_id':
                    record[col] = str(val)
                # Handle numeric values
                elif pd.api.types.is_numeric_dtype(df[col]):
                    if pd.isna(val) or val in [np.inf, -np.inf]:
                        record[col] = None
                    else:
                        record[col] = float(val) if isinstance(val, (float, np.floating)) else int(val)
                # Handle everything else
                else:
                    if pd.isna(val):
                        record[col] = None
                    else:
                        record[col] = val
            records.append(record)
        
        return records

    def delete_symbol(self, library: str, symbol: str, label: str = "main", target_table: Optional[str] = None):
        """Deletes all data for a specific symbol in a layer."""
        table_name = target_table or f"{library}_data"
        symbol_col, _ = self._get_table_columns(table_name)
        db_symbol = self._get_db_symbol(table_name, symbol)
        # In ClickHouse, this is an asynchronous mutation
        sql = f"ALTER TABLE {table_name} DELETE WHERE {symbol_col} = %(symbol)s"
        self.execute(sql, parameters={"symbol": db_symbol})
        logger.info(f"Triggered deletion of symbol {db_symbol} from {table_name}")

class ClickHouseIOManager(ConfigurableIOManager):
    """
    Dagster IO Manager for ClickHouse.
    Handles storage of unified data layers with metadata-led versioning.
    """
    def _get_storage(self) -> ClickHouseStorage:
        return ClickHouseStorage()

    def handle_output(self, context: Any, obj: Any):
        """Save the output of an asset to ClickHouse and track lineage in Postgres."""
        if not context.has_asset_key:
            return

        library_name = context.asset_key.path[0]  # e.g., 'bronze', 'silver', or 'gold'
        symbol = ".".join(context.asset_key.path[1:])
        label = context.metadata.get("label", "main")
        run_id = context.run_id
        
        # Get batch_id: reuse existing batch_id from df/object if present
        # to ensure metadata lineage matches the physically written batch_id
        batch_id = None
        if not isinstance(obj, BronzePayload):
            if isinstance(obj, pd.DataFrame) and "batch_id" in obj.columns and not obj.empty:
                batch_id = str(obj["batch_id"].iloc[0])
            elif isinstance(obj, list) and len(obj) > 0 and isinstance(obj[0], dict) and "batch_id" in obj[0]:
                batch_id = str(obj[0]["batch_id"])
        if not batch_id:
            batch_id = str(uuid.uuid4())

        storage = self._get_storage()
        registry = storage.registry

        with tracer.start_as_current_span("clickhouse_io_write", attributes={
            "asset.symbol": symbol,
            "asset.library": library_name,
            "asset.batch_id": batch_id
        }) as span:
            # 1. Register Asset
            asset_id = registry.register_asset(
                symbol=symbol, 
                library=library_name,
                label=label,
                description=context.metadata.get("description"),
                metadata=context.metadata
            )

            lineage_id = None
            try:
                # 2. Prepare Data
                if isinstance(obj, BronzePayload):
                    import json
                    df = pd.DataFrame([{
                        "id": str(uuid.uuid4()),
                        "symbol": symbol,
                        "batch_id": batch_id,
                        "ingested_at": pd.Timestamp.now(),
                        "protocol": obj.protocol,
                        "origin_metadata": json.dumps(obj.origin_metadata, default=str),
                        "execution_metadata": json.dumps(obj.execution_metadata, default=str),
                        "payload_format": obj.payload_format,
                        "payload_checksum": obj.payload_checksum or "",
                        "raw_payload": obj.raw_payload
                    }])
                    table_name = "bronze_raw"
                else:
                    if isinstance(obj, pd.DataFrame):
                        df = obj.copy()
                    else:
                        # Convert non-DataFrame to single-row DF
                        df = pd.DataFrame([obj] if not isinstance(obj, list) else obj)
                        
                    # Target table can be explicitly set in Dagster asset metadata
                    # Fallback to library_name_data for legacy
                    table_name = context.metadata.get("target_table", f"{library_name}_data")
                    
                    if "batch_id" not in df.columns:
                        df["batch_id"] = batch_id
                    if "symbol" not in df.columns:
                        df["symbol"] = symbol

                if df.empty:
                    context.log.info(f"Asset {symbol} ({label}) is empty (no new rows). Skipping ClickHouse insert and lineage commit.")
                    return

                lineage_id = registry.start_lineage(asset_id, run_id, batch_id)

                # Auto-register columns in Postgres metadata DB
                columns_to_register = []
                for col in df.columns:
                    columns_to_register.append({
                        "name": col,
                        "description": f"Auto-registered column: {col}",
                        "unit": "unknown",
                        "semantic_type": "unknown"
                    })
                registry.register_columns(asset_id, columns_to_register)

                # 3. Write to ClickHouse
                context.log.info(f"Writing {symbol} ({label}) to ClickHouse table '{table_name}' with batch_id {batch_id}")
                storage.insert_df(table_name, df, layer=library_name)

                # 4. Commit Lineage
                # We use lineage_id as the version_id for consistency with Arctic-style indexing
                registry.commit_lineage(lineage_id, version_id=lineage_id, batch_id=batch_id)
                context.log.info(f"Committed lineage for {symbol} ({label}) batch {batch_id}")

            except Exception as e:
                if lineage_id is not None:
                    registry.fail_lineage(lineage_id, str(e))
                context.log.error(f"Failed to write {symbol} to ClickHouse: {str(e)}")
                span.record_exception(e)
                raise

    def load_input(self, context: Any) -> pd.DataFrame:
        """Load an asset from ClickHouse as input for another asset."""
        library_name = context.asset_key.path[0]
        symbol = ".".join(context.asset_key.path[1:])
        
        version = context.metadata.get("version")
        label = context.metadata.get("label", "main")
        target_table = context.metadata.get("target_table", f"{library_name}_data")

        storage = self._get_storage()
        context.log.info(f"Loading {symbol} (version={version}) from ClickHouse table '{target_table}'")
        
        if target_table == "bronze_raw":
            batch_ids = storage.registry.get_batches_for_version(symbol, library_name, version, label)
            if not batch_ids: return pd.DataFrame()
            sql = f"SELECT * FROM bronze_raw WHERE batch_id IN %(batch_ids)s"
            df = storage.query_df(sql, {"batch_ids": batch_ids})
            return df
        else:
            return storage.get_symbol_data(symbol, library_name, version_id=version, label=label, target_table=target_table)
