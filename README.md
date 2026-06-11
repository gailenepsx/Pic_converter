Here is the script for **Component 2: Configuration & Thresholds (`02_config_prep.py`)**. 

As we discussed earlier, since the `exchange_rates.csv` file has been removed from the architecture, this script no longer needs to map dynamic currencies or use Pandas. Instead, it serves as a lightweight validation step to execute the business logic formula and compute the global static threshold for the target zeroes [1].

It applies the model's rule: `MAX(Business parameter #105, Business Logic Parameter 80 + Offset)` [1].

### Component 2: Configuration Prep (`02_config_prep.py`)

```python
import os
import json
from utils import load_config, get_logger

logger = get_logger("02_ConfigPrep")

def run():
    config = load_config()
    out_dir = config['paths']['parquet_dir']
    
    try:
        logger.info("Starting Configuration & Threshold Preparation.")
        
        # Extract business logic parameters from config.json
        param_105 = config['model_parameters']['PARAM_105']
        offset = config['model_parameters']['OFFSET']
        param_80 = config['model_parameters']['PARAM_80']
        
        # Calculate static TARGET_ZEROES fallback since dynamic exchange rates are removed.
        # Formula: MAX(Parameter #105, Parameter #80 + Offset)
        target_zeroes = max(param_105, param_80 + offset)
        
        # Prepare the computed threshold data
        threshold_data = {
            "GLOBAL_TARGET_ZEROES": target_zeroes
        }
        
        # Save this computed parameter securely as a JSON file 
        # so it can be picked up by the data bus for Component 04 (Flagging)
        output_path = os.path.join(out_dir, "computed_thresholds.json")
        with open(output_path, 'w') as f:
            json.dump(threshold_data, f)
            
        logger.info(f"Global Target Zeroes computed as: {target_zeroes}")
        logger.info(f"Threshold parameters successfully serialized to {output_path}")
        
    except Exception as e:
        logger.error(f"Failed during configuration prep: {str(e)}", exc_info=True)
        import sys
        sys.exit(1)

if __name__ == "__main__":
    run()
```

### Key Highlights of this Component:
* **Business Logic Enforcement:** It strictly calculates the zeroes based on the parameters mapped in the `config.json` file, enforcing the `PARAM_105` minimum floor rule defined in the Actimize documentation [1, 2].
* **Modular Data Hand-off:** By saving the calculation into `computed_thresholds.json` within the Parquet directory, it safely passes the exact threshold to the downstream `04_round_flagging.py` component without creating tight coupling between the scripts.
* **Error Handling:** Wraps the file generation in a `try...except` block, ensuring that if there are file permission issues in the output directory, the orchestrator is immediately alerted and halts the pipeline before running the heavier math modules.
