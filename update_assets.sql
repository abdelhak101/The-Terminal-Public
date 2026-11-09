UPDATE assets SET metadata = '{"target_table": "silver_market_ohlcv"}'::jsonb WHERE library = 'silver' AND symbol LIKE 'yahoo%';
UPDATE assets SET metadata = '{"target_table": "silver_macro_timeseries"}'::jsonb WHERE library = 'silver' AND (symbol LIKE 'fred%' OR symbol LIKE 'bls%');
UPDATE assets SET metadata = '{"target_table": "silver_census_demographics"}'::jsonb WHERE library = 'silver' AND symbol LIKE 'census%';
