This memory error happens because your test dataset contains highly concentrated data (e.g., thousands of transactions belonging to the exact same `CLIENT_NO` within a few days). 

In our previous script, the Pandas `rolling()` function was executing row-by-row on the exact transaction timestamps. If one client had 65,000 transactions, the script attempted to create 65,000 individual 14-day rolling windows. When it tried to attach the list of `TRANSACTION_KEY`s to each of those overlapping windows, it created lists inside of lists storing billions of strings, instantly maxing out your RAM.

**The Architectural Fix: "Daily Activity" Evaluation**
If we look at the official BNP-RND Model Specifications **[1]**, the model's **Evaluation Trigger** is explicitly defined as **"Daily Activity"**. This means the model is not supposed to trigger a rolling calculation at the exact millisecond of every transaction; it aggregates the volume at the end of the day, and checks the 14-day window *once per client, per day*.

By grouping the transactions by Day *before* doing the rolling window, we compress the data from 65,000 rows down to just a few rows per client. This perfectly matches the business rule and reduces RAM usage to almost zero.

Here is the completely memory-safe, architecturally accurate version of **Component 5 (`05_aggregation.py`)**:

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
        
        if not os.path.exists(tx_path):
            logger.error(f"Critical Error: {tx_path} not found. Ensure Component 04 ran successfully.")
            sys.exit(1)
            
        df = pd.read_parquet(tx_path)
        
        if df.empty:
            logger.warning("Input flagged dataset is empty. Generating empty aggregated alerts.")
            pd.DataFrame().to_parquet(os.path.join(pq_dir, "aggregated_alerts.parquet"), engine='pyarrow')
            return
            
        # =========================================================
        # STEP 1: Normalize to "Daily Activity" Evaluation Trigger
        # =========================================================
        # Remove timestamps to evaluate strictly at the daily level
        df['VALUE_DATE'] = pd.to_datetime(df['VALUE_DATE']).dt.normalize()
        df['ROUND_VOLUME'] = df['IS_ROUND'] * df['MAIN_CURRENCY_AMT']
        
        logger.info("Aggregating transactions to a Daily level per client...")
        
        # Group by Client and Day FIRST to eliminate memory explosion
        daily_df = df.groupby(['CLIENT_NO', 'VALUE_DATE']).agg({
            'IS_ROUND': 'sum',
            'ROUND_VOLUME': 'sum',
            'MAIN_CURRENCY_AMT': 'sum',
            'TRANSACTION_KEY': list # Group keys into daily lists safely
        }).reset_index()
        
        daily_df.rename(columns={
            'IS_ROUND': 'DAILY_OCCURRENCES',
            'ROUND_VOLUME': 'DAILY_ROUND_VOLUME',
            'MAIN_CURRENCY_AMT': 'DAILY_TOTAL_VOLUME',
            'TRANSACTION_KEY': 'DAILY_TX_KEYS'
        }, inplace=True)
        
        # =========================================================
        # STEP 2: Rolling 14-Day Window on Daily Aggregations
        # =========================================================
        logger.info("Executing 14-Day Rolling Evaluation...")
        
        daily_df = daily_df.sort_values('VALUE_DATE')
        daily_indexed = daily_df.set_index('VALUE_DATE')
        grouped = daily_indexed.groupby('CLIENT_NO')
        
        # Now the rolling window processes a maximum of 1 row per day, per client
        rolling_stats = grouped.rolling(f"{params['D_DAYS']}D").agg({
            'DAILY_OCCURRENCES': 'sum',                 
            'DAILY_ROUND_VOLUME': 'sum',             
            'DAILY_TOTAL_VOLUME': 'sum'         
        }).reset_index()
        
        rolling_stats.rename(columns={
            'DAILY_OCCURRENCES': 'OCCURRENCES', 
            'DAILY_TOTAL_VOLUME': 'TOTAL_VOLUME',
            'DAILY_ROUND_VOLUME': 'ROUND_VOLUME'
        }, inplace=True)
        
        rolling_stats['RATIO'] = (rolling_stats['ROUND_VOLUME'] / rolling_stats['TOTAL_VOLUME']).fillna(0)
        
        # Filter 1: Breaches Recurrence Threshold
        alerts = rolling_stats[rolling_stats['OCCURRENCES'] >= params['MIN_OCCURRENCES']].copy()
        
        # =========================================================
        # STEP 3: Safely Stitch Transaction IDs to valid Alerts
        # =========================================================
        logger.info("Retrieving Transaction IDs for the generated alerts...")
        
        if not alerts.empty:
            # Create a lightweight lookup dictionary of the daily lists
            daily_tx_map = daily_df.groupby('CLIENT_NO')[['VALUE_DATE', 'DAILY_TX_KEYS']].apply(
                lambda x: list(zip(x['VALUE_DATE'], x['DAILY_TX_KEYS']))
            ).to_dict()
            
            d_days_td = pd.Timedelta(days=params['D_DAYS'])
            
            def get_14d_keys(client_no, alert_date):
                client_history = daily_tx_map.get(client_no, [])
                start_date = alert_date - d_days_td
                keys = []
                # Append all daily lists that fall within the specific 14-day window
                for tx_date, daily_keys in client_history:
                    if start_date < tx_date <= alert_date:
                        keys.extend(daily_keys)
                return keys
            
            alerts['TRANSACTION_KEY'] = alerts.apply(
                lambda row: get_14d_keys(row['CLIENT_NO'], row['VALUE_DATE']), 
                axis=1
            )
        else:
            alerts['TRANSACTION_KEY'] = []
            
        # =========================================================
        # STEP 4: Output Generation & Test Scope Filtering
        # =========================================================
        test_start = pd.to_datetime(date_ranges['test_start_date'], format="%Y%m%d")
        test_end = pd.to_datetime(date_ranges['test_end_date'], format="%Y%m%d")
        
        alerts = alerts[(alerts['VALUE_DATE'] >= test_start) & (alerts['VALUE_DATE'] <= test_end)]
        logger.info(f"Filtered down to {len(alerts)} valid alerts executing strictly within the testing window.")
        
        alerts.to_parquet(os.path.join(pq_dir, "aggregated_alerts.parquet"), engine='pyarrow')
        logger.info("Aggregated alerts serialized to aggregated_alerts.parquet successfully.")
        
    except Exception as e:
        logger.error(f"Failed during aggregation: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    run()
```
