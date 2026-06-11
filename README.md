Here are the updated configurations and the **Component 1 (`01_ingestion.py`)** script to reflect your new data constraints. 

To ensure the downstream exceptions module (`03_exceptions.py`) continues to work without needing any rewrites, I have added a column mapping for the whitelist fields (converting `ENTITY_KEY` to `ID` and `ACC_A`, and `ENTITY_KEY2` to `ACC_B`).

### 1. Updated Configuration (`config.json`)
I have added an `execution_scope` object to define the `target_BU`. This parameter will be used dynamically to locate both the correct payments folders and the specific BU whitelist file.

```json
{
    "paths": {
        "raw_dir": "data/raw/",
        "parquet_dir": "data/parquet/",
        "output_dir": "outputs/",
        "log_file": "simulator.log"
    },
    "execution_scope": {
        "target_BU": "SG" 
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
This script now reads only from the `target_BU` directories, uses the `;` separator for the payments CSVs, and uses Pandas' `read_excel` to parse the specific "Lists" sheet from the BU's whitelist `.xlsx` file.

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
    target_bu = config['execution_scope']['target_BU']
    
    os.makedirs(pq_dir, exist_ok=True)

    try:
        logger.info(f"Starting Data Ingestion for BU: {target_bu}. Data range: {data_start} to {data_end}")
        
        # ==========================================
        # 1. INGEST PAYMENTS (CSV)
        # ==========================================
        # Dynamically locate CSV files matching the target BU and directory pattern
        # Pattern: data/raw/[YYYY]/V8/[BU]/Payments/CM_[BU]_PAYMENTS_V8_[YYYYMMDD].csv
        search_pattern = os.path.join(raw_dir, "*", "V8", target_bu, "Payments", f"CM_{target_bu}_PAYMENTS_V8_*.csv")
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
            logger.error(f"No CSV payment files found for BU {target_bu} in range ({data_start} to {data_end}).")
            import sys
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
        
        # Iteratively load and concatenate using the ';' separator
        df_list = []
        for file in valid_files:
            logger.info(f"Reading: {os.path.basename(file)}")
            df_temp = pd.read_csv(file, usecols=csv_columns, dtype=dtypes, sep=';')
            df_list.append(df_temp)
            
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
        # Pattern: CIB ITO FS - SAM8R [BU] RAW Parameters - [YYMMDD].xlsx
        wl_pattern = os.path.join(raw_dir, f"CIB ITO FS - SAM8R {target_bu} RAW Parameters - *.xlsx")
        wl_files = glob.glob(wl_pattern)
        
        if wl_files:
            # Sort to ensure we pick the latest one if multiple exist
            wl_files.sort(reverse=True)
            wl_path = wl_files
            logger.info(f"Found Whitelist file: {os.path.basename(wl_path)}")
            
            # Read only the target columns from the "Lists" sheet
            wl_columns = ["LIST_ID", "ENTITY_KEY", "ENTITY_KEY2"]
            df_wl = pd.read_excel(wl_path, sheet_name="Lists", usecols=wl_columns, engine='openpyxl')
            
            # Map columns to the expected Data Bus format for Component 3 (Exceptions)
            wl_rename_mapping = {
                "LIST_ID": "LIST_TYPE",
                "ENTITY_KEY": "ID",         # Primary mapped field for account whitelists
                "ENTITY_KEY2": "ACC_B"      # Opposite account for relations
            }
            df_wl.rename(columns=wl_rename_mapping, inplace=True)
            
            # Duplicate ID into ACC_A so relation whitelist checks in component 3 work flawlessly
            if "ID" in df_wl.columns:
                df_wl['ACC_A'] = df_wl['ID']
            
            df_wl.to_parquet(os.path.join(pq_dir, "whitelists.parquet"), engine='pyarrow')
            logger.info("Whitelist serialized successfully to Parquet.")
        else:
            logger.warning(f"No Whitelist file found matching pattern for BU {target_bu}. Exceptions filtering will fail or be bypassed.")
        
        logger.info("Data Ingestion component completed successfully.")
        
    except Exception as e:
        logger.error(f"Failed during ingestion: {str(e)}", exc_info=True)
        import sys
        sys.exit(1)

if __name__ == "__main__":
    run()
```

**Important Execution Note:**
Because the script now reads `.xlsx` files using Pandas, you must ensure the `openpyxl` engine is installed in your Python environment before running step 01. You can install it via:
```bash
pip install openpyxl
```
