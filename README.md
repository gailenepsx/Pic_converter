Here is the updated **Component 1 (`01_ingestion.py`)** script. 

I have implemented all three of your requested adjustments:
1.  **Empty DataFrame Check:** The script now checks `if not df_temp.empty:` before appending to `df_list`. I also added a safeguard to exit gracefully if all read files happen to be empty.
2.  **Regex Update:** The regex for the date extraction now uses `r'CM_' + re.escape(target_bu) + r'_PAYMENTS_V8_(\d{8})\.csv'` to safely match the exact BU string.
3.  **Simplified Whitelist Ingestion:** Removed the sorting logic. Since there is only one file per BU, it directly assigns `wl_path = wl_files`.

### Updated Component 1 (`01_ingestion.py`)

```python
import pandas as pd
import os
import glob
import re
import sys
from utils import load_config, get_logger

logger = get_logger("01_Ingestion")

def run():
    config = load_config()
    raw_dir = config['paths']['raw_dir']
    pq_dir = config['paths']['parquet_dir']
    
    data_start = config['date_ranges']['data_start_date']
    data_end = config['date_ranges']['data_end_date']
    target_bu = config['execution_scope']['target_BU']
    
    os.makedirs(pq_dir, exist_ok=True)

    try:
        logger.info(f"Starting Data Ingestion for BU: {target_bu}. Data range: {data_start} to {data_end}")
        
        # ==========================================
        # 1. INGEST PAYMENTS (CSV)
        # ==========================================
        search_pattern = os.path.join(raw_dir, "*", "V8", target_bu, "Payments", f"CM_{target_bu}_PAYMENTS_V8_*.csv")
        all_files = glob.glob(search_pattern)
        
        valid_files = []
        # Adjusted regex using re.escape as requested
        regex_pattern = r'CM_' + re.escape(target_bu) + r'_PAYMENTS_V8_(\d{8})\.csv'
        
        for file_path in all_files:
            filename = os.path.basename(file_path)
            match = re.search(regex_pattern, filename)
            
            if match:
                file_date = match.group(1)
                # Filter files based on the requested Data Date Range
                if data_start <= file_date <= data_end:
                    valid_files.append(file_path)
        
        if not valid_files:
            logger.error(f"No CSV payment files found for BU {target_bu} in range ({data_start} to {data_end}).")
            sys.exit(1)
            
        logger.info(f"Found {len(valid_files)} payment files to ingest.")
        
        csv_columns = [
            "TRANSACTION_KEY", "CLIENTNUM", "CLIENT_NAME", "ACCOUNT_POPULATION_GROUP",
            "PARTY_POPULATION_GROUP", "ACCOUNT_KEY", "TRANS_TYPE_CD", "TRANSACTION_TYPE_DESC",
            "DIRECTION", "TRANS_INSERT_DATE", "TRANS_VALUE_DATE", "CONVERTED_AMT",
            "ORIGINAL_AMOUNT", "ORIGINAL_CURR_CODE", "OPP_COUNTRY_CD", "PAY_OPP_ACCT_KEY", "BU"
        ]
        
        dtypes = {
            'TRANSACTION_KEY': 'string',
            'CLIENTNUM': 'string',
            'CLIENT_NAME': 'string',
            'ACCOUNT_POPULATION_GROUP': 'category',
            'PARTY_POPULATION_GROUP': 'category',
            'ACCOUNT_KEY': 'string',
            'TRANS_TYPE_CD': 'category',
            'TRANSACTION_TYPE_DESC': 'category',
            'DIRECTION': 'category',
            'ORIGINAL_CURR_CODE': 'category',
            'OPP_COUNTRY_CD': 'category',
            'PAY_OPP_ACCT_KEY': 'string',
            'BU': 'category'
        }
        
        # Iteratively load and concatenate using the ';' separator, avoiding empty dataframes
        df_list = []
        for file in valid_files:
            logger.info(f"Reading: {os.path.basename(file)}")
            df_temp = pd.read_csv(file, usecols=csv_columns, dtype=dtypes, sep=';')
            
            if not df_temp.empty:
                df_list.append(df_temp)
            else:
                logger.warning(f"File {os.path.basename(file)} is empty. Skipping.")
        
        if not df_list:
            logger.error("All valid files read were empty. Stopping ingestion.")
            sys.exit(1)
            
        df_tx = pd.concat(df_list, ignore_index=True)
        logger.info(f"Concatenated {len(df_tx)} total transactions.")
        
        # Map to the standardized Parquet data bus schema
        rename_mapping = {
            "CLIENTNUM": "CLIENT_NO",
            "TRANS_TYPE_CD": "APP_TRANSACTION_TYPE",
            "ORIGINAL_AMOUNT": "ORIG_CURRENCY_AMT",
            "ORIGINAL_CURR_CODE": "ORIG_CURRENCY_CD",
            "CONVERTED_AMT": "MAIN_CURRENCY_AMT",
            "ACCOUNT_KEY": "ACC_KEY",
            "PAY_OPP_ACCT_KEY": "OPP_ACCOUNT_KEY"
        }
        df_tx.rename(columns=rename_mapping, inplace=True)
        
        df_tx['VALUE_DATE'] = pd.to_datetime(df_tx['TRANS_VALUE_DATE'])
        df_tx['ORIG_CURRENCY_AMT'] = df_tx['ORIG_CURRENCY_AMT'].astype(float)
        df_tx['MAIN_CURRENCY_AMT'] = df_tx['MAIN_CURRENCY_AMT'].astype(float)
        
        df_tx.to_parquet(os.path.join(pq_dir, "transactions.parquet"), engine='pyarrow')
        logger.info("Serialized all transactions to transactions.parquet successfully.")

        # ==========================================
        # 2. INGEST WHITELISTS (XLSX)
        # ==========================================
        wl_pattern = os.path.join(raw_dir, f"CIB ITO FS - SAM8R {target_bu} RAW Parameters - *.xlsx")
        wl_files = glob.glob(wl_pattern)
        
        if wl_files:
            # Simply take the first matching file since there is only 1 whitelist per BU
            wl_path = wl_files
            logger.info(f"Found Whitelist file: {os.path.basename(wl_path)}")
            
            wl_columns = ["LIST_ID", "ENTITY_KEY", "ENTITY_KEY2"]
            df_wl = pd.read_excel(wl_path, sheet_name="Lists", usecols=wl_columns, engine='openpyxl')
            
            wl_rename_mapping = {
                "LIST_ID": "LIST_TYPE",
                "ENTITY_KEY": "ID",         
                "ENTITY_KEY2": "ACC_B"      
            }
            df_wl.rename(columns=wl_rename_mapping, inplace=True)
            
            if "ID" in df_wl.columns:
                df_wl['ACC_A'] = df_wl['ID']
            
            df_wl.to_parquet(os.path.join(pq_dir, "whitelists.parquet"), engine='pyarrow')
            logger.info("Whitelist serialized successfully to Parquet.")
        else:
            logger.warning(f"No Whitelist file found matching pattern for BU {target_bu}. Exceptions filtering will fail or be bypassed.")
        
        logger.info("Data Ingestion component completed successfully.")
        
    except Exception as e:
        logger.error(f"Failed during ingestion: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    run()
```
