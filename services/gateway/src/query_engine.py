import pandas as pd
from typing import List, Dict, Any, Optional
from shared.registry import MetadataRegistry
from shared.clickhouse import ClickHouseStorage
from adapters import ADAPTER_MAP
import os
import logging

logger = logging.getLogger(__name__)

class QueryEngine:
    """
    Handles semantic query resolution and batch data retrieval from ClickHouse.
    """
    def __init__(self):
        self.storage = ClickHouseStorage()
        self.registry = MetadataRegistry()

    def check_health(self) -> bool:
        """Verifies connectivity to ClickHouse."""
        return self.storage.check_health()

    def _get_asset_info(self, library: str, symbol: str) -> tuple[Optional[str], Optional[str]]:
        """Resolves target table and label from metadata registry assets."""
        assets = self.registry.get_all_assets()
        for a in assets:
            if a["library"] == library and a["symbol"] == symbol:
                return a.get("metadata", {}).get("target_table"), a.get("label")
        return None, None

    def _apply_filters(
        self, 
        df: pd.DataFrame, 
        columns: Optional[List[str]] = None,
        time_col: str = "timestamp"
    ) -> pd.DataFrame:
        """
        Applies column filtering to a DataFrame. 
        Temporal slicing is now handled in ClickHouse SQL.
        """
        if df.empty:
            return df

        # Column Filtering
        if columns:
            # Ensure the correct time column is always included
            if time_col not in columns:
                columns.append(time_col)
            # Only filter if columns exist in DF
            actual_cols = [c for c in columns if c in df.columns]
            df = df[actual_cols]
            
        return df

    def execute_query(
        self, 
        requests: List[Dict[str, Any]], 
        global_start: Optional[str] = None,
        global_end: Optional[str] = None,
        global_columns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Executes a batch of semantic requests against ClickHouse with PIT support.
        """
        results = {}
        metadata = {}

        for req in requests:
            symbol = req.get("symbol")
            adapter_type = req.get("adapter_type")
            params = req.get("params", {})
            version = req.get("version")
            
            # Local overrides
            start_date = req.get("start_date") or global_start
            end_date = req.get("end_date") or global_end
            columns = req.get("columns") or global_columns

            try:
                # 1. Resolve internal symbol name
                library_name = "silver"
                target_table, label = self._get_asset_info(library_name, symbol)
                label = req.get("label") or label or "main"
                _, time_col = self.storage._get_table_columns(target_table or "silver_data")

                # 2. Read from ClickHouse using PIT-aware method
                df = self.storage.get_symbol_data(
                    library=library_name,
                    symbol=symbol,
                    version_id=version,
                    label=label,
                    start_date=start_date,
                    end_date=end_date,
                    target_table=target_table
                )

                # 3. Apply Column Filtering
                df = self._apply_filters(df, columns, time_col=time_col)

                # 4. Store Result
                results[symbol] = df.to_dict(orient="records")
                metadata[symbol] = {
                    "status": "SUCCESS",
                    "rows": len(df),
                    "internal_key": symbol,
                    "storage": "clickhouse"
                }

            except Exception as e:
                logger.error(f"Failed to query {symbol}: {e}")
                results[symbol] = []
                metadata[symbol] = {
                    "status": "FAILED",
                    "error": str(e)
                }

        return {
            "data": results,
            "metadata": metadata
        }

    def read_direct(
        self, 
        library: str, 
        symbol: str, 
        start_date: Optional[str] = None, 
        end_date: Optional[str] = None, 
        columns: Optional[List[str]] = None,
        limit: int = 1000,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Reads data directly from a specified ClickHouse layer.
        """
        target_table, label = self._get_asset_info(library, symbol)
        label = label or "main"
        _, time_col = self.storage._get_table_columns(target_table or f"{library}_data")
        
        df = self.storage.get_symbol_data(
            library=library,
            symbol=symbol,
            label=label,
            start_date=start_date,
            end_date=end_date,
            target_table=target_table
        )
        
        df = self._apply_filters(df, columns, time_col=time_col)
        
        # Apply pagination
        paged_df = df.iloc[offset : offset + limit]
        return paged_df.to_dict(orient="records")
