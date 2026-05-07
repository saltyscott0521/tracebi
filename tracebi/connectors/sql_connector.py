"""SQLAlchemy-backed relational database connector."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from tracebi.connectors.base import BaseConnector


class SQLConnector(BaseConnector):
    """
    Load tables or run queries against any SQLAlchemy-supported database.

    Usage:
        connector = SQLConnector("sales_db", url="postgresql://user:pass@host/db")
        model.add_connector(connector)
        model.add_table("orders", connector="sales_db", source="orders")

    Args:
        name:   Logical name used to reference this connector in a DataModel.
        url:    SQLAlchemy connection URL.
        **kwargs: Additional keyword arguments passed to ``create_engine``.
    """

    def __init__(self, name: str, url: str, **kwargs) -> None:
        super().__init__(name)
        self.url = url
        self._engine_kwargs = kwargs
        self._engine = None

    def connect(self) -> None:
        try:
            from sqlalchemy import create_engine
        except ImportError:
            raise ImportError(
                "sqlalchemy is required for SQLConnector.\n"
                "Install with: pip install sqlalchemy"
            )
        self._engine = create_engine(self.url, **self._engine_kwargs)

    def load(self, source: str) -> pd.DataFrame:
        if self._engine is None:
            self.connect()
        # source may be a table name or a SELECT query
        if source.strip().upper().startswith("SELECT"):
            return pd.read_sql(source, con=self._engine)
        return pd.read_sql_table(source, con=self._engine)
