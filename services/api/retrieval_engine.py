"""Shared hybrid retrieval and optional GraphSAGE ranking for API and evaluation."""
from dataclasses import dataclass, field
import hashlib
import json
import logging
import threading
import time
from .features import Features, private_path
from .knowledge_graph.ingestion import build_snapshot, chunk_id, SnapshotGraphStore
from .chat_pipeline.gnn_reranking import GNNEmbeddingIndex, ShadowGNNReranker
from .chat_pipeline.gnn_activation import load_gnn_activation_gate
from .chat_pipeline.gnn_canary import GNNCanaryController


@dataclass
class Candidate:
    source: str
    chunk: object
    score: float = 0.0
    channel_scores: dict = field(default_factory=dict)
    graph_distance: int | None = None
    source_quality: int = 3
    graph_evidence_ids: list = field(default_factory=list)
    shadow_score: float | None = None


class RetrievalEngine:
    def __init__(self, knowledge, features=None, *, graph_store=None, artifact_dir=None, gate_path=None):
        self.knowledge = knowledge
        self.features = features or Features.from_env()
        self.snapshot = build_snapshot(knowledge) if self.features.graph else None
        self.graph = graph_store
        self.index = self.reranker = None
        self.gate = {'active': False, 'reason': 'disabled'}
        self.artifact_status = 'disabled'
        self.graph_failures = 0
        self.metrics_lock = threading.Lock()
        self.canary = GNNCanaryController(self.features.canary_percent, salt=knowledge.fingerprint)
        if self.snapshot is not None and self.graph is None:
            if self.features.graph_backend == 'neo4j':
                from .knowledge_graph.store import Neo4jGraphStore
                self.graph = Neo4jGraphStore.from_env(self.snapshot)
                try:
                    self.graph.verify()
                except Exception:
                    self.graph.close()
                    raise
            else:
                self.graph = SnapshotGraphStore(self.snapshot)
        if self.features.gnn_shadow or self.features.gnn_active:
            directory = artifact_dir or private_path(knowledge.root, 'GNN_ARTIFACT_DIR', 'models/gnn/artifacts/current')
            gate_path = gate_path or private_path(knowledge.root, 'GNN_ACTIVATION_GATE', 'models/gnn/evaluation/gate.json')
            try:
                self.index = GNNEmbeddingIndex(directory, expected_graph_version=self.snapshot.ingestion_version)
                self.reranker = ShadowGNNReranker(self.index)
                self.artifact_status = 'ready'
                self.gate = load_gnn_activation_gate(gate_path,
                    artifact_version=self.index.manifest['artifact_version'], graph_version=self.snapshot.ingestion_version)
                if self.gate['active']:
                    # An activation file is only valid with its exact paired report.
                    report_path = gate_path.parent / 'comparison.json'
                    gate = json.loads(gate_path.read_text())
                    report_bytes = report_path.read_bytes()
                    report = json.loads(report_bytes)
                    if (gate.get('report_sha256') != hashlib.sha256(report_bytes).hexdigest()
                            or not report.get('gate_eligible')
                            or report.get('artifact_version') != self.index.manifest['artifact_version']
                            or report.get('graph_version') != self.snapshot.ingestion_version):
                        self.gate = {'active': False, 'reason': 'report_mismatch'}
            except (ValueError, OSError, KeyError):
                if self.index is None:
                    self.artifact_status = 'missing_or_stale'
                self.gate = {'active': False, 'reason': 'missing_or_invalid_artifact_or_report'}

    def candidates(self, query, client=None):
        candidates = {}
        index = {chunk: i for i, chunk in enumerate(self.knowledge.chunks)}
        def candidate(chunk):
            identifier = chunk_id(index[chunk], chunk)
            if identifier not in candidates:
                candidates[identifier] = Candidate(identifier, chunk, graph_evidence_ids=[identifier])
            return candidates[identifier]
        for channel, hits in self.knowledge.search_channels(query, client).items():
            for rank, (chunk, score) in enumerate(hits, 1):
                item = candidate(chunk)
                item.score += 1 / (60 + rank)
                item.channel_scores[channel] = score
        if self.features.graph_retrieval and self.graph is not None:
            try:
                graph_rows = self.graph.search_evidence(query)
            except Exception:
                logging.getLogger(__name__).warning('Optional graph retrieval failed; keeping document retrieval')
                with self.metrics_lock:
                    self.graph_failures += 1
                graph_rows = []
            for rank, row in enumerate(graph_rows, 1):
                position = row['chunk_index']
                if not 0 <= position < len(self.knowledge.chunks):
                    continue
                chunk = self.knowledge.chunks[position]
                if row['evidence_id'] != chunk_id(position, chunk) or row['source'] != chunk.source:
                    continue
                item = candidate(chunk)
                item.score += 1 / (60 + rank)
                item.graph_distance = row['distance']
                item.channel_scores['graph'] = 1 / (row['distance'] + 1)
        return sorted(candidates.values(), key=lambda item: (-item.score, item.source))

    def rank(self, query, client=None, session_id='', limit=5, *, mode='runtime'):
        if mode not in {'runtime', 'baseline', 'candidate'}:
            raise ValueError('Invalid ranking mode')
        baseline = self.candidates(query, client)
        diagnostic = {'mode': 'baseline', 'graph_backend': self.features.graph_backend if self.features.graph_retrieval else 'disabled'}
        if mode == 'baseline':
            return [item.chunk for item in baseline[:limit]], diagnostic
        active = self.features.gnn_active and self.gate['active']
        decision = self.canary.decide(session_id) if active and mode == 'runtime' else {'selected': False}
        should_score = mode == 'candidate' or self.features.gnn_shadow or decision['selected']
        if not should_score:
            return [item.chunk for item in baseline[:limit]], diagnostic
        started = time.perf_counter()
        try:
            if self.reranker is None:
                raise ValueError('No current GraphSAGE artifact')
            scores = self.reranker.score(self.graph.anchors(query), baseline)
            diagnostic = scores
            if scores['mode'] == 'shadow' and (mode == 'candidate' or decision['selected']):
                baseline = sorted(baseline, key=lambda item: (-item.shadow_score, item.source))
                diagnostic = {**scores, 'mode': 'active'}
            elif scores['mode'] == 'fallback':
                diagnostic = {**scores, 'mode': 'fallback'}
        except Exception:
            logging.getLogger(__name__).warning('Optional GNN ranking failed; keeping hybrid order')
            diagnostic = {'mode': 'fallback', 'reason': 'gnn_unavailable'}
        self.canary.record(decision, diagnostic['mode'], (time.perf_counter() - started) * 1000, diagnostic.get('reason'))
        return [item.chunk for item in baseline[:limit]], diagnostic

    def status(self):
        return {
            'knowledge_graph_enabled': self.features.graph,
            'graph_retrieval_enabled': self.features.graph_retrieval,
            'graph_backend': self.features.graph_backend if self.features.graph else 'disabled',
            'graph_failures': self.graph_failures,
            'gnn_artifact': self.artifact_status,
            'gnn_shadow_enabled': self.features.gnn_shadow,
            'gnn_reranking_active': self.features.gnn_active and self.gate['active'] and self.features.canary_percent > 0 and not self.canary.status()['circuit_open'],
            'gnn_gate': 'passed' if self.gate['active'] else self.gate.get('reason', 'disabled'),
            'gnn_canary': self.canary.status(),
        }

    def close(self):
        if self.graph:
            self.graph.close()
