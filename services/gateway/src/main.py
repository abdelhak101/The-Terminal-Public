import os
import json
import redis
import pandas as pd
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query, Body
from shared.registry import MetadataRegistry
from shared.serialization import safe_json_response
from query_engine import QueryEngine
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("research-gateway")

app = FastAPI(title="Research Gateway", version="1.0.0")
registry = MetadataRegistry()
query_engine = QueryEngine()

# Redis client for online features
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    decode_responses=True
)

@app.get("/health")
def health_check():
    """
    Hard Health Check: Verifies ClickHouse connectivity.
    """
    if not query_engine.check_health():
        raise HTTPException(
            status_code=503, 
            detail="Storage layer unreachable (ClickHouse)"
        )
    return {"status": "healthy", "storage": "connected"}

@app.post("/v1/data/query")
def batch_query(
    requests: List[Dict[str, Any]] = Body(..., embed=True),
    start_date: Optional[str] = Body(None),
    end_date: Optional[str] = Body(None),
    columns: Optional[List[str]] = Body(None)
):
    """
    God Query: Retrieve historical data for multiple assets using human-readable params.
    Now powered by ClickHouse.
    """
    try:
        results = query_engine.execute_query(
            requests=requests,
            global_start=start_date,
            global_end=end_date,
            global_columns=columns
        )
        return safe_json_response(results)
    except Exception as e:
        logger.error(f"Batch query failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during data retrieval")

@app.get("/v1/data/{library}/{full_symbol}")
def get_direct_data(
    library: str,
    full_symbol: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    columns: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0)
):
    """
    Direct Access: Retrieve historical data using internal layer and symbol names.
    Bypasses semantic resolution for performance.
    """
    try:
        col_list = columns.split(",") if columns else None
        data = query_engine.read_direct(
            library=library,
            symbol=full_symbol,
            start_date=start_date,
            end_date=end_date,
            columns=col_list,
            limit=limit,
            offset=offset
        )
        return safe_json_response(data)
    except ValueError as e:
        # Library not found
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        # Symbol not found
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Direct data access failed for {library}/{full_symbol}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during data retrieval")

@app.post("/v1/features/retrieve")
def retrieve_features(
    features: List[str] = Body(...),
    symbols: List[str] = Body(...),
    timestamp: str = Body("latest")
):
    """Retrieve features for a set of symbols and an optional timestamp."""
    try:
        if timestamp == "latest":
            # 1. Online Retrieval (Redis)
            results = []
            for symbol in symbols:
                raw_data = redis_client.hget("feature_values", symbol)
                if raw_data:
                    data = json.loads(raw_data)
                    filtered = {k: v for k, v in data.items() if k in features or k == "timestamp"}
                    results.append({"symbol": symbol, "features": filtered})
                else:
                    results.append({"symbol": symbol, "features": {}, "error": "No data found"})
            
            return {"results": results, "source": "redis"}
        else:
            # 2. Offline Retrieval (ClickHouse + AsOfJoiner)
            return {"error": "Historical retrieval not yet implemented in Gateway", "source": "clickhouse"}
            
    except Exception as e:
        logger.error(f"Feature retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/v1/assets/search")
def search_assets(q: str = Query(..., min_length=1)):
    """Search for assets by symbol or description."""
    try:
        results = registry.search_assets(q)
        return {"query": q, "results": results}
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/v1/assets/{symbol}/manifest")
def get_manifest(symbol: str, lineage_id: Optional[int] = None):
    """Retrieve storage manifest and metadata for an asset."""
    try:
        manifest = registry.get_asset_manifest(symbol, lineage_id)
        if not manifest:
            raise HTTPException(status_code=404, detail=f"Asset '{symbol}' not found or no committed lineage")
        
        return manifest
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manifest retrieval failed for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
