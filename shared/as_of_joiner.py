import duckdb
import pandas as pd
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class AsOfJoiner:
    """
    Performs point-in-time joins using DuckDB's ASOF JOIN.
    
    This joiner ensures that for every record in the 'left' dataframe, 
    we find the most recent record from the 'right' dataframes that 
    occurred at or before the left record's timestamp.
    """
    
    def __init__(self):
        # Use an in-memory DuckDB connection for high-speed processing
        self.con = duckdb.connect(database=':memory:')

    def join(
        self, 
        left_df: pd.DataFrame, 
        right_dfs: Dict[str, pd.DataFrame], 
        on: str = "timestamp", 
        by: str = "symbol",
        validate: bool = True
    ) -> pd.DataFrame:
        """
        Joins multiple dataframes to the left_df using ASOF JOIN.
        
        Args:
            left_df: The primary dataframe (the 'spine' of the join).
            right_dfs: A dictionary mapping suffix/table name to the dataframe to be joined.
            on: The temporal column to join on (must be present in all DFs).
            by: The categorical column to group by (e.g., 'symbol' or 'ticker').
            validate: Whether to check for required columns before joining.
        
        Returns:
            A pandas DataFrame containing the results of the ASOF join.
        """
        if left_df.empty:
            return left_df

        # Ensure timestamp columns are in correct format for DuckDB
        left_df = left_df.copy()
        if not pd.api.types.is_datetime64_any_dtype(left_df[on]):
            left_df[on] = pd.to_datetime(left_df[on])

        # Register the base table
        self.con.register('base_table', left_df)
        
        current_table_name = 'base_table'
        
        for name, df in right_dfs.items():
            if df.empty:
                logger.warning(f"Skipping empty dataframe for join: {name}")
                continue
                
            # Prepare the right dataframe
            df = df.copy()
            if not pd.api.types.is_datetime64_any_dtype(df[on]):
                df[on] = pd.to_datetime(df[on])
                
            table_name = f"table_{name}"
            self.con.register(table_name, df)
            
            # Construct the ASOF JOIN query
            # We exclude 'on' and 'by' from the right table to avoid duplicate columns
            query = f"""
                SELECT 
                    base.*, 
                    join_target.* EXCLUDE ({on}, {by})
                FROM {current_table_name} AS base
                ASOF LEFT JOIN {table_name} AS join_target
                ON base.{on} >= join_target.{on}
                AND base.{by} = join_target.{by}
            """
            
            try:
                # Execute join and update the 'base' for the next iteration
                result_df = self.con.execute(query).df()
                current_table_name = f"result_{name}"
                self.con.register(current_table_name, result_df)
            except Exception as e:
                logger.error(f"Failed to join {name}: {str(e)}")
                raise

        return self.con.execute(f"SELECT * FROM {current_table_name}").df()

    def __del__(self):
        try:
            self.con.close()
        except:
            pass
