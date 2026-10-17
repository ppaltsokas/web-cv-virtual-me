from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np


DEFAULT_FEATURE_WEIGHTS = {
    "vector_similarity": 1.25,
    "lexical_score": 0.75,
    "graph_proximity": 1.0,
    "source_quality": 0.5,
    "gnn_similarity": 1.5,
}


def load_logistic_reranker(path: Path, *, artifact_version: str, graph_version: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("reranker_schema_version") != "gnn-logistic-reranker-v1":
        raise ValueError("Incompatible GNN logistic reranker schema")
    if payload.get("graphsage_artifact_version") != artifact_version:
        raise ValueError("GNN logistic reranker artifact version mismatch")
    if payload.get("graph_version") != graph_version:
        raise ValueError("GNN logistic reranker graph version mismatch")
    if set(payload.get("weights", {})) != set(DEFAULT_FEATURE_WEIGHTS):
        raise ValueError("GNN logistic reranker feature set mismatch")
    return payload


class GNNEmbeddingIndex:
    """Load and query a GraphSAGE embedding artifact without PyTorch."""

    def __init__(self, artifact_dir: Path, expected_graph_version: str | None = None) -> None:
        self.artifact_dir = artifact_dir
        self.manifest = self._load_manifest(expected_graph_version)
        index = json.loads((artifact_dir / "index.json").read_text(encoding="utf-8"))
        if not isinstance(index, dict):
            raise ValueError("GraphSAGE artifact index must be an object")
        dimensions = self.manifest.get("embedding_dimensions")
        if not isinstance(dimensions, int) or dimensions <= 0:
            raise ValueError("GraphSAGE artifact embedding dimensions are invalid")
        self.vectors: dict[str, np.ndarray] = {}
        with np.load(artifact_dir / "embeddings.npz", allow_pickle=False) as arrays:
            for node_type, stable_ids in index.items():
                if not isinstance(stable_ids, list) or not all(isinstance(node_id, str) for node_id in stable_ids):
                    raise ValueError(f"GraphSAGE artifact index is invalid: {node_type}")
                key = f"embeddings_{node_type}"
                if key not in arrays:
                    raise ValueError(f"GraphSAGE artifact embeddings are missing: {node_type}")
                vectors = np.asarray(arrays[key], dtype=np.float32)
                if vectors.shape != (len(stable_ids), dimensions):
                    raise ValueError(f"GraphSAGE artifact embedding shape mismatch: {node_type}")
                if not np.isfinite(vectors).all():
                    raise ValueError(f"GraphSAGE artifact embeddings contain non-finite values: {node_type}")
                norms = np.linalg.norm(vectors, axis=1, keepdims=True)
                vectors = vectors / np.maximum(norms, 1e-12)
                self.vectors.update(zip(stable_ids, vectors))

    def _load_manifest(self, expected_graph_version: str | None) -> dict[str, Any]:
        manifest_path = self.artifact_dir / "manifest.json"
        if not manifest_path.exists():
            raise ValueError(f"Missing GraphSAGE artifact manifest: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("artifact_schema_version") != "graphsage-artifact-v1":
            raise ValueError("Incompatible GraphSAGE artifact schema version")
        content = {key: value for key, value in manifest.items() if key != "artifact_version"}
        expected_version = "graphsage-v1-" + hashlib.sha256(
            json.dumps(content, sort_keys=True, default=float).encode("utf-8")
        ).hexdigest()[:16]
        if manifest.get("artifact_version") != expected_version:
            raise ValueError("GraphSAGE artifact version checksum mismatch")
        if expected_graph_version and manifest.get("graph_version") != expected_graph_version:
            raise ValueError("GraphSAGE artifact graph version mismatch")
        files = manifest.get("files", {})
        if set(files) != {"embeddings.npz", "index.json", "model.pt"}:
            raise ValueError("GraphSAGE artifact manifest has an invalid file set")
        for filename, expected_hash in files.items():
            path = self.artifact_dir / filename
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
                raise ValueError(f"GraphSAGE artifact checksum mismatch: {filename}")
        return manifest

    def similarity(self, anchor_ids: Iterable[str], candidate_ids: Iterable[str]) -> float | None:
        anchors = [self.vectors[node_id] for node_id in anchor_ids if node_id in self.vectors]
        candidates = [self.vectors[node_id] for node_id in candidate_ids if node_id in self.vectors]
        if not anchors or not candidates:
            return None
        anchor = np.mean(anchors, axis=0)
        anchor /= max(float(np.linalg.norm(anchor)), 1e-12)
        return max(float(np.dot(anchor, candidate)) for candidate in candidates)


class ShadowGNNReranker:
    """Compute uncalibrated scores; the engine controls shadow/gated activation."""

    def __init__(
        self,
        embedding_index: GNNEmbeddingIndex,
        *,
        weights: dict[str, float] | None = None,
        intercept: float = -2.0,
    ) -> None:
        self.embedding_index = embedding_index
        self.weights = {**DEFAULT_FEATURE_WEIGHTS, **(weights or {})}
        self.intercept = intercept

    def score(self, query_entity_ids: Iterable[str], candidates: list[Any]) -> dict[str, Any]:
        query_entity_ids = set(query_entity_ids)
        matched_query_ids = {
            node_id for node_id in query_entity_ids if node_id in self.embedding_index.vectors
        }
        if not matched_query_ids:
            return {
                "mode": "fallback",
                "reason": "query_entities_unavailable",
                "artifact_version": self.embedding_index.manifest["artifact_version"],
                "graph_version": self.embedding_index.manifest["graph_version"],
                "query_entity_ids_matched": 0,
                "candidates_scored": 0,
                "ranking_changed": False,
                "candidates": [],
            }
        rows = []
        for rrf_rank, candidate in enumerate(candidates, start=1):
            gnn_similarity = self.embedding_index.similarity(
                matched_query_ids,
                candidate.graph_evidence_ids,
            )
            features = {
                "vector_similarity": _clamp(candidate.channel_scores.get("faiss", 0.0), 0.0, 1.0),
                "lexical_score": _positive_scale(candidate.channel_scores.get("keyword", 0.0)),
                "graph_proximity": 1.0 / (candidate.graph_distance + 1) if candidate.graph_distance is not None else 0.0,
                "source_quality": candidate.source_quality / 3.0,
                "gnn_similarity": (gnn_similarity + 1.0) / 2.0 if gnn_similarity is not None else 0.0,
            }
            logit = self.intercept + sum(self.weights[name] * value for name, value in features.items())
            candidate.shadow_score = 1.0 / (1.0 + math.exp(-logit))
            rows.append(
                {
                    "source": candidate.source,
                    "rrf_rank": rrf_rank,
                    "rrf_score": round(candidate.score, 6),
                    "shadow_score": round(candidate.shadow_score, 6),
                    "gnn_similarity": round(gnn_similarity, 6) if gnn_similarity is not None else None,
                    "features": {name: round(value, 6) for name, value in features.items()},
                }
            )
        shadow_order = sorted(rows, key=lambda row: (-row["shadow_score"], row["source"]))
        shadow_ranks = {row["source"]: rank for rank, row in enumerate(shadow_order, start=1)}
        for row in rows:
            row["shadow_rank"] = shadow_ranks[row["source"]]
        return {
            "mode": "shadow",
            "artifact_version": self.embedding_index.manifest["artifact_version"],
            "graph_version": self.embedding_index.manifest["graph_version"],
            "query_entity_ids_matched": sum(
                node_id in self.embedding_index.vectors for node_id in matched_query_ids
            ),
            "candidates_scored": len(rows),
            "ranking_changed": any(row["rrf_rank"] != row["shadow_rank"] for row in rows),
            "candidates": rows,
        }


def _positive_scale(value: float) -> float:
    return 1.0 - math.exp(-max(float(value), 0.0))


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(float(value), upper))
