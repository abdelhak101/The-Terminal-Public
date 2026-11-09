import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from shared.clickhouse import ClickHouseStorage

logger = logging.getLogger("terminal-observer-evaluator")

class QualityEvaluator:
    """
    Evaluates data quality rules against ClickHouse layers.
    Focuses on temporal integrity (gap detection) and recency-weighted scoring.
    """

    # Frequency mapping to seconds
    FREQUENCY_MAP = {
        "daily": 86400,
        "hourly": 3600,
        "minutely": 60,
        "monthly": 2592000,  # Approx 30 days
        "weekly": 604800,
        "real-time": 1,
    }

    def __init__(self, storage: ClickHouseStorage):
        self.storage = storage

    def evaluate_asset(self, asset: Dict[str, Any], rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Runs all quality checks for a single asset and returns a summary.
        """
        symbol = asset['symbol']
        library = asset['library']
        frequency = asset.get('frequency', 'daily')
        
        # 1. Edge Scan (Staleness)
        edge_results = self._run_edge_scan(symbol, library, frequency)
        
        # 2. Full Scan (Historical Gaps) - Optional, run once a day ideally
        # For now, we combine them for simplicity in the design
        full_results = self._run_full_scan(symbol, library, frequency)
        
        # 3. Calculate Score
        score = self._calculate_weighted_score(edge_results, full_results)
        
        return {
            "score": score,
            "edge_staleness_seconds": edge_results.get("staleness_seconds", 0),
            "gap_count": full_results.get("gap_count", 0),
            "last_gap_age_days": full_results.get("last_gap_age_days")
        }

    def _run_edge_scan(self, symbol: str, library: str, frequency: str) -> Dict[str, Any]:
        """Checks for the most recent point to detect staleness."""
        table_name = f"{library}_data"
        sql = f"SELECT max(timestamp) as last_ts FROM {table_name} WHERE symbol = %(symbol)s"
        df = self.storage.query_df(sql, parameters={"symbol": symbol})
        
        if df.empty or pd.isnull(df.iloc[0]['last_ts']):
            return {"staleness_seconds": float('inf'), "status": "EMPTY"}
        
        last_ts = df.iloc[0]['last_ts']
        if isinstance(last_ts, str):
            last_ts = pd.to_datetime(last_ts)
            
        staleness = (pd.Timestamp.now() - last_ts.replace(tzinfo=None)).total_seconds()
        return {"staleness_seconds": staleness, "status": "OK", "last_ts": last_ts}

    def _run_full_scan(self, symbol: str, library: str, frequency: str) -> Dict[str, Any]:
        """Identifies historical gaps using ClickHouse neighbor() function."""
        table_name = f"{library}_data"
        interval_seconds = self.FREQUENCY_MAP.get(frequency, 86400)
        multiplier = 1.5 # Default multiplier
        
        # Query to find all gaps larger than multiplier * interval
        # We look at the last 30 days for the "standard" scan
        sql = f"""
        SELECT 
            timestamp,
            neighbor(timestamp, -1) as prev_timestamp,
            timestamp - prev_timestamp as gap_seconds
        FROM (
            SELECT timestamp FROM {table_name} 
            WHERE symbol = %(symbol)s 
            AND timestamp > now() - INTERVAL 30 DAY
            ORDER BY timestamp ASC
        )
        WHERE gap_seconds > %(threshold)s
        """
        threshold = interval_seconds * multiplier
        df = self.storage.query_df(sql, parameters={"symbol": symbol, "threshold": threshold})
        
        if df.empty:
            return {"gap_count": 0, "gaps": []}
            
        # Add age in days for each gap
        now = pd.Timestamp.now()
        df['age_days'] = (now - df['timestamp'].apply(lambda x: pd.to_datetime(x).replace(tzinfo=None))).dt.days
        
        return {
            "gap_count": len(df),
            "gaps": df.to_dict(orient="records"),
            "last_gap_age_days": df['age_days'].min()
        }

    def _calculate_weighted_score(self, edge: Dict[str, Any], full: Dict[str, Any]) -> float:
        """Calculates 0-100 score based on exponential decay penalties."""
        if edge.get("status") == "EMPTY":
            return 0.0
            
        score = 100.0
        
        # 1. Staleness Penalty (Very high weight)
        # If data is stale beyond 2 intervals, start dropping score fast
        # (This is just a heuristic for the MVP)
        staleness = edge.get("staleness_seconds", 0)
        # Use frequency if possible, else default to daily
        # (Hardcoded for now as we don't pass frequency duration here easily)
        if staleness > 172800: # 2 days
            score -= min(40, (staleness / 86400) * 10)

        # 2. Historical Gap Penalty (Exponential decay)
        # Penalty = 10 * exp(-0.1 * age_days)
        for gap in full.get("gaps", []):
            age = gap['age_days']
            penalty = 15 * np.exp(-0.05 * age) # Lasts longer than staleness
            score -= penalty
            
        return max(0.0, min(100.0, score))
