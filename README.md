This error is a classic **Memory Explosion (Cartesian Product)** caused by the `pd.merge()` operation in the previous optimization. 

Here is exactly what happened: By merging the `alerts` and the `transactions` using only the `CLIENT_NO`, Pandas created every possible combination of a client's alerts and their total transaction history. If a single client had 50 alerts and 5,000 historical transactions, that single merge generated $250,000$ rows in memory. Multiplied across your entire dataset, Pandas tried to build a temporary table with **7.2 billion rows**, which required 54 GiB of RAM, instantly crashing your system.

To achieve maximum speed **without** exploding your memory, we need to use a **Hash-Mapped Dictionary Lookup** instead of a relational merge. This approach groups the transactions into a fast Python dictionary once, and then extracts the keys using a lightning-fast list comprehension.

Replace the `TRANSACTION_KEY` computation block in your **Component 5 (`05_aggregation.py`)** with this memory-safe optimized version:

```python
        # ---------------------------------------------------------
        # Separately Compute TRANSACTION_KEY list for Alerts (MEMORY-OPTIMIZED)
        # ---------------------------------------------------------
        logger.info("Retrieving Transaction IDs for the generated alerts using hash-mapped dictionary...")
        
        if not alerts.empty:
            # 1. Pre-group transactions by CLIENT_NO into a dictionary for O(1) lookups
            # This completely avoids the catastrophic memory explosion of pd.merge
            logger.info("Building client transaction map...")
            
            # Create a combined column of tuples: (VALUE_DATE, TRANSACTION_KEY)
            tx_subset = df[['CLIENT_NO', 'VALUE_DATE', 'TRANSACTION_KEY']].copy()
            tx_subset['TX_TUPLE'] = list(zip(tx_subset['VALUE_DATE'], tx_subset['TRANSACTION_KEY']))
            
            # Group by client and convert to a native Python dictionary
            client_tx_map = tx_subset.groupby('CLIENT_NO')['TX_TUPLE'].apply(list).to_dict()
            
            # 2. Define a high-speed list comprehension lookup
            d_days_td = pd.Timedelta(days=params['D_DAYS'])
            
            def get_tx_keys_fast(client_no, alert_date):
                # Retrieve the client's entire history instantly from the dictionary
                client_history = client_tx_map.get(client_no, [])
                start_date = alert_date - d_days_td
                
                # Filter down to keys strictly within the specific 14-day window
                return [tx_key for tx_date, tx_key in client_history if start_date < tx_date <= alert_date]
            
            # 3. Apply the fast function
            alerts['TRANSACTION_KEY'] = alerts.apply(
                lambda row: get_tx_keys_fast(row['CLIENT_NO'], row['VALUE_DATE']), 
                axis=1
            )
        else:
            alerts['TRANSACTION_KEY'] = []
```

### Why this solves both the Speed and Memory issues:
1. **Zero Memory Explosion:** We are no longer creating duplicate rows. The dictionary (`client_tx_map`) simply stores references to the existing data, taking almost zero extra memory.
2. **Lightning Fast:** Instead of Pandas searching through 65,000 rows for every single alert (which caused your original slow down), the `.get(client_no)` instantly retrieves only that specific client's history in `O(1)` time. The list comprehension then iterates over just a handful of records to apply the 14-day date filter.
