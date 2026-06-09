Here is the drafted **"Transaction Fields"** subsection that you can integrate into Section 6 (Data Dictionary & Field Mappings) of your Technical Specifications Document (TSD). I have mapped each field from your list to its specific purpose within the BNP-RND simulator's logic, based on the model's rules and our established architecture.

***

### 6.3. Transaction Fields (Simulator Input Schema)
To accurately execute the simulation, the ingestion component (`01_ingestion.py`) expects the core transaction input file to contain the following fields. These fields are essential for evaluating thresholds, applying whitelist exceptions, calculating metrics, and generating the audit trail.

*   **`BU` (Business Unit):** Identifies the business unit for the transaction. This is critical for configuration, as setup parameters like `Business Logic Parameter #105` (Minimum zeroes) and the `Offset` are defined per BU [1].
*   **`CLIENT_NO` & `CLIENT_NAME`:** The unique identifier and name of the client/party. These are used during the aggregation phase, as the model's Distribution Level is set to "Party" [2].
*   **`TRANS_VALUE_DATE`:** The execution date of the transaction. This maps to the model's `VALUE DATE` parameter and is the anchor used to establish the rolling 14-day look-back Observation Period for calculating recurrence [3].
*   **`TRANSACTION_KEY`:** A unique identifier for the specific transaction. Used primarily in the Output Generation component to itemize triggered transactions in the Audit Trail.
*   **`CRDS_CODE` & `RMPM_CODE`:** Transaction classification codes used to filter and identify the `APP Transaction Type`. The simulator uses these fields to isolate transactions that match the defined `TRANS TYPE` (e.g., 'EFT-ALL') [3, 4].
*   **`POPULATION_GROUP_ID`:** An identifier grouping the account or client, which can be utilized for specific routing, threshold variations, or applying specific Model White Lists (like BNP-RND-EX-01) [4].
*   **`MAIN_CURRENCY_AMT`:** The transaction value expressed in the main currency. The detection logic explicitly evaluates this field to determine if the transaction is a round amount [3].
*   **`MAIN_CURRENCY_CD`:** The currency code corresponding to the `MAIN_CURRENCY_AMT` [3]. Used to determine the target number of zeroes based on exchange rates [1].
*   **`ACC_KEY`:** The unique identifier for the primary account. This is essential for the "Account" Detection Level [2], tracking total round amount volumes per account, and applying Account White List exceptions [4].
*   **`ACC_CURRENCY`:** The base currency of the account. This is required for calculating the "Total round amount value" used in **SCALE 2**, which must be evaluated in the Account Currency before being mapped to the scoring scale (which is often normalized to EUR) [4, 5].
*   **`POS_SENS_OPE`:** The direction/sense of the operation (e.g., Debit or Credit). Used to determine the flow of funds and to correctly identify the relation direction (A $\rightarrow$ B or B $\rightarrow$ A) for exception handling [4].
*   **`OPP_ACCOUNT_KEY`:** The unique identifier for the opposite/counterparty account. This field is evaluated in tandem with `ACC_KEY` to apply the **Relation White List** (e.g., AML-REL-EX-04), which explicitly excludes specific pairs of account keys from detection [4].

*** 
*Note: You can add this directly under the existing "6.1. Transaction Value & Currency Fields" or "6.2. Threshold Pre-Processing" subsections in the TSD.*
