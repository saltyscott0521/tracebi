"""AltsVault BDC credit marks: a live, real-data pipeline in the demo app.

Three steps, run from the Refresh page (the ``altsvault`` pipeline):

1. **pull** — download the exports the report needs from the AltsVault API
   (``https://alts-vault.com/api/v1``) as untouched CSVs.
2. **transform** — ordinary pandas that cleans them and sinks a star schema
   into a DuckDB warehouse, then checks the sink contract.
3. **build** — render ``altsvault/credit_marks`` from the model, so the
   Reports page opens the fresh build.

Files live under ``$TRACEBI_ALTSVAULT_DIR`` (default ``data/altsvault`` in the
working directory). The pull needs ``ALTSVAULT_API_KEY``; without it the
pipeline is still listed, and the pull step says what is missing.
"""

import os

DATA_DIR = os.environ.get("TRACEBI_ALTSVAULT_DIR") or os.path.join(
    os.getcwd(), "data", "altsvault")
RAW_DIR = os.path.join(DATA_DIR, "inputs")
WAREHOUSE = os.path.join(DATA_DIR, "warehouse.duckdb")
