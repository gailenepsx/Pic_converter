Here is the script for **Component 3: Exceptions Filtering (`03_exceptions.py`)**. 

Based on the Actimize model specifications [1], this module explicitly filters out transactions if the account is present in the **Model White List (`BNP-RND-EX-01`)**, an **Account White List**, or if the transaction occurs between two accounts listed in the **Relation White List (`AML-REL-EX-04`)** (evaluating in both directions: A $\rightarrow$ B or B $\rightarrow$ A) [1].

I have incorporated robust error handling, missing file checks, and optimized Pandas boolean masking to ensure high performance.

### Component 3: Exceptions Filtering (`03_exceptions.py`)

```python
import pandas as pd
import os
import sys
from utils import load_config, get_logger

logger = get_logger("03_Exceptions")

def run():
    config = load_config()
    pq_dir = config['paths']['parquet_dir']
    
    try:
        logger.info("Starting Exceptions Filtering.")
        tx_path = os.path.join(pq_dir, "transactions.parquet")
        wl_path = os.path.join(pq_dir, "whitelists.parquet")
        
        # ---------------------------------------------------------
        # Error Handling: Check if input transactions exist
        # ---------------------------------------------------------
        if not os.path.exists(tx_path):
            logger.error(f"Critical Error: Input file not found at {tx_path}. Cannot proceed.")
            sys.exit(1)
            
        df_tx = pd.read_parquet(tx_path)
        initial_count = len(df_tx)
        logger.info(f"Loaded {initial_count} transactions for filtering.")
        
        # ---------------------------------------------------------
        # Error Handling: Check if whitelists exist
        # ---------------------------------------------------------
        if not os.path.exists(wl_path):
            logger.warning(f"Whitelist file not found at {wl_path}. Bypassing exception filtering.")
            # Still save the file so Component 4 can pick it up uninterrupted
            df_tx.to_parquet(os.path.join(pq_dir, "filtered_transactions.parquet"), engine='pyarrow')
            return

        df_wl = pd.read_parquet(wl_path)
        
        # ==========================================
        # 1. ACCOUNT & MODEL WHITELISTS
        # ==========================================
        # Applies Model White List (BNP-RND-EX-01) and generic Account White Lists
        acc_wl_types = ['ACCOUNT_WHITE_LIST', 'ACCOUNT WHITE LIST', 'BNP-RND-EX-01']
        
        # Safely extract IDs, dropping any NaNs to prevent pandas errors
        account_exemptions = df_wl[df_wl['LIST_TYPE'].isin(acc_wl_types)]['ID'].dropna().unique()
        
        if len(account_exemptions) > 0:
            # Vectorized filtering for performance
            df_tx = df_tx[~df_tx['ACC_KEY'].isin(account_exemptions)]
            logger.info(f"Filtered {initial_count - len(df_tx)} transactions due to Account/Model Whitelists.")
        else:
            logger.info("No Account or Model Whitelist exemptions found to apply.")
            
        # ==========================================
        # 2. RELATION WHITELISTS (Bidirectional A -> B or B -> A)
        # ==========================================
        # Applies Relation White List (AML-REL-EX-04)
        rel_whitelist = df_wl[df_wl['LIST_TYPE'] == 'AML-REL-EX-04'].dropna(subset=['ACC_A', 'ACC_B'])
        
        if not rel_whitelist.empty:
            current_count = len(df_tx)
            
            # Create a boolean mask initialized to False
            mask = pd.Series(False, index=df_tx.index)
            
            # Build the condition dynamically for each relation pair
            for _, row in rel_whitelist.iterrows():
                acc_a = row['ACC_A']
                acc_b = row['ACC_B']
                
                # Condition: (ACC_KEY == A & OPP == B) OR (ACC_KEY == B & OPP == A)
                cond = ((df_tx['ACC_KEY'] == acc_a) & (df_tx['OPP_ACCOUNT_KEY'] == acc_b)) | \
                       ((df_tx['ACC_KEY'] == acc_b) & (df_tx['OPP_ACCOUNT_KEY'] == acc_a))
                
                # Update the master mask
                mask = mask | cond
                
            # Filter the dataframe to KEEP transactions where the mask is False (not a relation match)
            df_tx = df_tx[~mask]
            logger.info(f"Filtered {current_count - len(df_tx)} transactions due to Relation Whitelist (AML-REL-EX-04).")
        else:
            logger.info("No Relation Whitelist exemptions found to apply.")

        # ==========================================
        # 3. OUTPUT GENERATION
        # ==========================================
        final_count = len(df_tx)
        logger.info(f"Exception filtering complete. Total removed: {initial_count - final_count}. Remaining: {final_count}.")
        
        df_tx.to_parquet(os.path.join(pq_dir, "filtered_transactions.parquet"), engine='pyarrow')
        logger.info("Saved clean data to filtered_transactions.parquet successfully.")
        
    except Exception as e:
        logger.error(f"Failed during exception filtering: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    run()
```
