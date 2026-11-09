from shared.clickhouse import ClickHouseStorage

def test_get_db_symbol_dotted_market_tickers():
    storage = ClickHouseStorage()
    
    # Dotted Yahoo tickers
    assert storage._get_db_symbol("silver_market_ohlcv", "yahoo.dx-y.nyb_main_1d_e92df") == "DX-Y.NYB"
    assert storage._get_db_symbol("silver_market_ohlcv", "yahoo.brk.a_main_1d_e92df") == "BRK.A"
    assert storage._get_db_symbol("silver_market_ohlcv", "yahoo.bf.b_main_1d_e92df") == "BF.B"
    
    # Standard and index tickers
    assert storage._get_db_symbol("silver_market_ohlcv", "yahoo.aapl_main_1d_e92df") == "AAPL"
    assert storage._get_db_symbol("silver_market_ohlcv", "yahoo.^gspc_main_1d_e92df") == "^GSPC"

def test_get_db_symbol_macro_series():
    storage = ClickHouseStorage()
    
    assert storage._get_db_symbol("silver_macro_timeseries", "fred.cpiaucsl_main_default_6ea8b") == "CPIAUCSL"
    assert storage._get_db_symbol("silver_macro_timeseries", "fred.m2sl_main_default_6ea8b") == "M2SL"
    assert storage._get_db_symbol("silver_macro_timeseries", "moneycontrol.1414914_main_default_aca0a") == "1414914"
    assert storage._get_db_symbol("silver_macro_timeseries", "bls.cuur0000sa0_main_default_6ea8b") == "CUUR0000SA0"

def test_get_db_symbol_census_demographics():
    storage = ClickHouseStorage()
    
    assert storage._get_db_symbol("silver_census_demographics", "census.eits_resconst_apermit_main_default_2739e") == "timeseries/eits/resconst"
    assert storage._get_db_symbol("silver_census_demographics", "census.eits_marts_44000_main_default_2739e") == "timeseries/eits/marts"

def test_get_db_symbol_bronze_and_fallback():
    storage = ClickHouseStorage()
    
    assert storage._get_db_symbol("bronze_raw", "yahoo.dx-y.nyb_main_1d_e92df") == "yahoo.dx-y.nyb_main_1d_e92df"
    assert storage._get_db_symbol("bronze_raw", "fred.cpiaucsl_main_default_6ea8b") == "fred.cpiaucsl_main_default_6ea8b"
    assert storage._get_db_symbol("unknown_table", "some.symbol") == "some.symbol"
