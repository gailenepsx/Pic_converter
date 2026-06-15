You are absolutely right. A complete AML model simulator must separate the outputs into two distinct deliverables: the **Alerts file** (the summarized alert metadata at the Account/Party level) and the **Audit Trail file** (the itemized list of specific transactions that triggered each alert).

Here is the complete **Component 7 (`07_output.py`)** script. It takes the `scored_alerts.parquet`, generates a unique `ALERT_ID`, tags the official model metadata [1], and then uses the Pandas `.explode()` function to safely expand your list of transactions into a separate, line-by-line Audit Trail.

### Component 7: Output Generation (`07_output.py`)

```python
import pandas as pd
import os
import sys
from utils import load_config, get_logger

logger = get_logger("07_Output")

def run():
    config = load_config()
    pq_dir = config['paths']['parquet_dir']
    
    # Define an output directory for the final CSV files
    # (Defaulting to a 'results' folder in the project root)
    out_dir = config.get('paths', {}).get('output_dir', './results')
    os.makedirs(out_dir, exist_ok=True)
    
    try:
        logger.info("Starting Output Generation component.")
        alerts_path = os.path.join(pq_dir, "scored_alerts.parquet")
        
        # ---------------------------------------------------------
        # Error Handling: Check if input file exists
        # ---------------------------------------------------------
        if not os.path.exists(alerts_path):
            logger.error(f"Critical Error: {alerts_path} not found. Ensure Component 06 ran successfully.")
            sys.exit(1)
            
        df = pd.read_parquet(alerts_path)
        
        if df.empty:
            logger.warning("No alerts to process. Generating empty output files.")
            pd.DataFrame().to_csv(os.path.join(out_dir, "alerts_file.csv"), index=False)
            pd.DataFrame().to_csv(os.path.join(out_dir, "audit_trail_file.csv"), index=False)
            return
            
        logger.info(f"Loaded {len(df)} scored alerts for formatting.")
        
        # =========================================================
        # STEP 1: Model Metadata Enrichment
        # =========================================================
        # Appending the official model identifiers required for routing
        df['Rule_Id'] = 'BNP-RND-EFT-ALL-A-S14-SST'
        df['Alert_Type'] = '10001 [Account Suspicious Activity]'
        df['Rule_Name'] = 'Round Amount Activity'
        
        # Generate a unique ALERT_ID using Client No and the Value Date
        df['ALERT_ID'] = 'RND_' + df['CLIENT_NO'].astype(str) + '_' + pd.to_datetime(df['VALUE_DATE']).dt.strftime('%Y%m%d')
        
        # =========================================================
        # STEP 2: Generate the Alerts File
        # =========================================================
        logger.info("Formatting the Alerts file...")
        
        # Select and order the columns for the summarized alerts view
        alerts_columns = [
            'ALERT_ID', 'CLIENT_NO', 'ACC_KEY', 'VALUE_DATE', 
            'OCCURRENCES', 'ROUND_VOLUME', 'TOTAL_VOLUME', 'RATIO', 
            'SCORE_SCALE_1', 'SCORE_SCALE_2', 'SCORE_SCALE_3', 'TOTAL_SCORE',
            'Rule_Id', 'Alert_Type', 'Rule_Name'
        ]
        alerts_file = df[alerts_columns].copy()
        
        # =========================================================
        # STEP 3: Generate the Audit Trail File
        # =========================================================
        logger.info("Exploding transaction lists to generate the itemized Audit Trail file...")
        
        # Select the key mapping columns
        audit_columns = ['ALERT_ID', 'CLIENT_NO', 'ACC_KEY', 'TRANSACTION_KEY']
        audit_trail_base = df[audit_columns].copy()
        
        # Explode the list of transaction IDs so each transaction gets its own row
        audit_trail_file = audit_trail_base.explode('TRANSACTION_KEY')
        
        # Drop any potential empty rows (if a transaction list was missing)
        audit_trail_file = audit_trail_file.dropna(subset=['TRANSACTION_KEY'])
        
        # =========================================================
        # STEP 4: Export to CSV
        # =========================================================
        alerts_out_path = os.path.join(out_dir, "alerts_file.csv")
        audit_out_path = os.path.join(out_dir, "audit_trail_file.csv")
        
        alerts_file.to_csv(alerts_out_path, index=False)
        audit_trail_file.to_csv(audit_out_path, index=False)
        
        logger.info("Output generation complete.")
        logger.info(f"--> Saved {len(alerts_file)} summary rows to {alerts_out_path}")
        logger.info(f"--> Saved {len(audit_trail_file)} itemized transaction rows to {audit_out_path}")
        
    except Exception as e:
        logger.error(f"Failed during output generation: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    run()
```

### Key Highlights of this Script:
* **The Alerts File (`alerts_file.csv`)** captures exactly what investigators see at the top level: The `ALERT_ID`, the Account/Party involved, the total scores, and the exact Model Metadata specified in the documentation (Rule: `BNP-RND-EFT-ALL-A-S14-SST`, Alert Type: `10001 [Account Suspicious Activity]`) [1]. 
* **The Audit Trail File (`audit_trail_file.csv`)** uses Pandas `.explode('TRANSACTION_KEY')` to take the Python list of historical transaction IDs that we grouped during the 14-day rolling window, and splits them into individual rows. 
* **Relational Traceability:** Both files share the exact same `ALERT_ID`, `CLIENT_NO`, and `ACC_KEY`, allowing you or your stakeholders to perfectly cross-reference an alert's score with the specific transactions that caused it.
