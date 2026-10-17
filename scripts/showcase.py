"""Build and evaluate the optional stack without enabling hosted features."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def knowledge_for(examples=False):
    from services.api.profile import load_profile, load_manifest, config_path
    from services.api.knowledge import KnowledgeBase
    profile = ROOT / 'config/profile.example.json' if examples else config_path('profile')
    manifest = ROOT / 'config/content.example.json' if examples else config_path('content')
    return KnowledgeBase(load_profile(profile), load_manifest(manifest), ROOT,
                         None if examples else ROOT / os.getenv('INDEX_DIR', 'data/index'))


def paths(examples):
    if examples:
        base = ROOT / 'models/showcase'
        return base / 'graph.json', base / 'dataset', base / 'artifacts/current', base / 'evaluation'
    from services.api.features import private_path
    return (ROOT / 'models/graph/snapshot.json', ROOT / 'models/gnn/dataset',
        private_path(ROOT, 'GNN_ARTIFACT_DIR', 'models/gnn/artifacts/current'),
        private_path(ROOT, 'GNN_ACTIVATION_GATE', 'models/gnn/evaluation/gate.json').parent)


def prepare(knowledge, examples=False, neo4j=False):
    from services.api.knowledge_graph.ingestion import build_snapshot
    from services.graph.gnn_dataset import export_gnn_dataset
    snapshot = build_snapshot(knowledge)
    graph, dataset, _, _ = paths(examples)
    graph.parent.mkdir(parents=True, exist_ok=True)
    graph.write_text(snapshot.model_dump_json(indent=2), encoding='utf-8')
    manifest = export_gnn_dataset(snapshot, dataset)
    if neo4j:
        from services.api.knowledge_graph.store import Neo4jGraphStore
        store = Neo4jGraphStore.from_env(snapshot)
        try:
            store.ingest()
            store.verify()
        finally:
            store.close()
    return manifest


def train(knowledge, examples=False, epochs=30):
    from services.gnn.training import (load_gnn_dataset, normalized_text_features,
        build_training_bundle, train_graphsage, write_embedding_artifact)
    from services.graph.gnn_dataset import TRAINABLE_NODE_TYPES
    prepare(knowledge, examples)
    _, dataset, artifact, _ = paths(examples)
    manifest, nodes, edges = load_gnn_dataset(dataset)
    features = normalized_text_features(nodes, 64)
    data, cases, local_index, stable_ids = build_training_bundle(nodes, edges, features, seed=42)
    model, embeddings, metrics = train_graphsage(data, cases, local_index,
        embedding_dimensions=16, epochs=epochs, patience=8, seed=42)
    import torch
    import torch_geometric
    return write_embedding_artifact(artifact, manifest=manifest,
        embeddings={key: values for key, values in embeddings.items() if key in TRAINABLE_NODE_TYPES},
        stable_ids={key: values for key, values in stable_ids.items() if key in TRAINABLE_NODE_TYPES},
        metrics=metrics, model_state=model.state_dict(),
        training_config={'feature_method': 'sha256-token-hashing-l2', 'feature_dimensions': 64,
            'embedding_dimensions': 16, 'epochs_requested': epochs, 'seed': 42,
            'torch_version': torch.__version__, 'torch_geometric_version': torch_geometric.__version__})


def evaluate(knowledge, examples=False, cases_path=None, semantic=False):
    from services.api.features import Features
    from services.api.retrieval_engine import RetrievalEngine
    from services.evaluation.showcase import compare_retrieval, write_comparison
    _, _, artifact, evaluation = paths(examples)
    cases_path = cases_path or ROOT / 'examples/evaluation/retrieval.jsonl'
    features = Features(graph=True, graph_retrieval=True, gnn_shadow=True)
    engine = RetrievalEngine(knowledge, features, artifact_dir=artifact, gate_path=evaluation / 'gate.json')
    client = None
    if semantic:
        from services.api.cost_controls import require_paid_ai
        require_paid_ai()
        if knowledge.index is None:
            raise ValueError('Semantic evaluation requires an owner-bound FAISS index. Build it explicitly first.')
        from openai import OpenAI
        client = OpenAI(max_retries=0)
    try:
        report = compare_retrieval(engine, cases_path, client=client)
        gate = write_comparison(report, evaluation)
        print(json.dumps({'case_count': report['case_count'], 'summary': report['summary'],
            'candidate_fallback_rate': report['candidate_fallback_rate'], 'gate_passed': gate['passed'],
            'report': str(evaluation.relative_to(ROOT) / 'comparison.json')}, indent=2))
        return report
    finally:
        engine.close()


def service_credentials():
    from dotenv import dotenv_values, set_key
    target = ROOT / '.env.local'
    if not target.is_file():
        raise ValueError('Run scripts/manage.py init first')
    values = dotenv_values(target, interpolate=False)
    password = values.get('POSTGRES_PASSWORD') or secrets.token_urlsafe(28)
    updates = {
        'POSTGRES_PASSWORD': password,
        'DATABASE_URL': 'postgresql://portfolio_demo:' + password + '@127.0.0.1:55432/portfolio_demo',
        'NEO4J_URI': 'bolt://127.0.0.1:57687', 'NEO4J_USERNAME': 'neo4j',
        'NEO4J_PASSWORD': secrets.token_urlsafe(28), 'NEO4J_DATABASE': 'neo4j',
    }
    for key, value in updates.items():
        if not values.get(key):
            set_key(target, key, value)
    print('Missing local service credentials generated privately. Existing values and feature flags were preserved.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ['graph', 'train', 'evaluate', 'demo', 'status', 'inspect-answers', 'service-credentials']:
        command = sub.add_parser(name)
        command.add_argument('--examples', action='store_true', help='Use only the checked-in fictional owner')
        if name == 'graph':
            command.add_argument('--neo4j', action='store_true', help='Explicitly write the selected graph to your configured Neo4j')
        if name in {'train', 'demo'}:
            command.add_argument('--epochs', type=int, default=30)
        if name in {'evaluate', 'demo', 'inspect-answers'}:
            command.add_argument('--cases', type=Path)
        if name == 'evaluate':
            command.add_argument('--semantic', action='store_true', help='Explicit paid query embeddings; needs an existing owner index')
        if name == 'inspect-answers':
            command.add_argument('--answers', type=Path, required=True)
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env.local', override=False)
    try:
        if args.command == 'service-credentials':
            service_credentials()
            return 0
        examples = args.examples or args.command == 'demo'
        if args.command in {'train', 'demo'} and not 1 <= args.epochs <= 300:
            raise ValueError('Choose between 1 and 300 training epochs')
        knowledge = knowledge_for(examples)
        if args.command == 'graph':
            report = prepare(knowledge, examples, args.neo4j)
            print(json.dumps({key: report[key] for key in ['graph_version', 'node_count', 'edge_count', 'source_split_counts']}))
        elif args.command == 'train':
            report = train(knowledge, examples, args.epochs)
            print(json.dumps({'artifact_version': report['artifact_version'], 'metrics': report['metrics']}))
        elif args.command == 'evaluate':
            evaluate(knowledge, examples, args.cases, args.semantic)
        elif args.command == 'demo':
            train(knowledge, True, args.epochs)
            evaluate(knowledge, True, args.cases)
            print('Fictional offline demo complete. No feature flags, local owner inputs, hosted services or API keys were changed.')
        elif args.command == 'inspect-answers':
            from services.evaluation.showcase import load_cases, evaluate_answers
            _, cases = load_cases(args.cases or ROOT / 'examples/evaluation/retrieval.jsonl', knowledge)
            print(json.dumps(evaluate_answers(args.answers, cases), indent=2))
        elif args.command == 'status':
            from services.api.features import Features
            from services.api.retrieval_engine import RetrievalEngine
            _, _, artifact, evaluation = paths(examples)
            features = Features(graph=True, graph_retrieval=True, gnn_shadow=True) if examples else Features.from_env()
            engine = RetrievalEngine(knowledge, features, artifact_dir=artifact, gate_path=evaluation / 'gate.json')
            try:
                print(json.dumps(engine.status(), indent=2))
            finally:
                engine.close()
    except Exception as exc:
        if type(exc) is ValueError:
            print(str(exc), file=sys.stderr)
        else:
            print(f'Showcase command failed ({type(exc).__name__}). Check optional dependencies and private service settings.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
