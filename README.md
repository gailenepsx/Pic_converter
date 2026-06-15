To enrich your **Alerts CSV** (`RND_alerts.csv`), we can expand the extracted columns to include the `VALUE_DATE` (which acts as the trigger/observation date for the alert) along with other crucial compliance metadata such as the **Rule ID**, **Alert Type**, **Rule Name**, and the **Total Score**. 

By adding these fields, every single hit transaction row will now have the complete context of the alert it belongs to, making it much easier for an investigator to review.

Here is the updated **Component 7 (`07_output.py`)** script with the enhanced Alerts file:

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
    
    # Define output directory
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
        logger.info("Formatting the Alerts file (Hit Transactions) with enhanced fields...")
        
        # Append official model identifiers to contextualize the hit transactions
        df['Rule_Id'] = 'BNP-RND-EFT-ALL-A-S14-SST'
        df['Alert_Type'] = '10001 [Account Suspicious Activity]'
        df['Rule_Name'] = 'Round Amount Activity'
        
        # Enhanced fields for the Alerts file
        alerts_columns = [
            'ALERT_ID', 
            'Rule_Id',
            'Alert_Type',
            'Rule_Name',
            'CLIENT_NO', 
            'ACC_KEY', 
            'VALUE_DATE', 
            'TOTAL_SCORE',
            'TRANSACTION_KEY'
        ]
        alerts_file = df[alerts_columns].copy()
        
        # Explode the list so each specific hit transaction gets its own row
        alerts_file = alerts_file.explode('TRANSACTION_KEY').dropna(subset=['TRANSACTION_KEY'])
        
        # Rename columns to be more business-friendly for investigators
        alerts_file.rename(columns={
            'CLIENT_NO': 'Party_ID',
            'ACC_KEY': 'Account_ID',
            'VALUE_DATE': 'Alert_Observation_Date',
            'TRANSACTION_KEY': 'Hit_Transaction_ID'
        }, inplace=True)
        
        # =========================================================
        # STEP 2: Audit Trail CSV (Detailed Scoring & Config)
        # =========================================================
        logger.info("Formatting the Audit Trail file (Scoring Results)...")
        audit_trail_file = df.copy()
        
        # Retrieve the configuration parameters used during this run.
        # Fallback to model specification default values if missing from config
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

### What was enhanced:
1.  **Model Metadata Injected:** We mapped the exact rule values from the specifications [1] (`Rule_Id: BNP-RND-EFT-ALL-A-S14-SST`, `Alert_Type: 10001 [Account Suspicious Activity]`, `Rule_Name: Round Amount Activity`) so that every exploded transaction row clearly belongs to the RND model parameters.
2.  **Added Contextual Fields:** Your `RND_alerts.csv` will now display the `VALUE_DATE` (renamed to `Alert_Observation_Date` for clarity) and `TOTAL_SCORE` next to each specific `Hit_Transaction_ID`. This explicitly bridges the overall alert data with the micro-transaction data.
