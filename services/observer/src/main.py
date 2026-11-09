import os
import time
import logging
import threading
import pandas as pd
from typing import List, Dict, Any
from prometheus_client import start_http_server, Gauge
from shared.registry import MetadataRegistry
from shared.clickhouse import ClickHouseStorage
from shared.metrics import (
    TERMINAL_CLICKHOUSE_COMPRESSION_RATIO, 
    TERMINAL_CLICKHOUSE_OLDEST_RECORD_DAYS
)
from src.evaluator import QualityEvaluator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("terminal-observer")

# Prometheus Metrics
FRESHNESS_GAUGE = Gauge(
    'terminal_asset_freshness_seconds',
    'Seconds since the last successful update of an asset',
    ['symbol', 'library']
)
QUALITY_GAUGE = Gauge(
    'terminal_asset_quality_score',
    'Quality score of an asset based on registry rules',
    ['symbol', 'library']
)
GAP_COUNT_GAUGE = Gauge(
    'terminal_asset_gap_count',
    'Total number of temporal gaps found in the scan window',
    ['symbol', 'library']
)
STORAGE_SIZE_GAUGE = Gauge(
    'terminal_asset_storage_bytes',
    'Storage size of an asset in ClickHouse',
    ['symbol', 'library']
)
INVENTORY_SYMBOL_ROWS = Gauge(
    'terminal_inventory_symbol_rows',
    'Total number of rows for a symbol in ClickHouse',
    ['symbol', 'library']
)
INVENTORY_LIBRARY_SYMBOLS = Gauge(
    'terminal_inventory_library_symbols_total',
    'Total number of unique symbols in a ClickHouse layer',
    ['library']
)
INVENTORY_SCAN_COUNTER = Gauge(
    'terminal_inventory_scan_total',
    'Total number of inventory scans performed'
)

