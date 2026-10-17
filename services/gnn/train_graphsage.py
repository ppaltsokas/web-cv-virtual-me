from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.gnn.training import (
    build_training_bundle,
    load_gnn_dataset,
    normalized_text_features,
    train_graphsage,
    write_embedding_artifact,
)
from services.graph.gnn_dataset import TRAINABLE_NODE_TYPES


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a two-layer relational GraphSAGE link predictor.")
    parser.add_argument("--dataset-dir", type=Path, default=REPOSITORY_ROOT / "models" / "gnn" / "dataset")
    parser.add_argument("--output-dir", type=Path, default=REPOSITORY_ROOT / "models" / "gnn" / "artifacts" / "current")
    parser.add_argument("--feature-dimensions", type=int, default=256)
    parser.add_argument("--embedding-dimensions", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    manifest, nodes, edges = load_gnn_dataset(args.dataset_dir)
    features = normalized_text_features(nodes, args.feature_dimensions)
    data, examples, local_index, stable_ids = build_training_bundle(
        nodes,
        edges,
        features,
        seed=args.seed,
    )
    model, embeddings, metrics = train_graphsage(
        data,
        examples,
        local_index,
        embedding_dimensions=args.embedding_dimensions,
        epochs=args.epochs,
        patience=args.patience,
        seed=args.seed,
    )
    artifact_embeddings = {
        node_type: values
        for node_type, values in embeddings.items()
        if node_type in TRAINABLE_NODE_TYPES
    }
    artifact_ids = {
        node_type: values
        for node_type, values in stable_ids.items()
        if node_type in TRAINABLE_NODE_TYPES
    }
    import torch
    import torch_geometric

    artifact = write_embedding_artifact(
        args.output_dir,
        manifest=manifest,
        embeddings=artifact_embeddings,
        stable_ids=artifact_ids,
        metrics=metrics,
        model_state=model.state_dict(),
        training_config={
            "feature_method": "sha256-token-hashing-l2",
            "feature_dimensions": args.feature_dimensions,
            "embedding_dimensions": args.embedding_dimensions,
            "epochs_requested": args.epochs,
            "patience": args.patience,
            "seed": args.seed,
            "torch_version": torch.__version__,
            "torch_geometric_version": torch_geometric.__version__,
        },
    )
    print(json.dumps(artifact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
