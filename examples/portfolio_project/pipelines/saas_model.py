"""Pipeline for ``saas_model``: rebuild the warehouse, then its reports.

    transform  runs transforms/saas_transform.py: cleans inputs/subscriptions.csv
               and sinks the star schema into data/warehouse.duckdb
    build      builds every report in reports/saas_model/, each with a receipt

    tracebi run-pipeline saas_model
"""

from tracebi import model_pipeline

runner = model_pipeline("saas_model", transform="saas_transform")
