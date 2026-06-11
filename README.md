Here are the updated configurations and the **Component 1 (`01_ingestion.py`)** script. 

To handle the nested directory structure and multiple daily files, the script now uses the `glob` and `re` (regex) libraries to dynamically traverse the directories, extract the date from the filenames, and selectively ingest only the files that fall within your defined "data date range".

### 1. Updated Configuration (`config.json`)
I have added a new `"date_ranges"` object. 
*   **`data_start_date` & `data_end_date`**: Used by the ingestion script to determine which CSV files to read. *(Note: The data start date should generally be at least 14 days prior to your test start date to allow the system to build the 14-day rolling window history).*
*   **`test_start_date` & `test_end_date`**: Stored in the config to be used by the downstream Aggregation and Scoring modules to restrict which generated alerts are actually outputted.

```json
{
    "paths": {
        "raw_dir": "data/raw/",
        "parquet_dir": "data/parquet/",
        "output_dir": "outputs/",
        "log_file": "simulator.log"
    },
    "date_ranges": {
        "data_start_date": "20230101",
        "data_end_date": "20230131",
        "test_start_date": "20230115",
        "test_end_date": "20230131"
    },
    "model_parameters": {
        "TRANS_TYPE": "EFT-ALL",
        "MIN_VALUE_REF": 1000.0,
        "PARAM_105": 3,
        "PARAM_80": 3,
        "OFFSET": 0,
        "IGNORE_DECIMALS": 1,
        "IGNORE_DIGIT_5": 1,
        "D_DAYS": 14,
        "MIN_OCCURRENCES": 3
    },
    "scoring_scales": {
        "SCALE_1": [{"min": 10, "score": 80}, {"min": 5, "score": 40}, {"min": 3, "score": 30}],
        "SCALE_2": [{"min": 100000, "score": 80}, {"min": 10000, "score": 30}, {"min": 3000, "score": 10}],
        "SCALE_3": [{"min": 0.50, "score": 30}, {"min": 0.30, "score": 20}, {"min": 0.10, "score": 10}]
    }
}
```

### 2. Component 1: Data Ingestion (`01_ingestion.py`)
This script now traverses `data/raw/[YYYY]/V8/[BU]/Payments/`, parses the `[YYYYMMDD]` from the filename, and concatenates all valid files into a single Parquet data bus.

```python
import pandas as pd
import os
import glob
import re
from utils import load_config, get_logger

logger = get_logger("01_Ingestion")

def run():
    config = load_config()
    raw_dir = config['paths']['raw_dir']
    pq_dir = config['paths']['parquet_dir']
    
    data_start = config['date_ranges']['data_start_date']
    data_end = config['date_ranges']['data_end_date']
    
    os.makedirs(pq_dir, exist_ok=True)

    try:
        logger.info(f"Starting Data Ingestion. Data range: {data_start} to {data_end}")
        
        # 1. Dynamically locate CSV files matching the directory and name pattern
        # Pattern matches: data/raw/[YYYY]/V8/[BU]/Payments/CM_[BU]_PAYMENTS_V8_[YYYYMMDD].csv
        search_pattern = os.path.join(raw_dir, "*", "V8", "*", "Payments", "CM_*_PAYMENTS_V8_*.csv")
        all_files = glob.glob(search_pattern)
        
        valid_files = []
        for file_path in all_files:
            filename = os.path.basename(file_path)
            # Extract the 8-digit date using regex
            match = re.search(r'CM_.*_PAYMENTS_V8_(\d{8})\.csv', filename)
            if match:
                file_date = match.group(1)
                # Filter files based on the requested Data Date Range
                if data_start <= file_date <= data_end:
                    valid_files.append(file_path)
        
        if not valid_files:
            logger.error(f"No CSV files found in the specified date range ({data_start} to {data_end}).")
            import sys
            sys.exit(1)
            
        logger.info(f"Found {len(valid_files)} payment files to ingest.")
        
        # Exact list of columns to read from the input CSVs
        csv_columns = [
            "TRANSACTION_KEY", "CLIENTNUM", "CLIENT_NAME", "ACCOUNT_POPULATION_GROUP",
            "PARTY_POPULATION_GROUP", "ACCOUNT_KEY", "TRANS_TYPE_CD", "TRANSACTION_TYPE_DESC",
            "DIRECTION", "TRANS_INSERT_DATE", "TRANS_VALUE_DATE", "CONVERTED_AMT",
            "ORIGINAL_AMOUNT", "ORIGINAL_CURR_CODE", "OPP_COUNTRY_CD", "PAY_OPP_ACCT_KEY", "BU"
        ]
        
        # Memory-efficient dtypes for high volume processing
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
        
        # 2. Iteratively load and concatenate all valid CSV files
        df_list = []
        for file in valid_files:
            logger.info(f"Reading: {os.path.basename(file)}")
            df_temp = pd.read_csv(file, usecols=csv_columns, dtype=dtypes)
            df_list.append(df_temp)
            
        df_tx = pd.concat(df_list, ignore_index=True)
        logger.info(f"Concatenated {len(df_tx)} total transactions.")
        
        # 3. Map to the standardized Parquet data bus schema
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
        
        # Create standard VALUE_DATE for the 14-day rolling window
        df_tx['VALUE_DATE'] = pd.to_datetime(df_tx['TRANS_VALUE_DATE'])
        
        # Ensure numeric fields are floats for the Actimize math logic
        df_tx['ORIG_CURRENCY_AMT'] = df_tx['ORIG_CURRENCY_AMT'].astype(float)
        df_tx['MAIN_CURRENCY_AMT'] = df_tx['MAIN_CURRENCY_AMT'].astype(float)
        
        # Serialize the unified dataset to Parquet
        df_tx.to_parquet(os.path.join(pq_dir, "transactions.parquet"), engine='pyarrow')
        logger.info("Serialized all transactions to transactions.parquet successfully.")

        # 4. Ingest Whitelists
        wl_path = os.path.join(raw_dir, "whitelists.csv")
        if os.path.exists(wl_path):
            pd.read_csv(wl_path).to_parquet(os.path.join(pq_dir, "whitelists.parquet"))
            logger.info("Whitelists serialized successfully.")
        else:
            logger.warning(f"{wl_path} not found. Exceptions filtering will require this file.")
        
        logger.info("Ingestion completed successfully.")
        
    except Exception as e:
        logger.error(f"Failed during ingestion: {str(e)}", exc_info=True)
        import sys
        sys.exit(1)

if __name__ == "__main__":
    run()
```
