import pandas as pd
from .dsl import Feature, FeatureInput, Transformation
from .models import FeatureMetadata

def calculate_rsi(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """
    Standard RSI calculation.
    Expects a DataFrame with a 'close' column.
    Returns a DataFrame with an 'rsi' column.
    """
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    
    # Avoid division by zero
    rs = gain / loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))
    
    result = df.copy()
    result['rsi'] = rsi
    return result

# Define the RSI-14 Feature using the DSL
rsi_14 = Feature(
    metadata=FeatureMetadata(
        name="RSI-14",
        description="Relative Strength Index with 14-period window",
        owner="quant_team",
        tags=["momentum", "technical_indicator"]
    ),
    inputs=[
        FeatureInput(
            name="base_price",
            source_type="arcticdb",
            source_key="silver",
            columns=["close"]
        )
    ],
    transformation=Transformation(
        name="rsi_calculation",
        logic=calculate_rsi,
        params={"window": 14}
    )
)

def calculate_spread_pct(df: pd.DataFrame) -> pd.DataFrame:
    """Calculates high-low spread as a percentage of close."""
    result = df.copy()
    result['spread_pct'] = (df['high'] - df['low']) / df['close']
    return result

# Define another sample feature: Volatility Spread
volatility_spread = Feature(
    metadata=FeatureMetadata(
        name="VOL_SPREAD",
        description="High-Low spread percentage",
        owner="quant_team",
        tags=["volatility"]
    ),
    inputs=[
        FeatureInput(
            name="ohlc",
            source_type="arcticdb",
            source_key="silver",
            columns=["high", "low", "close"]
        )
    ],
    transformation=Transformation(
        name="spread_calc",
        logic=calculate_spread_pct
    )
)
