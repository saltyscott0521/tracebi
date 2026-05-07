"""Google BigQuery connector."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from tracebi.connectors.base import BaseConnector


class BigQueryConnector(BaseConnector):
    """
    Load tables from Google BigQuery.

    Requires: pip install google-cloud-bigquery db-dtypes

    Usage:
        connector = BigQueryConnector(
            "bq",
            project="my-project",
            dataset="analytics",
        )
        model.add_connector(connector)
        model.add_table("events", connector="bq", source="events")

    Args:
        name:        Logical name used to reference this connector in a DataModel.
        project:     GCP project ID.
        dataset:     BigQuery dataset name.
        credentials: Optional google.oauth2.credentials.Credentials object.
                     Uses Application Default Credentials when omitted.
    """

    def __init__(
        self,
        name: str,
        project: str,
        dataset: str,
        credentials=None,
    ) -> None:
        super().__init__(name)
        self.project = project
        self.dataset = dataset
        self.credentials = credentials
        self._client = None

    def connect(self) -> None:
        try:
            from google.cloud import bigquery
        except ImportError:
            raise ImportError(
                "google-cloud-bigquery is required for BigQueryConnector.\n"
                "Install with: pip install google-cloud-bigquery db-dtypes"
            )
        self._client = bigquery.Client(
            project=self.project,
            credentials=self.credentials,
        )

    def load(self, source: str) -> pd.DataFrame:
        if self._client is None:
            self.connect()
        from google.cloud import bigquery

        if source.strip().upper().startswith("SELECT"):
            query = source
        else:
            query = f"SELECT * FROM `{self.project}.{self.dataset}.{source}`"

        return self._client.query(query).to_dataframe()
