"""Snowflake connector."""

from __future__ import annotations

import pandas as pd

from tracebi.connectors.base import BaseConnector


class SnowflakeConnector(BaseConnector):
    """
    Load tables from Snowflake.

    Requires: pip install snowflake-connector-python

    Usage:
        connector = SnowflakeConnector(
            "sf",
            account="myaccount",
            user="myuser",
            password="mypassword",
            warehouse="COMPUTE_WH",
            database="SALES",
            schema="PUBLIC",
        )
        model.add_connector(connector)
        model.add_table("orders", connector="sf", source="ORDERS")

    Args:
        name:      Logical name used to reference this connector in a DataModel.
        account:   Snowflake account identifier.
        user:      Snowflake username.
        password:  Snowflake password.
        warehouse: Virtual warehouse name.
        database:  Database name.
        schema:    Schema name (default ``PUBLIC``).
    """

    def __init__(
        self,
        name: str,
        account: str,
        user: str,
        password: str,
        warehouse: str,
        database: str,
        schema: str = "PUBLIC",
    ) -> None:
        super().__init__(name)
        self.account = account
        self.user = user
        self.password = password
        self.warehouse = warehouse
        self.database = database
        self.schema = schema
        self._conn = None

    def connect(self) -> None:
        try:
            import snowflake.connector
        except ImportError:
            raise ImportError(
                "snowflake-connector-python is required for SnowflakeConnector.\n"
                "Install with: pip install snowflake-connector-python"
            )
        self._conn = snowflake.connector.connect(
            account=self.account,
            user=self.user,
            password=self.password,
            warehouse=self.warehouse,
            database=self.database,
            schema=self.schema,
        )

    def load(self, source: str) -> pd.DataFrame:
        if self._conn is None:
            self.connect()
        cur = self._conn.cursor()
        if source.strip().upper().startswith("SELECT"):
            cur.execute(source)
        else:
            cur.execute(f"SELECT * FROM {source}")
        df = cur.fetch_pandas_all()
        cur.close()
        return df
