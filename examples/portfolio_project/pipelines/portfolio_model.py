"""Pipeline for ``portfolio_model``: rebuild the warehouse, then its reports.

    transform  runs transforms/holdings_transform.py: cleans inputs/holdings.csv
               and sinks the star schema into data/warehouse.duckdb
    build      builds every report in reports/portfolio_model/, each with a receipt

    tracebi run-pipeline portfolio_model
"""

from tracebi import model_pipeline

runner = model_pipeline("portfolio_model", transform="holdings_transform")
