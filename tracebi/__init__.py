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
from tracebi.model.star_schema import StarSchema
from tracebi.etl.bronze import BronzeLayer
from tracebi.etl.silver import SilverLayer
from tracebi.etl.gold import GoldLayer
from tracebi.lineage.diagram import LineageDiagram
from tracebi.pipeline.runner import PipelineRunner

__all__ = [
    "BaseConnector",
    "CSVConnector",
    "SQLConnector",
    "MemoryConnector",
    "DataSet",
    "LineageNode",
    "DataModel",
    "StarSchema",
    "BronzeLayer",
    "SilverLayer",
    "GoldLayer",
    "LineageDiagram",
    "PipelineRunner",
]
