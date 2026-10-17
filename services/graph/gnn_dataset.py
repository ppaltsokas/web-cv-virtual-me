from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from services.api.knowledge_graph.models import GraphNode, GraphSnapshot


GNN_DATASET_SCHEMA_VERSION = "gnn-data-v1"
TRAINABLE_NODE_TYPES = {"Project", "Skill", "Technology", "Role", "Claim", "Chunk", "Employer", "Education", "Certification"}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_source_group(path: str) -> str:
    # Paths are manifest IDs, not a private repository directory layout.
    return path.strip().replace("\\", "/")


def source_group(source_path: str) -> str:
    paths = sorted(
        {
            _canonical_source_group(part)
            for part in source_path.split("|")
            if part.strip()
        }
    )
    return "|".join(paths) or "unknown"


def assign_source_splits(source_paths: Iterable[str]) -> dict[str, str]:
    groups = sorted({source_group(path) for path in source_paths})
    fixed_train = {group for group in groups if group == "profile"}
    candidates = [group for group in groups if group not in fixed_train]
    if len(candidates) < 3:
        return {group: "train" for group in groups}
    ordered = sorted(
        candidates,
        key=lambda group: (hashlib.sha256(group.encode("utf-8")).hexdigest(), group),
    )
    test_count = max(1, round(len(ordered) * 0.10))
    validation_count = max(1, round(len(ordered) * 0.10))
    splits = {group: "train" for group in fixed_train}
    for index, group in enumerate(ordered):
        if index < test_count:
            splits[group] = "test"
        elif index < test_count + validation_count:
            splits[group] = "validation"
        else:
            splits[group] = "train"
    return splits


def _feature_text(node: GraphNode) -> str:
    values: list[str] = [node.name]
    for key in ("text", "description", "category", "title"):
        value = node.properties.get(key)
        if isinstance(value, str) and value.strip() and value.strip() not in values:
            values.append(value.strip())
    return "\n".join(values)


def _jsonl(rows: Iterable[dict[str, Any]]) -> bytes:
    return ("\n".join(_canonical_json(row) for row in rows) + "\n").encode("utf-8")


def export_gnn_dataset(snapshot: GraphSnapshot, output_dir: Path) -> dict[str, Any]:
    node_types = sorted({node.label.value for node in snapshot.nodes})
    edge_types = sorted({relationship.type.value for relationship in snapshot.relationships})
    node_type_to_index = {node_type: index for index, node_type in enumerate(node_types)}
    edge_type_to_index = {edge_type: index for index, edge_type in enumerate(edge_types)}
    ordered_nodes = sorted(snapshot.nodes, key=lambda node: node.id)
    node_index_by_id = {node.id: index for index, node in enumerate(ordered_nodes)}
    source_splits = assign_source_splits(
        [node.source_path for node in snapshot.nodes]
        + [relationship.source_path for relationship in snapshot.relationships]
    )

    nodes = [
        {
            "index": node_index_by_id[node.id],
            "id": node.id,
            "type": node.label.value,
            "type_index": node_type_to_index[node.label.value],
            "name": node.name,
            "feature_text": _feature_text(node),
            "trainable": node.label.value in TRAINABLE_NODE_TYPES,
            "source_key": source_group(node.source_path),
            "source_hash": node.source_hash,
            "split": source_splits[source_group(node.source_path)],
            "confidence": node.confidence,
        }
        for node in ordered_nodes
    ]
    ordered_relationships = sorted(
        snapshot.relationships,
        key=lambda relationship: (relationship.source_id, relationship.type.value, relationship.target_id),
    )
    edges = [
        {
            "id": relationship.id,
            "source_id": relationship.source_id,
            "source_index": node_index_by_id[relationship.source_id],
            "target_id": relationship.target_id,
            "target_index": node_index_by_id[relationship.target_id],
            "type": relationship.type.value,
            "type_index": edge_type_to_index[relationship.type.value],
            "source_key": source_group(relationship.source_path),
            "source_hash": relationship.source_hash,
            "split": source_splits[source_group(relationship.source_path)],
            "confidence": relationship.confidence,
        }
        for relationship in ordered_relationships
    ]
    node_bytes = _jsonl(nodes)
    edge_bytes = _jsonl(edges)
    dataset_version = "gnn-v1-" + _sha256_bytes(
        snapshot.ingestion_version.encode("utf-8") + node_bytes + edge_bytes
    )[:16]
    manifest = {
        "schema_version": GNN_DATASET_SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "graph_version": snapshot.ingestion_version,
        "source_files": snapshot.source_files,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_type_to_index": node_type_to_index,
        "edge_type_to_index": edge_type_to_index,
        "trainable_node_types": sorted(TRAINABLE_NODE_TYPES),
        "node_split_counts": dict(sorted(Counter(node["split"] for node in nodes).items())),
        "edge_split_counts": dict(sorted(Counter(edge["split"] for edge in edges).items())),
        "source_split_counts": dict(sorted(Counter(source_splits.values()).items())),
        "source_splits": source_splits,
        "files": {
            "nodes.jsonl": _sha256_bytes(node_bytes),
            "edges.jsonl": _sha256_bytes(edge_bytes),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "nodes.jsonl").write_bytes(node_bytes)
    (output_dir / "edges.jsonl").write_bytes(edge_bytes)
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def validate_gnn_dataset(
    dataset_dir: Path,
    *,
    expected_graph_version: str | None = None,
) -> dict[str, Any]:
    manifest_path = dataset_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Missing GNN dataset manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != GNN_DATASET_SCHEMA_VERSION:
        raise ValueError("Incompatible GNN dataset schema version")
    if expected_graph_version and manifest.get("graph_version") != expected_graph_version:
        raise ValueError("GNN dataset graph version does not match the active graph")
    files = manifest.get("files", {})
    if set(files) != {"nodes.jsonl", "edges.jsonl"}:
        raise ValueError("GNN dataset manifest has an invalid file set")
    file_bytes = {}
    for filename, expected_hash in files.items():
        path = dataset_dir / filename
        if not path.exists():
            raise ValueError(f"GNN dataset checksum mismatch: {filename}")
        file_bytes[filename] = path.read_bytes()
        if _sha256_bytes(file_bytes[filename]) != expected_hash:
            raise ValueError(f"GNN dataset checksum mismatch: {filename}")
    if len(file_bytes["nodes.jsonl"].splitlines()) != manifest.get("node_count"):
        raise ValueError("GNN dataset node count mismatch")
    if len(file_bytes["edges.jsonl"].splitlines()) != manifest.get("edge_count"):
        raise ValueError("GNN dataset edge count mismatch")
    expected_dataset_version = "gnn-v1-" + _sha256_bytes(
        manifest["graph_version"].encode("utf-8")
        + file_bytes["nodes.jsonl"]
        + file_bytes["edges.jsonl"]
    )[:16]
    if manifest.get("dataset_version") != expected_dataset_version:
        raise ValueError("GNN dataset version mismatch")
    return manifest
