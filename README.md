The error you encountered happens because newer versions of Pandas strictly enforce numeric operations within the `.rolling().agg()` method. Passing a lambda function to generate a list of strings (`TRANSACTION_KEY`) causes the aggregator to fail with the `must be real number, not list` exception.

=IF(OR(LOWER(A2)="individual",LOWER(A2)="business"),A2,IF(OR(LOWER(B2)="individual",LOWER(B2)="business"),B2,IF(OR(LOWER(D2)="individual",LOWER(D2)="business"),D2,"")))

To fix this efficiently, we must separate the string aggregation from the numeric rolling calculations. A highly optimized way to do this is to perform the numeric `.rolling()` first, filter down to the alerts that breach the threshold, and *then* look up the `TRANSACTION_KEY` list strictly for those specific alert periods. This prevents Pandas from trying to concatenate lists millions of times in the rolling window.

Here is the corrected **Component 5 (`05_aggregation.py`)**:

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
        df['ROUND_VOLUME'] = df['IS_ROUND'] * df['MAIN_CURRENCY_AMT']
        
        # ---------------------------------------------------------
        # Rolling Window Aggregation (Numeric Metrics Only)
        # ---------------------------------------------------------
        logger.info("Executing numeric rolling window aggregation per CLIENT_NO...")
        
        # Set index to VALUE_DATE for pandas rolling operations
        df_indexed = df.set_index('VALUE_DATE')
        
        # Group by Party (CLIENT_NO) and apply rolling window of D_DAYS
        grouped = df_indexed.groupby('CLIENT_NO')
        
        # Calculate ONLY numeric metrics to prevent Pandas "must be real number" errors
        rolling_stats = grouped.rolling(f"{params['D_DAYS']}D").agg({
            'IS_ROUND': 'sum',                 # SCALE 1: Number of Occurrences
            'ROUND_VOLUME': 'sum',             # SCALE 2: Total Round Amount Value
            'MAIN_CURRENCY_AMT': 'sum'         # Total Volume (Used for SCALE 3 Ratio calculation)
        }).reset_index()
        
        # Rename columns for semantic clarity
        rolling_stats.rename(columns={
            'IS_ROUND': 'OCCURRENCES', 
            'MAIN_CURRENCY_AMT': 'TOTAL_VOLUME'
        }, inplace=True)
        
        # Calculate SCALE 3 Ratio
        rolling_stats['RATIO'] = (rolling_stats['ROUND_VOLUME'] / rolling_stats['TOTAL_VOLUME']).fillna(0)
        
        # ---------------------------------------------------------
        # Apply Model Threshold Filters
        # ---------------------------------------------------------
        # Filter 1: Recurrence >= MIN_OCCURRENCES over D Days
        alerts = rolling_stats[rolling_stats['OCCURRENCES'] >= params['MIN_OCCURRENCES']].copy()
        logger.info(f"Found {len(alerts)} instances breaching the Recurrence threshold (>= {params['MIN_OCCURRENCES']}).")
        
        # ---------------------------------------------------------
        # Separately Compute TRANSACTION_KEY list for Alerts
        # ---------------------------------------------------------
        logger.info("Retrieving Transaction IDs specifically for the generated alerts...")
        
        def get_tx_keys(row, source_df, d_days):
            end_date = row['VALUE_DATE']
            # Pandas rolling D calculates exactly > (end_date - D) and <= end_date
            start_date = end_date - pd.Timedelta(days=d_days)
            
            # Filter the source dataframe for the current client within their specific 14-day window
            mask = (
                (source_df['CLIENT_NO'] == row['CLIENT_NO']) &
                (source_df['VALUE_DATE'] > start_date) &
                (source_df['VALUE_DATE'] <= end_date)
            )
            return source_df.loc[mask, 'TRANSACTION_KEY'].tolist()

        # Apply the helper function only to the filtered alerts to save immense processing time
        if not alerts.empty:
            alerts['TRANSACTION_KEY'] = alerts.apply(
                lambda row: get_tx_keys(row, df, params['D_DAYS']), axis=1
            )
        else:
            alerts['TRANSACTION_KEY'] = []
            
        # ---------------------------------------------------------
        # Test Date Range Filter
        # ---------------------------------------------------------
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
