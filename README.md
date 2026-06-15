To ensure you have a clear, consistent audit trail of how many transactions are moving through the pipeline at each stage, we can enhance the logging right before each component saves its Parquet file. 

Here are the specific lines to update in each of your scripts to explicitly log the count of **treated transactions**.

### 1. Ingestion (`01_ingestion.py`)
Locate the section where the transactions are serialized to Parquet (around line 77) and update the log statement to include `len(df_tx)`:

**Change this:**
```python
        df_tx.to_parquet(os.path.join(pq_dir, "transactions.parquet"), engine='pyarrow')
        logger.info("Serialized all transactions to transactions.parquet successfully.")
```
**To this:**
```python
        df_tx.to_parquet(os.path.join(pq_dir, "transactions.parquet"), engine='pyarrow')
        logger.info(f"Step 01 Ingestion complete: {len(df_tx)} treated transactions serialized to the data bus.")
```

### 2. Exceptions Filtering (`03_exceptions.py`)
Locate the Output Generation section at the end of the script and adjust the final log to clearly state the remaining treated transactions:

**Change this:**
```python
        final_count = len(df_tx)
        logger.info(f"Exception filtering complete. Total removed: {initial_count - final_count}. Remaining: {final_count}.")
        
        df_tx.to_parquet(os.path.join(pq_dir, "filtered_transactions.parquet"), engine='pyarrow')
        logger.info("Saved clean data to filtered_transactions.parquet successfully.")
```
**To this:**
```python
        final_count = len(df_tx)
        df_tx.to_parquet(os.path.join(pq_dir, "filtered_transactions.parquet"), engine='pyarrow')
        logger.info(f"Step 03 Exceptions complete. Total removed: {initial_count - final_count}. Total treated transactions remaining: {final_count}.")
```

### 3. Round Amount Flagging (`04_round_flagging.py`)
Locate the final serialization step at the bottom of the script. We will add a summary log that recaps the total number of eligible treated transactions being passed to the aggregator:

**Change this:**
```python
        # Serialize to data bus
        df.to_parquet(os.path.join(pq_dir, "flagged_transactions.parquet"), engine='pyarrow')
        logger.info("Flagged dataset serialized to flagged_transactions.parquet.")
```
**To this:**
```python
        # Serialize to data bus
        df.to_parquet(os.path.join(pq_dir, "flagged_transactions.parquet"), engine='pyarrow')
        logger.info(f"Step 04 Flagging complete. Total treated transactions evaluated and serialized: {len(df)}.")
```

### 4. Aggregation (`05_aggregation.py`)
At the very end of the script, update the final log to reflect both the number of historical transactions treated during this step and the final number of alerts generated:

**Change this:**
```python
        alerts.to_parquet(os.path.join(pq_dir, "aggregated_alerts.parquet"), engine='pyarrow')
        logger.info("Aggregated alerts serialized to aggregated_alerts.parquet successfully.")
```
**To this:**
```python
        alerts.to_parquet(os.path.join(pq_dir, "aggregated_alerts.parquet"), engine='pyarrow')
        logger.info(f"Step 05 Aggregation complete. Processed {len(df)} treated transactions, resulting in {len(alerts)} final alerts generated.")
```

*(Note: Step 02, the Configuration Prep script, does not process transactions directly as it only computes the mathematical zeroes thresholds based on the Business Logic Parameters, so no transaction count logging is required there).*
