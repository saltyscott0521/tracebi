"""Pipeline for ``housing_model``: rebuild the warehouse, then its report.

    transform  runs transforms/affordability_transform.py: reads
               inputs/housing_history.csv and sinks data/housing.duckdb
    build      builds every report in reports/housing_model/, each with a receipt

    tracebi run-pipeline housing_model

The CSV is a committed snapshot of public series (Freddie Mac, FHFA, NAR,
Census, BLS). Refreshing it needs the network, so it is a separate, deliberate
step and not part of this pipeline: python inputs/fetch_housing.py
"""

from tracebi import model_pipeline

runner = model_pipeline("housing_model", transform="affordability_transform")
