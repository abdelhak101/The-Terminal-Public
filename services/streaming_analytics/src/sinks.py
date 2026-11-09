import os
import pandas as pd
import uuid
from typing import List, Any, Dict
from shared.clickhouse import ClickHouseStorage, ClickHouseIOManager
from shared.registry import MetadataRegistry
from bytewax.outputs import DynamicSink, StatelessSinkPartition
import logging
import redis
import json

logger = logging.getLogger(__name__)

class RedisSinkPartition(StatelessSinkPartition):
    def __init__(self, host: str, port: int):
        self.client = redis.Redis(host=host, port=port, decode_responses=True)

    def write_batch(self, items: List[Any]):
        """
        Expects items to be a list of (symbol, metadata, feature_dict)
        """
        for symbol, _, features in items:
            try:
                # Store as: HSET feature_values {symbol} {json_data}
                self.client.hset("feature_values", symbol, json.dumps(features))
            except Exception as e:
                logger.error(f"Failed to persist feature to Redis for {symbol}: {e}")

class RedisSink(DynamicSink):
    def __init__(self, host: str = "redis", port: int = 6379):
        self.host = os.getenv("REDIS_HOST", host)
        self.port = int(os.getenv("REDIS_PORT", port))

    def build(self, step_id: str, worker_index: int, worker_count: int):
        return RedisSinkPartition(self.host, self.port)

class ClickHouseSinkPartition(StatelessSinkPartition):
    def __init__(self, library_name: str):
        self.library_name = library_name
        self.storage = ClickHouseStorage()
        self.registry = MetadataRegistry()
        self.io_manager = ClickHouseIOManager() # Used for serialization
        
        # Ensure schema is initialized
        if self.storage.check_health():
            self.storage.init_schema()

    def write_batch(self, items: List[Any]):
        """
        Expects items to be a list of (symbol, window_metadata, aggregated_bar_dict)
        """
        for symbol, metadata, bar in items:
            try:
                batch_id = str(uuid.uuid4())
                
                # 1. Register/Start Lineage
                asset_id = self.registry.register_asset(symbol, self.library_name)
                lineage_id = self.registry.start_lineage(asset_id, "streaming-analytics-flow", batch_id)
                
                # 2. Convert and Serialize to Super-Schema
                df = pd.DataFrame([bar])
                df_serialized = self.io_manager._serialize_df(df, symbol, batch_id)

                # 3. Write to ClickHouse
                table_name = f"{self.library_name}_data"
                self.storage.insert_df(table_name, df_serialized, layer=self.library_name)
                
                # 4. Commit Lineage
                self.registry.commit_lineage(lineage_id, version_id=lineage_id, batch_id=batch_id)
                logger.info(f"Persisted bar for {symbol} to {table_name} (batch {batch_id})")
                
            except Exception as e:
                logger.error(f"Failed to persist bar for {symbol}: {e}")

class ClickHouseSink(DynamicSink):
    def __init__(self, library_name: str = "silver"):
        self.library_name = library_name

    def build(self, step_id: str, worker_index: int, worker_count: int):
        return ClickHouseSinkPartition(self.library_name)
