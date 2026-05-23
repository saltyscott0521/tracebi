"""
TraceBi — code-first, traceable BI and analytics framework.

Quick start:
    from tracebi import DataModel, CSVConnector, DataSet
"""

from tracebi.connectors.base import BaseConnector
from tracebi.connectors.csv_connector import CSVConnector
from tracebi.connectors.sql_connector import SQLConnector
from tracebi.connectors.memory_connector import MemoryConnector
from tracebi.connectors.duckdb_connector import DuckDBConnector
from tracebi.model.dataset import DataSet, LineageNode
from tracebi.model.data_model import DataModel
from tracebi.etl.bronze import BronzeLayer, LandingLayer
from tracebi.etl.silver import SilverLayer, ManipulationLayer
from tracebi.etl.gold import GoldLayer, FinalLayer
from tracebi.lineage.diagram import LineageDiagram
from tracebi.pipeline.runner import PipelineRunner

__all__ = [
    # Connectors
    "BaseConnector",
    "CSVConnector",
    "SQLConnector",
    "MemoryConnector",
    "DuckDBConnector",
    # Core
    "DataSet",
    "LineageNode",
    "DataModel",
    # Layers (canonical)
    "LandingLayer",
    "ManipulationLayer",
    "FinalLayer",
    # Layers (back-compat aliases)
    "BronzeLayer",
    "SilverLayer",
    "GoldLayer",
    # Visualisation & orchestration
    "LineageDiagram",
    "PipelineRunner",
]
