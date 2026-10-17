"""Paired, offline evaluation of the exact runtime retrieval engine."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import time
from .metrics import evaluate_ranking, percentile


def load_cases(path: Path, knowledge):
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if not rows or rows[0].get('schema') != 'portfolio-retrieval-cases-v1':
        raise ValueError('Evaluation needs a portfolio-retrieval-cases-v1 header')
    header, cases = rows[0], rows[1:]
    if header.get('owner') != knowledge.profile.resume.personalInfo.name:
        raise ValueError('Evaluation fixtures belong to another owner. Supply your own labeled cases.')
    known = {'profile', *knowledge.documents}
    ids, queries = set(), set()
    for case in cases:
        if not case.get('id') or case['id'] in ids or not case.get('query', '').strip() or case['query'].casefold() in queries:
            raise ValueError('Evaluation cases need unique IDs and questions')
        if not case.get('relevant_sources') or not set(case['relevant_sources']) <= known:
            raise ValueError('Evaluation relevance labels must use current manifest IDs or profile')
        ids.add(case['id'])
        queries.add(case['query'].casefold())
    if not cases:
        raise ValueError('No evaluation cases')
    return header, cases


def compare_retrieval(engine, cases_path: Path, *, client=None):
    header, cases = load_cases(cases_path, engine.knowledge)
    if engine.index is None:
        raise ValueError('Train a current GraphSAGE artifact before comparing candidate retrieval')
    rows = []
    for case in cases:
        row = {'id': case['id']}
        for name, mode in [('baseline', 'baseline'), ('candidate', 'candidate')]:
            started = time.perf_counter()
            chunks, diagnostic = engine.rank(case['query'], client, session_id=case['id'], limit=5, mode=mode)
            ranking = list(dict.fromkeys(chunk.source for chunk in chunks))
            row[name] = {**evaluate_ranking(case, ranking), 'top1': float(bool(ranking) and ranking[0] in case['relevant_sources']),
                'latency_ms': (time.perf_counter() - started) * 1000, 'mode': diagnostic['mode']}
        rows.append(row)
    summary = {}
    for name in ['baseline', 'candidate']:
        summary[name] = {metric: sum(row[name][metric] for row in rows) / len(rows)
                         for metric in ['recall_at_5', 'reciprocal_rank', 'ndcg_at_5', 'top1']}
        summary[name]['p95_latency_ms'] = percentile([row[name]['latency_ms'] for row in rows], .95)
    fallback_rate = sum(row['candidate']['mode'] == 'fallback' for row in rows) / len(rows)
    thresholds = {'minimum_cases': 6, 'maximum_fallback_rate': .10, 'maximum_p95_latency_ms': 1000}
    eligible = (
        len(rows) >= thresholds['minimum_cases']
        and fallback_rate <= thresholds['maximum_fallback_rate']
        and summary['candidate']['p95_latency_ms'] <= thresholds['maximum_p95_latency_ms']
        and all(summary['candidate'][metric] + 1e-9 >= summary['baseline'][metric]
                for metric in ['recall_at_5', 'reciprocal_rank', 'ndcg_at_5', 'top1'])
    )
    return {'schema': 'portfolio-paired-retrieval-v1', 'purpose': header.get('purpose', 'owner-supplied'),
        'owner_fingerprint': engine.knowledge.fingerprint, 'graph_version': engine.snapshot.ingestion_version,
        'artifact_version': engine.index.manifest['artifact_version'],
        'cases_sha256': hashlib.sha256(cases_path.read_bytes()).hexdigest(), 'case_count': len(rows),
        'semantic_embeddings_used': client is not None and engine.knowledge.index is not None,
        'summary': summary, 'candidate_fallback_rate': fallback_rate, 'thresholds': thresholds,
        'gate_eligible': eligible, 'cases': rows,
        'limitations': 'Small offline retrieval benchmark. Link AUC and citation IDs do not prove answer quality or production improvement.'}


def write_comparison(report, directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    data = json.dumps(report, indent=2, sort_keys=True).encode()
    (directory / 'comparison.json').write_bytes(data)
    gate = {'gate_schema_version': 'gnn-activation-gate-v1', 'passed': report['gate_eligible'],
        'artifact_version': report['artifact_version'], 'graph_version': report['graph_version'],
        'report_sha256': hashlib.sha256(data).hexdigest()}
    (directory / 'gate.json').write_text(json.dumps(gate, indent=2), encoding='utf-8')
    return gate


def evaluate_answers(path: Path, cases):
    """Inspect saved answers; no provider or LLM judge is called."""
    expected = {case['id']: set(case['relevant_sources']) for case in cases}
    rows, seen = [], set()
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item.get('id') not in expected or item['id'] in seen:
            raise ValueError('Answer IDs must be unique and belong to the selected evaluation cases')
        seen.add(item['id'])
        answer, sources = item['answer'], item.get('sources', {})
        citations = set(re.findall(r'\[(S\d+)\]', answer))
        valid = citations <= sources.keys()
        rows.append({'id': item['id'], 'has_citation': bool(citations), 'valid_citation_ids': valid,
            'cites_relevant_source': bool({sources.get(identifier) for identifier in citations} & expected[item['id']])})
    return {'schema': 'portfolio-answer-inspection-v1', 'cases': rows,
        'coverage': len(rows) / max(1, len(cases)),
        'limitations': 'Citation checks inspect identifiers and labeled source relevance, not semantic entailment or factual accuracy.'}
