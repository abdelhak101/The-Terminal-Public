import json
import numpy as np
import math
from datetime import datetime
from uuid import UUID
from fastapi.responses import JSONResponse

def clean_nans(obj):
    """
    Recursively replaces NaN, Inf, and -Inf with None in a data structure.
    Also handles conversion of common non-serializable types.
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (datetime, np.datetime64)):
        if isinstance(obj, np.datetime64):
            # Convert numpy datetime to python datetime
            ts = (obj - np.datetime64('1970-01-01T00:00:00')) / np.timedelta64(1, 's')
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: clean_nans(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, np.ndarray)):
        if isinstance(obj, np.ndarray):
            return [clean_nans(x) for x in obj.tolist()]
        return [clean_nans(x) for x in obj]
    return obj

def safe_json_response(content, status_code: int = 200):
    """
    Creates a JSON response with safe encoding for all edge cases (NaN, Inf, etc).
    Uses a pre-processing step to ensure all values are JSON-compliant.
    """
    cleaned_content = clean_nans(content)
    return JSONResponse(content=cleaned_content, status_code=status_code)
