Here is the script for **Component 4: Round Amount Flagging (`04_round_flagging.py`)**. 

This module implements the exact mathematical logic specified by the Actimize BNP-RND model to determine if a transaction is a "round amount" [1, 2]. It incorporates robust error handling, efficiently checks for required input files, and safely manages empty dataframes to prevent pipeline crashes.

### Component 4: Round Amount Flagging (`04_round_flagging.py`)

```python
import pandas as pd
import numpy as np
import os
import sys
import json
from utils import load_config, get_logger

logger = get_logger("04_Flagging")

def vectorize_round_check(amount_series, zeroes, ignore_decimals, ignore_digit_5):
    """
    High-performance vectorization of the Actimize Round Amount Formula.
    Uses mathematical modulo operations to detect trailing zeroes, aligning 
    with the model's 'INT(Amount) NOT 0' and modulo logic.
    """
    # Use absolute amount to handle credits/debits uniformly
    abs_amt = np.abs(amount_series)
    
    # Apply IGNORE DECIMALS rule
    if ignore_decimals == 1:
        abs_amt = np.floor(abs_amt)
        
    # Condition: INT(Amount) NOT 0
    valid_int = np.floor(abs_amt) != 0
    
    # Calculate Modulo against 10^Z
    divisor = 10.0 ** zeroes
    remainder = abs_amt % divisor
    
    # Condition 1: Pure Round (remainder is 0)
    is_round = valid_int & (remainder == 0)
    
    # Condition 2: Apply IGNORE DIGIT 5 rule
    if ignore_digit_5 == 1:
        # e.g., if Z=3, the remainder must be exactly 500
        digit_5_value = 5.0 * (10.0 ** (zeroes - 1))
        is_digit_5_round = valid_int & (remainder == digit_5_value)
        is_round = is_round | is_digit_5_round
        
    return is_round

def run():
    config = load_config()
    pq_dir = config['paths']['parquet_dir']
    params = config['model_parameters']
    
    try:
        logger.info("Starting Round Amount Flagging component.")
        tx_path = os.path.join(pq_dir, "filtered_transactions.parquet")
        threshold_path = os.path.join(pq_dir, "computed_thresholds.json")
        
        # ---------------------------------------------------------
        # Error Handling: Check if inputs exist
        # ---------------------------------------------------------
        if not os.path.exists(tx_path):
            logger.error(f"Critical Error: {tx_path} not found. Ensure Component 03 ran successfully.")
            sys.exit(1)
            
        if not os.path.exists(threshold_path):
            logger.error(f"Critical Error: {threshold_path} not found. Ensure Component 02 ran successfully.")
            sys.exit(1)
            
        # Load data and global thresholds
        df = pd.read_parquet(tx_path)
        with open(threshold_path, 'r') as f:
            target_zeroes = json.load(f)["GLOBAL_TARGET_ZEROES"]
            
        logger.info(f"Loaded {len(df)} transactions. Applying global target zeroes: {target_zeroes}.")
        
        # ---------------------------------------------------------
        # Pre-Filtering based on Model Rules
        # ---------------------------------------------------------
        # Rule (1): Transactions of APP Transaction Type = TRANS TYPE
        initial_count = len(df)
        df = df[df['APP_TRANSACTION_TYPE'] == params['TRANS_TYPE']]
        logger.info(f"Filtered out {initial_count - len(df)} transactions not matching TRANS_TYPE '{params['TRANS_TYPE']}'.")
        
        # Rule (2): Transaction value >= MIN VALUE (Evaluated on Reference Currency / Main Currency)
        current_count = len(df)
        df = df[df['MAIN_CURRENCY_AMT'] >= params['MIN_VALUE_REF']]
        logger.info(f"Filtered out {current_count - len(df)} transactions below MIN_VALUE_REF of {params['MIN_VALUE_REF']}.")
        
        # Early exit if no transactions remain after filtering
        if df.empty:
            logger.warning("No transactions remaining after TRANS_TYPE and MIN_VALUE filters. Generating empty flagged output.")
            df['IS_ROUND'] = False
            df.to_parquet(os.path.join(pq_dir, "flagged_transactions.parquet"), engine='pyarrow')
            return
            
        # ---------------------------------------------------------
        # Actimize Mathematical Flagging Execution
        # ---------------------------------------------------------
        logger.info("Executing mathematical flagging on Original and Main currency amounts...")
        
        # Rule (3) & (4): Transaction value in Original Currency OR Main Currency is round amount
        flag_orig = vectorize_round_check(
            df['ORIG_CURRENCY_AMT'], 
            target_zeroes, 
            params['IGNORE_DECIMALS'], 
            params['IGNORE_DIGIT_5']
        )
        
        flag_main = vectorize_round_check(
            df['MAIN_CURRENCY_AMT'], 
            target_zeroes, 
            params['IGNORE_DECIMALS'], 
            params['IGNORE_DIGIT_5']
        )
        
        # A transaction is round if either the Original OR the Main currency amount meets the criteria
        df['IS_ROUND'] = flag_orig | flag_main
        
        round_count = df['IS_ROUND'].sum()
        logger.info(f"Successfully flagged {round_count} round transactions out of {len(df)} eligible transactions.")
        
        # Serialize to data bus
        df.to_parquet(os.path.join(pq_dir, "flagged_transactions.parquet"), engine='pyarrow')
        logger.info("Flagged dataset serialized to flagged_transactions.parquet.")
        
    except Exception as e:
        logger.error(f"Failed during round amount flagging: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    run()
```

### Key Technical Alignments:
*   **Actimize Logic Implementation:** The `vectorize_round_check` function mathematically replicates the rule formulas presented in the model specifications (`INT(Amount) NOT 0`, extracting trailing zeroes, and handling `IGNORE DECIMALS` and `IGNORE DIGIT 5`) [2].
*   **Dual Currency Evaluation:** Reflecting the model's detection logic, the script tests both the `ORIG_CURRENCY_AMT` and `MAIN_CURRENCY_AMT` using an `OR` condition (`flag_orig | flag_main`) [3].
*   **Threshold Application:** It applies the exact `MIN VALUE` filter specifically against the reference currency (`MAIN_CURRENCY_AMT`) prior to evaluating the mathematical roundness [3, 4].