class ObserverService:
    def __init__(self):
        self.registry = MetadataRegistry()
        self.storage = ClickHouseStorage()
        self.evaluator = QualityEvaluator(self.storage)
        self.interval = int(os.getenv("OBSERVER_INTERVAL", "60"))
        logger.info("Observer initialized for ClickHouse storage")

    def update_inventory_metrics(self):
        """
        Scan ClickHouse layers and export symbol-level metadata.
        """
        logger.info("Starting ClickHouse inventory scan")
        INVENTORY_SCAN_COUNTER.inc()
        
        if not self.storage.check_health():
            logger.error("ClickHouse is unreachable, skipping scan.")
            return
        
        layers = ["bronze", "silver", "gold"]
        for layer in layers:
            table_name = f"{layer}_data"
            try:
                # 1. Get unique symbols and row counts
                sql = f"SELECT symbol, count(*) as row_count FROM {table_name} GROUP BY symbol"
                df = self.storage.query_df(sql)
                
                logger.info(f"Layer {layer} has {len(df)} symbols")
                INVENTORY_LIBRARY_SYMBOLS.labels(library=layer).set(len(df))
                
                for _, row in df.iterrows():
                    symbol = row['symbol']
                    row_count = row['row_count']
                    INVENTORY_SYMBOL_ROWS.labels(
                        symbol=symbol, 
                        library=layer
                    ).set(row_count)
                
            except Exception as e:
                logger.error(f"Error scanning ClickHouse table {table_name}: {e}")

    def update_storage_metrics(self):
        """
        Calculate ClickHouse storage size, compression, and lifecycle stats.
        """
        try:
            # 1. Total and Layer Sizes
            sql = "SELECT table, sum(bytes_on_disk) as size FROM system.parts WHERE active GROUP BY table"
            df = self.storage.query_df(sql)
            for _, row in df.iterrows():
                table = row['table']
                size = row['size']
                if table.endswith("_data"):
                    layer = table.replace("_data", "").lower()
                    STORAGE_SIZE_GAUGE.labels(symbol="TOTAL", library=layer).set(size)
            
            total_size = df['size'].sum()
            STORAGE_SIZE_GAUGE.labels(symbol="TOTAL", library="CLICKHOUSE").set(total_size)

            # 2. Compression Ratios
            comp_sql = """
                SELECT 
                    table, 
                    sum(data_uncompressed_bytes) as uncompressed, 
                    sum(data_compressed_bytes) as compressed 
                FROM system.columns 
                WHERE table LIKE '%_data' 
                GROUP BY table
            """
            comp_df = self.storage.query_df(comp_sql)
            for _, row in comp_df.iterrows():
                layer = row['table'].replace("_data", "").lower()
                ratio = row['uncompressed'] / row['compressed'] if row['compressed'] > 0 else 1.0
                TERMINAL_CLICKHOUSE_COMPRESSION_RATIO.labels(layer=layer).set(ratio)

            # 3. Oldest Record Age (TTL Monitoring)
            layers = ["bronze", "silver", "gold"]
            for layer in layers:
                try:
                    age_sql = f"SELECT min(timestamp) as oldest FROM {layer}_data"
                    age_df = self.storage.query_df(age_sql)
                    if not age_df.empty and pd.notnull(age_df.iloc[0]['oldest']):
                        oldest_ts = age_df.iloc[0]['oldest']
                        # Handle both string and timestamp types from query_df
                        if isinstance(oldest_ts, str):
                            oldest_ts = pd.to_datetime(oldest_ts)
                        
                        age_days = (pd.Timestamp.now() - oldest_ts.replace(tzinfo=None)).days
                        TERMINAL_CLICKHOUSE_OLDEST_RECORD_DAYS.labels(layer=layer).set(age_days)
                except Exception as e:
                    logger.debug(f"Could not get oldest record for {layer}: {e}")

            logger.info(f"Updated ClickHouse storage metrics. Total size: {total_size} bytes")
        except Exception as e:
            logger.error(f"Error updating ClickHouse storage metrics: {e}")

    def get_all_assets_with_rules(self) -> List[Dict[str, Any]]:
        """
        Fetch all assets and their associated quality rules from the registry.
        """
        return self.registry.get_all_assets()

    def evaluate_freshness(self, asset: Dict[str, Any]):
        """
        Calculate and export freshness metrics.
        """
        if asset.get('updated_at'):
            freshness = (time.time() - asset['updated_at'].timestamp())
            FRESHNESS_GAUGE.labels(symbol=asset['symbol'], library=asset['library']).set(freshness)

    def evaluate_quality(self, asset: Dict[str, Any]):
        """
        Evaluate DQ rules using the QualityEvaluator.
        """
        try:
            results = self.evaluator.evaluate_asset(asset, [])  # Rules list not used in MVP
            symbol = asset['symbol']
            library = asset['library']
            
            QUALITY_GAUGE.labels(symbol=symbol, library=library).set(results['score'])
            GAP_COUNT_GAUGE.labels(symbol=symbol, library=library).set(results['gap_count'])
            
            if results['score'] < 100:
                logger.warning(f"Quality Issue: {symbol} in {library} has score {results['score']:.2f} (Gaps: {results['gap_count']})")
        except Exception as e:
            logger.error(f"Error evaluating quality for {asset.get('symbol')}: {e}")

    def run_cycle(self):
        """
        A single polling cycle.
        """
        logger.info("Starting observer polling cycle...")
        try:
            self.update_storage_metrics()
            
            # 1. Evaluate assets from Registry
            assets = self.get_all_assets_with_rules()
            for asset in assets:
                self.evaluate_freshness(asset)
                self.evaluate_quality(asset)
            
            # 2. Perform deep inventory scan (ClickHouse direct)
            self.update_inventory_metrics()
            
        except Exception as e:
            logger.error(f"Error in observer cycle: {e}")

    def start(self):
        """
        Main loop.
        """
        metrics_port = int(os.getenv("METRICS_PORT", "8000"))
        start_http_server(metrics_port)
        logger.info(f"Prometheus metrics exporter started on port {metrics_port}")

        while True:
            self.run_cycle()
            time.sleep(self.interval)

if __name__ == "__main__":
    service = ObserverService()
    service.start()
