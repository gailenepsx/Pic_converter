That is fantastic progress! Reaching 950 valid alerts means the mathematical engine, grouping, and execution scoping are perfectly aligned with your test dataset.

Now, we move to **Component 6: Scoring (`06_scoring.py`)**. 

Based on the BNP-RND model specifications, the final score of an alert is the sum of specific scales [1]. This script mathematically applies the thresholds for **SCALE 1** (Occurrences), **SCALE 2** (Total Round Amount Value), and **SCALE 3** (Ratio), and caps the result at the model's absolute maximum score [1, 2]. 

Here is the highly optimized, vectorized scoring component.

### Component 6: Scoring (`06_scoring.py`)

```python
import pandas as pd
import numpy as np
import os
import sys
from utils import load_config, get_logger

logger = get_logger("06_Scoring")

def run():
    config = load_config()
    pq_dir = config['paths']['parquet_dir']
    
    try:
        logger.info("Starting Alert Scoring component.")
        alerts_path = os.path.join(pq_dir, "aggregated_alerts.parquet")
        
        # ---------------------------------------------------------
        # Error Handling: Check if input file exists
        # ---------------------------------------------------------
        if not os.path.exists(alerts_path):
            logger.error(f"Critical Error: {alerts_path} not found. Ensure Component 05 ran successfully.")
            sys.exit(1)
            
        df = pd.read_parquet(alerts_path)
        
        if df.empty:
            logger.warning("Input alerts dataset is empty. Generating empty scored output.")
            pd.DataFrame().to_parquet(os.path.join(pq_dir, "scored_alerts.parquet"), engine='pyarrow')
            return
            
        logger.info(f"Loaded {len(df)} alerts for scoring evaluation.")
        
        # =========================================================
        # SCALE 1: Number of Occurrences
        # =========================================================
        # 10+ = 80, 5+ = 40, 3+ = 30
        cond_scale_1 = [
            df['OCCURRENCES'] >= 10,
            df['OCCURRENCES'] >= 5,
            df['OCCURRENCES'] >= 3
        ]
        val_scale_1 = 
        df['SCORE_SCALE_1'] = np.select(cond_scale_1, val_scale_1, default=0)
        
        # =========================================================
        # SCALE 2: Total Round Amount Value
        # =========================================================
        # 100,000+ = 80, 10,000+ = 30, 3,000+ = 10
        # (Evaluated against the reference currency proxy)
        cond_scale_2 = [
            df['ROUND_VOLUME'] >= 100000,
            df['ROUND_VOLUME'] >= 10000,
            df['ROUND_VOLUME'] >= 3000
        ]
        val_scale_2 = 
        df['SCORE_SCALE_2'] = np.select(cond_scale_2, val_scale_2, default=0)
        
        # =========================================================
        # SCALE 3: Ratio of Round Amount Volume to Total volume
        # =========================================================
        # 50%+ = 30, 30%+ = 20, 10%+ = 10
        cond_scale_3 = [
            df['RATIO'] >= 0.50,
            df['RATIO'] >= 0.30,
            df['RATIO'] >= 0.10
        ]
        val_scale_3 = 
        df['SCORE_SCALE_3'] = np.select(cond_scale_3, val_scale_3, default=0)
        
        # =========================================================
        # Final Score Aggregation
        # =========================================================
        logger.info("Aggregating base scales into TOTAL_SCORE...")
        
        # Sum the three primary scales
        df['TOTAL_SCORE'] = df['SCORE_SCALE_1'] + df['SCORE_SCALE_2'] + df['SCORE_SCALE_3']
        
        # Enforce Maximum Score ceiling
        MAX_SCORE = 9999
        df['TOTAL_SCORE'] = np.minimum(df['TOTAL_SCORE'], MAX_SCORE)
        
        # ---------------------------------------------------------
        # Output Generation
        # ---------------------------------------------------------
        df.to_parquet(os.path.join(pq_dir, "scored_alerts.parquet"), engine='pyarrow')
        logger.info(f"Step 06 Scoring complete. Successfully evaluated and assigned scores to {len(df)} treated alerts.")
        
    except Exception as e:
        logger.error(f"Failed during alert scoring: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    run()
```

### Key Alignments with Model Specifications:
* **Progressive Thresholds:** I utilized `numpy.select` to build the progressive tiering for all three scales efficiently without looping [2]. If a ratio is `0.35` (35%), it will correctly fall through to the second condition and grant 20 points [2].
* **Euro-Base Scale Mapping:** The specifications note that SCALE 2 is based on threshold values of 3k, 10k, and 100k, and that "scales are in Euro" [2]. By applying these conditions against `ROUND_VOLUME` (which we calculated using `MAIN_CURRENCY_AMT`), the script accurately matches the rule blueprint mapping [1, 3].
* **Maximum Score Enforcement:** Per the model documentation, the absolute maximum score is capped at `9999` [1]. The script uses `np.minimum` to cleanly enforce this ceiling. *(Note: Standard prior alert scales and High Focus Risk Level CVA scores are external metrics. This engine computes the core detection scores)* [1].
