Here is the script for **Component 5: Observation & Aggregation (`05_aggregation.py`)**.

This module calculates the sliding 14-day observation window (`D=14`) per client (since the Distribution Level is "Party" [1]). It evaluates if the transactions breach the minimum Recurrence threshold (e.g., $\ge$ 3 occurrences) [2, 3], and calculates the necessary metrics for the three scoring scales [3, 4].

I have also implemented the **Test Date Range filter** here. The system uses the historical data (from `data_start_date`) to accurately build the 14-day rolling window history, but it will only output alerts that actually trigger within your specified `test_start_date` and `test_end_date`.

### Component 5: Aggregation (`05_aggregation.py`)

```python
import pandas as pd
import os
import sys
from utils import load_config, get_logger

logger = get_logger("05_Aggregation")

def run():
    config = load_config()
    pq_dir = config['paths']['parquet_dir']
    params = config['model_parameters']
    date_ranges = config['date_ranges']
    
    try:
        logger.info(f"Starting Observation & Aggregation (D={params['D_DAYS']} Days).")
        tx_path = os.path.join(pq_dir, "flagged_transactions.parquet")
        
        # ---------------------------------------------------------
        # Error Handling: Check if input file exists
        # ---------------------------------------------------------
        if not os.path.exists(tx_path):
            logger.error(f"Critical Error: {tx_path} not found. Ensure Component 04 ran successfully.")
            sys.exit(1)
            
        df = pd.read_parquet(tx_path)
        
        if df.empty:
            logger.warning("Input flagged dataset is empty. Generating empty aggregated alerts.")
            pd.DataFrame().to_parquet(os.path.join(pq_dir, "aggregated_alerts.parquet"), engine='pyarrow')
            return
            
        logger.info(f"Loaded {len(df)} flagged transactions for aggregation.")
        
        # ---------------------------------------------------------
        # Data Preparation
        # ---------------------------------------------------------
        # Ensure VALUE_DATE is datetime and properly sorted for rolling operations
        df['VALUE_DATE'] = pd.to_datetime(df['VALUE_DATE'])
        df = df.sort_values('VALUE_DATE')
        
        # Calculate the round amount volume per transaction
        # Since IS_ROUND is boolean, multiplying it by the volume zeroes out non-round transactions 
        df['ROUND_VOLUME'] = df['IS_ROUND'] * df['MAIN_CURRENCY_AMT']
        
        # ---------------------------------------------------------
        # Rolling Window Aggregation (Distribution Level: Party)
        # ---------------------------------------------------------
        logger.info("Executing rolling window aggregation per CLIENT_NO...")
        
        # Set index to VALUE_DATE for pandas rolling operations
        df_indexed = df.set_index('VALUE_DATE')
        
        # Group by Party (CLIENT_NO) and apply rolling window of D_DAYS
        grouped = df_indexed.groupby('CLIENT_NO')
        
        # Calculate metrics for SCALE 1, SCALE 2, and SCALE 3
        rolling_stats = grouped.rolling(f"{params['D_DAYS']}D").agg({
            'IS_ROUND': 'sum',                 # SCALE 1: Number of Occurrences
            'ROUND_VOLUME': 'sum',             # SCALE 2: Total Round Amount Value
            'MAIN_CURRENCY_AMT': 'sum',        # Total Volume (Used for SCALE 3 Ratio calculation)
            'TRANSACTION_KEY': lambda x: list(x) # Gather transaction IDs for Audit Trail tracking
        }).reset_index()
        
        # Rename columns for semantic clarity
        rolling_stats.rename(columns={
            'IS_ROUND': 'OCCURRENCES', 
            'MAIN_CURRENCY_AMT': 'TOTAL_VOLUME'
        }, inplace=True)
        
        # Calculate SCALE 3 Ratio (Total Round Amount Volume / Total Volume)
        # Fill NaN with 0 to safely handle any potential division by zero
        rolling_stats['RATIO'] = (rolling_stats['ROUND_VOLUME'] / rolling_stats['TOTAL_VOLUME']).fillna(0)
        
        # ---------------------------------------------------------
        # Apply Model Threshold Filters
        # ---------------------------------------------------------
        # Filter 1: Recurrence >= MIN_OCCURRENCES over D Days
        alerts = rolling_stats[rolling_stats['OCCURRENCES'] >= params['MIN_OCCURRENCES']].copy()
        logger.info(f"Found {len(alerts)} instances breaching the Recurrence threshold (>= {params['MIN_OCCURRENCES']}).")
        
        # Filter 2: Execution Scope (Test Date Range)
        # We only output alerts generated within the requested testing window
        test_start = pd.to_datetime(date_ranges['test_start_date'], format="%Y%m%d")
        test_end = pd.to_datetime(date_ranges['test_end_date'], format="%Y%m%d")
        
        alerts = alerts[(alerts['VALUE_DATE'] >= test_start) & (alerts['VALUE_DATE'] <= test_end)]
        logger.info(f"Filtered down to {len(alerts)} alerts executing strictly within the testing window ({test_start.date()} to {test_end.date()}).")
        
        # ---------------------------------------------------------
        # Output Generation
        # ---------------------------------------------------------
        alerts.to_parquet(os.path.join(pq_dir, "aggregated_alerts.parquet"), engine='pyarrow')
        logger.info("Aggregated alerts serialized to aggregated_alerts.parquet successfully.")
        
    except Exception as e:
        logger.error(f"Failed during aggregation: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    run()
```

### Key Technical Enhancements
*   **Vectorized Volume Isolation:** Instead of using slow `.apply()` or `lambda` functions, the code isolates the round volume using simple boolean vectorization (`df['IS_ROUND'] * df['MAIN_CURRENCY_AMT']`). This handles thousands of rows in milliseconds.
*   **Test Date Windowing:** The script leverages the `date_ranges` parameter from `config.json` to filter the *final* alert output. The historical dates prior to `test_start_date` are successfully read to build up the sliding 14-day metrics [1], but are cleanly truncated before the final serialization so you only get test results for the targeted timeframe.
*   **Division by Zero Safety:** Handled ratio calculations dynamically, using `.fillna(0)` to prevent the script from crashing if an edge case results in a blank volume sum [4].
