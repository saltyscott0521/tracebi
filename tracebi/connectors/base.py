"""Abstract base class for all TraceBi connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class BaseConnector(ABC):
    """
    Abstract connector. Subclass this to add a new data source.

    Every connector has a ``name`` (used to reference it in a DataModel)
    and two abstract methods: ``connect()`` and ``load(source)``.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def connect(self) -> None:
        """Open / validate the connection to the data source."""
        ...

    @abstractmethod
    def load(self, source: str) -> pd.DataFrame:
        """
        Load data from *source* and return a pandas DataFrame.

        Args:
            source: Connector-specific identifier (file name, table name, query, …).
        """
        ...

    def write(
        self,
        df: "pd.DataFrame",
        table: str,
        if_exists: str = "replace",
    ) -> None:
        """
        Write *df* to *table* in this connector's data store.

        Args:
            df:        DataFrame to write.
            table:     Destination table / key name.
            if_exists: What to do if the table already exists:
                       ``'replace'`` (default), ``'append'``, or ``'fail'``.

        Raises:
            NotImplementedError: If the connector does not support writes.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support write(). "
            "Use SQLConnector or MemoryConnector for write operations."
        )

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"
