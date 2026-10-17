from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from services.graph.gnn_dataset import validate_gnn_dataset


TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


def load_gnn_dataset(dataset_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    manifest = validate_gnn_dataset(dataset_dir)
    nodes = [json.loads(line) for line in (dataset_dir / "nodes.jsonl").read_text(encoding="utf-8").splitlines()]
    edges = [json.loads(line) for line in (dataset_dir / "edges.jsonl").read_text(encoding="utf-8").splitlines()]
    return manifest, nodes, edges


def normalized_text_features(nodes: list[dict[str, Any]], dimensions: int = 256) -> np.ndarray:
    if dimensions < 8:
        raise ValueError("dimensions must be at least 8")
    features = np.zeros((len(nodes), dimensions), dtype=np.float32)
    for node in nodes:
        row = features[node["index"]]
        tokens = TOKEN_PATTERN.findall(node.get("feature_text", "").lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            row[index] += sign
        norm = float(np.linalg.norm(row))
        if norm > 0:
            row /= norm
    return features


def typed_negative_samples(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    split: str,
    seed: int,
    ratio: float = 1.0,
    excluded: set | None = None,
) -> list[dict[str, Any]]:
    if ratio < 0:
        raise ValueError("ratio must be non-negative")
    node_by_id = {node["id"]: node for node in nodes}
    node_ids_by_type: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        node_ids_by_type[node["type"]].append(node["id"])
    positives = [edge for edge in edges if edge["split"] == split]
    existing = {(edge["source_id"], edge["type"], edge["target_id"]) for edge in edges}
    requested = math.ceil(len(positives) * ratio)
    random_generator = random.Random(seed)
    negatives = []
    attempts = 0
    max_attempts = max(100, requested * 50)
    while len(negatives) < requested and attempts < max_attempts and positives:
        attempts += 1
        positive = positives[random_generator.randrange(len(positives))]
        target_type = node_by_id[positive["target_id"]]["type"]
        candidates = node_ids_by_type[target_type]
        target_id = candidates[random_generator.randrange(len(candidates))]
        key = (positive["source_id"], positive["type"], target_id)
        if key in existing or key in (excluded or set()) or any(
            item["source_id"] == key[0] and item["type"] == key[1] and item["target_id"] == key[2]
            for item in negatives
        ):
            continue
        negatives.append(
            {
                "source_id": positive["source_id"],
                "target_id": target_id,
                "type": positive["type"],
                "split": split,
                "negative": True,
            }
        )
    return negatives


def build_training_bundle(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    features: np.ndarray,
    *,
    seed: int,
):
    try:
        import torch
        from torch_geometric.data import HeteroData
    except ImportError as exc:
        raise RuntimeError("Install services/gnn/requirements.txt before training") from exc

    data = HeteroData()
    nodes_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        nodes_by_type[node["type"]].append(node)
    local_index: dict[str, tuple[str, int]] = {}
    stable_ids: dict[str, list[str]] = {}
    for node_type, rows in sorted(nodes_by_type.items()):
        ordered = sorted(rows, key=lambda row: row["index"])
        stable_ids[node_type] = [row["id"] for row in ordered]
        global_indexes = [row["index"] for row in ordered]
        data[node_type].x = torch.from_numpy(features[global_indexes])
        for index, row in enumerate(ordered):
            local_index[row["id"]] = (node_type, index)

    train_edges: dict[tuple[str, str, str], list[tuple[int, int]]] = defaultdict(list)
    for edge in edges:
        if edge["split"] != "train":
            continue
        source_type, source_index = local_index[edge["source_id"]]
        target_type, target_index = local_index[edge["target_id"]]
        train_edges[(source_type, edge["type"], target_type)].append((source_index, target_index))
        train_edges[(target_type, f"rev_{edge['type']}", source_type)].append((target_index, source_index))
    for edge_type, pairs in sorted(train_edges.items()):
        data[edge_type].edge_index = torch.tensor(pairs, dtype=torch.long).t().contiguous()

    examples = {}
    previous_negatives = set()
    for split_index, split in enumerate(("train", "validation", "test")):
        positives = [{**edge, "negative": False} for edge in edges if edge["split"] == split]
        negatives = typed_negative_samples(nodes, edges, split=split, seed=seed + split_index, excluded=previous_negatives)
        previous_negatives.update((row["source_id"], row["type"], row["target_id"]) for row in negatives)
        examples[split] = positives + negatives
    return data, examples, local_index, stable_ids


def train_graphsage(
    data,
    examples: dict[str, list[dict[str, Any]]],
    local_index: dict[str, tuple[str, int]],
    *,
    embedding_dimensions: int = 64,
    epochs: int = 100,
    learning_rate: float = 0.005,
    weight_decay: float = 1e-4,
    patience: int = 15,
    seed: int = 42,
):
    try:
        import torch
        import torch.nn.functional as functional
        from sklearn.metrics import average_precision_score, roc_auc_score
        from torch import nn
        from torch_geometric.nn import HeteroConv, SAGEConv
    except ImportError as exc:
        raise RuntimeError("Install services/gnn/requirements.txt before training") from exc

    torch.manual_seed(seed)
    torch.set_num_threads(1)
    random.seed(seed)
    np.random.seed(seed)
    edge_types = data.metadata()[1]
    node_types = data.metadata()[0]
    relation_types = sorted({row["type"] for rows in examples.values() for row in rows})
    if any(not rows or not any(row["negative"] for row in rows) for rows in examples.values()):
        raise ValueError("Training needs nonempty train/validation/test groups with typed negative examples. Supply at least three distinct documents.")

    class RelationalGraphSAGE(nn.Module):
        def __init__(self):
            super().__init__()
            self.input_layers = nn.ModuleDict({
                node_type: nn.Linear(data[node_type].x.shape[1], embedding_dimensions)
                for node_type in node_types
            })
            self.convolutions = nn.ModuleList([
                HeteroConv(
                    {edge_type: SAGEConv((-1, -1), embedding_dimensions) for edge_type in edge_types},
                    aggr="sum",
                )
                for _ in range(2)
            ])
            self.relation_matrices = nn.ParameterDict({
                relation: nn.Parameter(torch.empty(embedding_dimensions, embedding_dimensions))
                for relation in relation_types
            })
            for matrix in self.relation_matrices.values():
                nn.init.xavier_uniform_(matrix)

        def forward(self):
            values = {
                node_type: functional.relu(self.input_layers[node_type](data[node_type].x))
                for node_type in node_types
            }
            for index, convolution in enumerate(self.convolutions):
                updated = convolution(values, data.edge_index_dict)
                values = {
                    node_type: updated.get(node_type, values[node_type])
                    for node_type in node_types
                }
                if index == 0:
                    values = {node_type: functional.relu(value) for node_type, value in values.items()}
            return {node_type: functional.normalize(value, p=2, dim=-1) for node_type, value in values.items()}

        def score(self, embeddings, rows):
            scores = []
            for row in rows:
                source_type, source_index = local_index[row["source_id"]]
                target_type, target_index = local_index[row["target_id"]]
                relation = row["type"]
                source = embeddings[source_type][source_index]
                target = embeddings[target_type][target_index]
                scores.append(source @ self.relation_matrices[relation] @ target)
            return torch.stack(scores) if scores else torch.empty(0)

    model = RelationalGraphSAGE()
    with torch.no_grad():
        model()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate, weight_decay=weight_decay)

    def labels(rows):
        return torch.tensor([0.0 if row["negative"] else 1.0 for row in rows], dtype=torch.float32)

    def evaluate(split):
        rows = examples[split]
        if not rows:
            return {"auc": 0.5, "average_precision": 0.0}
        model.eval()
        with torch.no_grad():
            probabilities = torch.sigmoid(model.score(model(), rows)).cpu().numpy()
        expected = labels(rows).numpy()
        return {
            "auc": float(roc_auc_score(expected, probabilities)) if len(set(expected)) > 1 else 0.5,
            "average_precision": float(average_precision_score(expected, probabilities)),
        }

    best_state = None
    best_validation_auc = -1.0
    best_epoch = 0
    epochs_without_improvement = 0
    history = []
    for epoch in range(1, epochs + 1):
        model.train()
        optimizer.zero_grad()
        train_rows = examples["train"]
        logits = model.score(model(), train_rows)
        loss = functional.binary_cross_entropy_with_logits(logits, labels(train_rows))
        loss.backward()
        optimizer.step()
        validation = evaluate("validation")
        history.append({"epoch": epoch, "loss": float(loss.item()), **validation})
        if validation["auc"] > best_validation_auc:
            best_validation_auc = validation["auc"]
            best_epoch = epoch
            best_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
        if epochs_without_improvement >= patience:
            break
    if best_state:
        model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        embeddings = {key: value.cpu().numpy() for key, value in model().items()}
    return model, embeddings, {
        "best_epoch": best_epoch,
        "epochs_trained": len(history),
        "history": history,
        "validation": evaluate("validation"),
        "test": evaluate("test"),
    }


def write_embedding_artifact(
    output_dir: Path,
    *,
    manifest: dict[str, Any],
    embeddings: dict[str, np.ndarray],
    stable_ids: dict[str, list[str]],
    metrics: dict[str, Any],
    model_state: dict[str, Any],
    training_config: dict[str, Any],
) -> dict[str, Any]:
    import torch

    output_dir.mkdir(parents=True, exist_ok=True)
    arrays = {f"embeddings_{node_type}": values for node_type, values in embeddings.items()}
    np.savez_compressed(output_dir / "embeddings.npz", **arrays)
    index = {node_type: ids for node_type, ids in sorted(stable_ids.items())}
    (output_dir / "index.json").write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
    torch.save(model_state, output_dir / "model.pt")
    files = {}
    for filename in ("embeddings.npz", "index.json", "model.pt"):
        files[filename] = hashlib.sha256((output_dir / filename).read_bytes()).hexdigest()
    artifact = {
        "artifact_schema_version": "graphsage-artifact-v1",
        "dataset_version": manifest["dataset_version"],
        "graph_version": manifest["graph_version"],
        "embedding_dimensions": next(iter(embeddings.values())).shape[1],
        "node_counts": {key: len(value) for key, value in sorted(stable_ids.items())},
        "training_config": training_config,
        "metrics": metrics,
        "files": files,
    }
    artifact["artifact_version"] = "graphsage-v1-" + hashlib.sha256(
        json.dumps(artifact, sort_keys=True, default=float).encode("utf-8")
    ).hexdigest()[:16]
    (output_dir / "manifest.json").write_text(
        json.dumps(artifact, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return artifact


def validate_embedding_artifact(
    artifact_dir: Path,
    *,
    expected_graph_version: str | None = None,
    expected_dataset_version: str | None = None,
) -> dict[str, Any]:
    manifest_path = artifact_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Missing GraphSAGE artifact manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("artifact_schema_version") != "graphsage-artifact-v1":
        raise ValueError("Incompatible GraphSAGE artifact schema version")
    if expected_graph_version and manifest.get("graph_version") != expected_graph_version:
        raise ValueError("GraphSAGE artifact graph version mismatch")
    if expected_dataset_version and manifest.get("dataset_version") != expected_dataset_version:
        raise ValueError("GraphSAGE artifact dataset version mismatch")
    files = manifest.get("files", {})
    if set(files) != {"embeddings.npz", "index.json", "model.pt"}:
        raise ValueError("GraphSAGE artifact manifest has an invalid file set")
    for filename, expected_hash in files.items():
        path = artifact_dir / filename
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise ValueError(f"GraphSAGE artifact checksum mismatch: {filename}")
    index = json.loads((artifact_dir / "index.json").read_text(encoding="utf-8"))
    with np.load(artifact_dir / "embeddings.npz", allow_pickle=False) as arrays:
        for node_type, stable_node_ids in index.items():
            key = f"embeddings_{node_type}"
            if key not in arrays or arrays[key].shape != (
                len(stable_node_ids),
                manifest["embedding_dimensions"],
            ):
                raise ValueError(f"GraphSAGE artifact embedding shape mismatch: {node_type}")
    return manifest
