Here is the updated **Component 7 (`07_output.py`)** script. 

Based on your instructions, we have reversed the traditional contents of the two files: your **Alerts CSV** will now contain the itemized list of hit transactions grouped by the Alert ID, and your **Audit Trail CSV** will serve as the detailed scoring matrix containing the actual values, the assigned scales, and the specific configuration parameters (such as `IGNORE_DECIMALS` [1], Parameter `#105` [2], and Parameter `#80` [3]).

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
    params = config['model_parameters']
    
    # Define output directory exactly as requested
    out_dir = './outputs'
    os.makedirs(out_dir, exist_ok=True)
    
    try:
        logger.info("Starting Output Generation component.")
        alerts_path = os.path.join(pq_dir, "scored_alerts.parquet")
        
        # ---------------------------------------------------------
        # Error Handling
        # ---------------------------------------------------------
        if not os.path.exists(alerts_path):
            logger.error(f"Critical Error: {alerts_path} not found. Ensure Component 06 ran successfully.")
            sys.exit(1)
            
        df = pd.read_parquet(alerts_path)
        
        if df.empty:
            logger.warning("No alerts to process. Generating empty output files.")
            pd.DataFrame().to_csv(os.path.join(out_dir, "RND_alerts.csv"), index=False)
            pd.DataFrame().to_csv(os.path.join(out_dir, "RND_audit_trail.csv"), index=False)
            return
            
        logger.info(f"Loaded {len(df)} scored alerts for formatting.")
        
        # Generate a unique ALERT_ID using Client No, Account Key, and Value Date
        df['ALERT_ID'] = 'RND_' + df['CLIENT_NO'].astype(str) + '_' + df['ACC_KEY'].astype(str) + '_' + pd.to_datetime(df['VALUE_DATE']).dt.strftime('%Y%m%d')
        
        # =========================================================
        # STEP 1: Alerts CSV (Itemized Hit Transactions)
        # =========================================================
        logger.info("Formatting the Alerts file (Hit Transactions)...")
        
        alerts_columns = ['ALERT_ID', 'CLIENT_NO', 'ACC_KEY', 'TRANSACTION_KEY']
        alerts_file = df[alerts_columns].copy()
        
        # Explode the list so each specific hit transaction gets its own row
        # This explicitly groups the breached transactions under their unique AlertID
        alerts_file = alerts_file.explode('TRANSACTION_KEY').dropna(subset=['TRANSACTION_KEY'])
        
        # =========================================================
        # STEP 2: Audit Trail CSV (Detailed Scoring & Config)
        # =========================================================
        logger.info("Formatting the Audit Trail file (Scoring Results)...")
        audit_trail_file = df.copy()
        
        # Retrieve the configuration parameters used during this run.
        # Fallback to model specification default values if missing from config.json
        audit_trail_file['IGNORE_DECIMALS'] = params.get('IGNORE_DECIMALS', 1)  
        audit_trail_file['PARAM_105'] = params.get('PARAM_105', 2) 
        audit_trail_file['PARAM_80'] = params.get('PARAM_80', 3)   
        audit_trail_file['TARGET_ZEROES_APPLIED'] = params.get('TARGET_ZEROES', 3)
        
        # Select exactly the columns requested for the Audit Trail
        audit_columns = [
            'ALERT_ID', 
            'ACC_KEY', 
            'CLIENT_NO', 
            'VALUE_DATE', 
            'OCCURRENCES', 'SCORE_SCALE_1',
            'ROUND_VOLUME', 'SCORE_SCALE_2', 
            'RATIO', 'SCORE_SCALE_3',
            'TOTAL_SCORE',
            'IGNORE_DECIMALS', 'PARAM_105', 'PARAM_80', 'TARGET_ZEROES_APPLIED'
        ]
        
        audit_trail_file = audit_trail_file[audit_columns]
        
        # Rename columns to clearly match the requested report headers
        audit_trail_file.rename(columns={
            'ACC_KEY': 'Account_ID',
            'CLIENT_NO': 'Party_ID',
            'VALUE_DATE': 'Observation_Date',
            'OCCURRENCES': 'Actual_Number_of_Occurrences',
            'ROUND_VOLUME': 'Actual_Total_Round_Amount_Value',
            'RATIO': 'Actual_Ratio'
        }, inplace=True)
        
        # =========================================================
        # STEP 3: Export to CSV
        # =========================================================
        alerts_out_path = os.path.join(out_dir, "RND_alerts.csv")
        audit_out_path = os.path.join(out_dir, "RND_audit_trail.csv")
        
        alerts_file.to_csv(alerts_out_path, index=False)
        audit_trail_file.to_csv(audit_out_path, index=False)
        
        logger.info("Output generation complete.")
        logger.info(f"--> Saved {len(alerts_file)} hit transactions to {alerts_out_path}")
        logger.info(f"--> Saved {len(audit_trail_file)} scoring audit results to {audit_out_path}")
        
    except Exception as e:
        logger.error(f"Failed during output generation: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    run()
```

### What changed to meet your requirements:
1. **File Paths & Names:** Both files are now correctly mapped to the `./outputs` folder as `RND_alerts.csv` and `RND_audit_trail.csv`.
2. **Alerts CSV Design:** I used the Pandas `.explode()` function on `TRANSACTION_KEY` to expand the array. This creates a dedicated row for every single hit transaction while keeping them explicitly bound together by the same unique `AlertID`. 
3. **Audit Trail CSV Design:** I built a custom dataframe view that perfectly pairs the *Actual Value* calculated during Step 5 with the *Assigned Score* mapped during Step 6 (e.g., `Actual_Total_Round_Amount_Value` next to `SCORE_SCALE_2`).
4. **Configuration Extraction:** The script pulls the business logic parameters used during the run—like `IGNORE_DECIMALS` [1], `#105` [2], and `#80` [3]—directly from your `params` configuration dictionary and appends them to the audit trail so reviewers can see the exact definition of a "round amount" [1, 2] applied to that specific alert. *(Note: default fallback values of 1, 2, and 3 are coded in to match the documentation defaults if your config file is missing those specific keys [3, 4])* .
