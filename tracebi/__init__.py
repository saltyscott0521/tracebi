"""
TraceBi — code-first, traceable BI and analytics framework.

Quick start:
    from tracebi import DataModel, CSVConnector, DataSet
"""

from tracebi.connectors.base import BaseConnector
from tracebi.connectors.csv_connector import CSVConnector
from tracebi.connectors.sql_connector import SQLConnector
from tracebi.connectors.memory_connector import MemoryConnector
from tracebi.model.dataset import DataSet, LineageNode
from tracebi.model.data_model import DataModel

__all__ = [
    "BaseConnector",
    "CSVConnector",
    "SQLConnector",
    "MemoryConnector",
    "DataSet",
    "LineageNode",
    "DataModel",
]
