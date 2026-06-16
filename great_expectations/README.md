# Great Expectations — Olist Raw Layer Validation

## Purpose
Detect anomalies in raw source data (`olist_raw`) before dbt transformation.
Documents what needs to be cleaned in dbt staging.

## What it checks
- 44 structural GE expectations across 7 raw tables
- 20 custom business logic anomaly checks covering:
  - Payment anomalies (zero/negative, high value, installments, mismatch)
  - Order / delivery anomalies (missing timestamps, time inversions)
  - Review anomalies (invalid dates, duplicate reviews)
  - Product anomalies (missing weight/dimensions)
  - Seller anomalies (orphan sellers, single-order sellers)
  - Customer anomalies (orphan customers, repeat buyer identification)
  - Geolocation coverage gaps

## How to run
```bash
conda activate m2
cd ~/ELT_olist
python great_expectations/ge_olist_raw.py
```

## Output
Results printed to terminal. To save to file:
```bash
python great_expectations/ge_olist_raw.py 2>/dev/null > ge_raw_report.txt
```

## Notes
- Keyfile path is hardcoded. Update path if running on a different machine.
- See `Module2_Data_Quality_Report.docx` for full analysis of results
