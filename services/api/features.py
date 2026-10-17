"""Explicit optional capabilities; defaults make no database or model calls."""
from dataclasses import dataclass
import math
import os
from pathlib import Path


def flag(name: str, default=False) -> bool:
    value = os.getenv(name, str(default)).lower()
    if value not in {'true', 'false', '1', '0', 'yes', 'no'}:
        raise ValueError(f'{name} must be true or false')
    return value in {'true', '1', 'yes'}


def private_path(root: Path, name: str, default: str) -> Path:
    path = (root / os.getenv(name, default)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'{name} must remain inside this deployment')
    return path


@dataclass(frozen=True)
class Features:
    graph: bool = False
    graph_retrieval: bool = False
    graph_backend: str = 'snapshot'
    postgres: bool = False
    persistent_history: bool = False
    gnn_shadow: bool = False
    gnn_active: bool = False
    canary_percent: float = 0.0

    @classmethod
    def from_env(cls):
        value = cls(
            graph=flag('KNOWLEDGE_GRAPH_ENABLED'),
            graph_retrieval=flag('GRAPH_RETRIEVAL_ENABLED'),
            graph_backend=os.getenv('GRAPH_BACKEND', 'snapshot'),
            postgres=flag('POSTGRES_ENABLED'),
            persistent_history=flag('PERSISTENT_CHAT_HISTORY_ENABLED'),
            gnn_shadow=flag('GNN_SHADOW_ENABLED'),
            gnn_active=flag('GNN_RERANKING_ENABLED'),
            canary_percent=float(os.getenv('GNN_CANARY_PERCENT', '0')),
        )
        if value.graph_backend not in {'snapshot', 'neo4j'}:
            raise ValueError('GRAPH_BACKEND must be snapshot or neo4j')
        if value.graph_retrieval and not value.graph:
            raise ValueError('Graph retrieval requires KNOWLEDGE_GRAPH_ENABLED=true')
        if value.persistent_history and not value.postgres:
            raise ValueError('Persistent history requires POSTGRES_ENABLED=true')
        if (value.gnn_shadow or value.gnn_active) and not value.graph_retrieval:
            raise ValueError('GNN ranking requires graph retrieval')
        if not math.isfinite(value.canary_percent) or not 0 <= value.canary_percent <= 100:
            raise ValueError('GNN_CANARY_PERCENT must be between 0 and 100')
        return value
