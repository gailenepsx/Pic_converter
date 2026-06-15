To solve this performance bottleneck, we can replace the slow row-by-row `.apply()` function with a **Vectorized Relational Merge**. 

The current method filters the entire 65,000-row dataframe separately for every single alert generated. By using a Pandas `merge` (similar to a SQL JOIN), we can match the transactions to the alerts entirely in C-compiled memory, executing in a fraction of a second instead of several minutes.

Replace the `get_tx_keys` section in **Component 5 (`05_aggregation.py`)** with this highly optimized code block:

```python
        # ---------------------------------------------------------
        # Separately Compute TRANSACTION_KEY list for Alerts (OPTIMIZED)
        # ---------------------------------------------------------
        logger.info("Retrieving Transaction IDs specifically for the generated alerts using vectorized merge...")
        
        if not alerts.empty:
            # 1. Prepare a lightweight subset of the original transactions
            tx_subset = df[['CLIENT_NO', 'VALUE_DATE', 'TRANSACTION_KEY']].copy()
            # Rename to avoid overlap with the alert's VALUE_DATE during the merge
            tx_subset.rename(columns={'VALUE_DATE': 'TX_DATE'}, inplace=True)
            
            # 2. Merge transactions onto alerts based on CLIENT_NO
            # This links all of a client's historical transactions to their triggered alert row
            merged = pd.merge(alerts[['CLIENT_NO', 'VALUE_DATE']], tx_subset, on='CLIENT_NO', how='left')
            
            # 3. Vectorized Filter: Keep only transactions within the specific 14-day rolling window
            d_days_td = pd.Timedelta(days=params['D_DAYS'])
            mask = (merged['TX_DATE'] > (merged['VALUE_DATE'] - d_days_td)) & \
                   (merged['TX_DATE'] <= merged['VALUE_DATE'])
            valid_tx = merged[mask]
            
            # 4. Group by the alert exact date/client and aggregate the valid keys into a list
            tx_lists = valid_tx.groupby(['CLIENT_NO', 'VALUE_DATE'])['TRANSACTION_KEY'].agg(list).reset_index()
            
            # 5. Merge the aggregated lists back into the main alerts dataframe
            alerts = pd.merge(alerts, tx_lists, on=['CLIENT_NO', 'VALUE_DATE'], how='left')
            
            # Ensure any empty matches safely default to an empty list rather than NaN
            alerts['TRANSACTION_KEY'] = alerts['TRANSACTION_KEY'].apply(lambda x: x if isinstance(x, list) else [])
        else:
            alerts['TRANSACTION_KEY'] = []
```

### Why this makes it drastically faster:
*   **No Python `for` loops or `lambda` rows:** The previous method used `lambda row: ...` which forced Pandas to fall back to slow Python iteration. This new method uses native Pandas relational algebra (`pd.merge` and `.groupby().agg()`), which utilizes underlying C and Cython libraries.
*   **Targeted Filtering:** Instead of searching through 65,000 rows for every single alert, it links the IDs (`CLIENT_NO`) instantly, creates a combined matrix, and uses a single vectorized boolean mask to drop any transaction outside of the `D_DAYS` window.
