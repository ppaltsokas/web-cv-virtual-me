# Technology showcase

This replica demonstrates a portfolio and document-grounded virtual persona with fictional content. Its reusable components include the original application's two-layer relational GraphSAGE training, typed negative sampling, embedding validation, shadow reranking and canary circuit breaker. Owner-specific ingestion and retrieval wiring have configurable replacements.

| Capability | Implementation | Default |
| --- | --- | --- |
| Portfolio | React 19, TypeScript, Vite, bundled Tailwind, Lucide, Markdown | Available |
| Entrance and proxy | Node, scrypt passwords, HttpOnly visitor sessions | Enabled after setup |
| Persona API | Python, FastAPI, Pydantic, OpenAI, LangChain Core | Paid calls disabled |
| Grounded retrieval | Keyword, FAISS embeddings, reciprocal rank fusion, citations | Keyword; semantic index explicit |
| Knowledge graph / GraphRAG | Typed entities, manifest-backed excerpts, two-hop retrieval | Disabled |
| Graph database | Neo4j driver, scoped Cypher, explicit transactional ingestion | Optional |
| Persistent conversation | Psycopg/PostgreSQL, accepted turns, first-message recall, compaction, expiry | Disabled |
| Graph neural network | PyTorch, PyTorch Geometric, HeteroConv / SAGEConv | Offline training |
| Reranking | Checksummed NumPy embeddings, shadow and gated canary modes | Disabled |
| Evaluation | Scikit-learn AUC/AP, paired recall/MRR/nDCG/top-1, latency, saved-answer citation checks | Explicit offline commands |
| Deployment | Docker, Railway, Cloud Run, GitHub Actions | Configuration only |

SQLite answer caching, legacy Gemini compatibility, notebook ingestion, automatic paid online judging, original account-specific release automation and chat archiving are excluded. They are not represented as enabled technologies. The main application's personal corpus, evaluation fixtures, trained weights, indexes and Git history are excluded.

## Architecture

~~~mermaid
flowchart TD
    Visitor --> Gate["Node password gate"]
    Gate --> UI["React / TypeScript portfolio"]
    Gate --> API["FastAPI private proxy boundary"]
    API --> Intent["OpenAI intent planning"]
    Intent --> Social["Social conversation / recall"]
    Intent --> Retrieval["Shared retrieval engine"]
    Docs["Selected profile and manifest documents"] --> Keyword["Keyword retrieval"]
    Docs --> FAISS["Optional OpenAI embeddings + FAISS"]
    Docs --> Graph["Deterministic typed graph"]
    Graph --> GraphStore["Snapshot or Neo4j"]
    Keyword --> Retrieval
    FAISS --> Retrieval
    GraphStore --> Retrieval
    Retrieval --> Ranking["Optional GraphSAGE shadow / gated reranking"]
    Ranking --> LLM["Grounded OpenAI response via LangChain"]
    Social --> LLM
    LLM --> Citations["Citation validation and bounded correction"]
    Citations --> Memory["Bounded memory / optional PostgreSQL"]
    Citations --> Visitor
    Graph --> Train["Offline relational GraphSAGE"]
    Train --> Artifact["Versioned embedding artifact"]
    Artifact --> Ranking
    Retrieval --> Evaluate["Paired offline evaluation"]
    Evaluate --> GateFile["Version-bound activation gate"]
    GateFile --> Ranking
~~~

Live chat and evaluation call the same retrieval engine. Co-occurrence creates evidence links, not invented achievements. Database results must match current manifest chunks. Graph/model versions bind the owner configuration, document bytes and schema. Runtime never loads a pickled model; it reads validated NumPy embeddings.

## Run the fictional demonstration

From the replica root, with Python 3.11 and its virtual environment active:

~~~powershell
python -m pip install -r services/api/requirements-stack.txt
python -m pip install -r services/gnn/requirements.txt
python scripts/showcase.py demo
python scripts/showcase.py status --examples
~~~

This runs real CPU training and a 12-question comparison. It uses only checked-in Alex Morgan examples and writes ignored artifacts under models/showcase/. It makes no OpenAI calls, database connections, deployments or environment changes. It preserves local owner inputs and works without an API key or Docker.

Read models/showcase/evaluation/comparison.json and gate.json. A failed gate is a valid result: runtime retains the hybrid order. Small fictional datasets do not establish production improvement.

The training graph contains training-source edges only. Validation and test sources are grouped by document ID; typed negatives are disjoint across splits and exclude every known positive. Text features for all nodes are visible, so this is a transductive demonstration. At least three documents are needed for held-out groups. Link AUC and question retrieval measure different tasks.

## Test the local chatbot

Example-only artifacts cannot be used with a different profile or manifest paths. For the initialized local owner:

~~~powershell
python scripts/showcase.py graph
python scripts/showcase.py train
Copy-Item examples/evaluation/retrieval.jsonl config/retrieval.local.jsonl
~~~

Preserve an existing custom benchmark instead of overwriting it. Edit its header to the configured owner name and supply supported questions with current manifest document IDs as relevance labels.

~~~powershell
python scripts/showcase.py evaluate --cases config/retrieval.local.jsonl
~~~

Add these flags to ignored .env.local, preserving existing credentials:

~~~dotenv
KNOWLEDGE_GRAPH_ENABLED=true
GRAPH_RETRIEVAL_ENABLED=true
GRAPH_BACKEND=snapshot
GNN_SHADOW_ENABLED=true
GNN_RERANKING_ENABLED=false
GNN_CANARY_PERCENT=0
~~~

Restart the backend with python scripts/manage.py backend and run the frontend with python scripts/manage.py frontend. Use its password gate. Actual conversation requires the backend key and PAID_AI_ENABLED=true; graph commands are offline.

Health reports graph backend, artifact/gate status and aggregate canary counters. Shadow preserves the hybrid answer order. To deliberately test active ordering, first obtain a matching passed gate, then set GNN_RERANKING_ENABLED=true and GNN_CANARY_PERCENT between 1 and 100. Deterministic session allocation and a process-local failure circuit breaker apply. Missing graph anchors retain hybrid retrieval. Changing documents invalidates the old model and gate.

Default evaluation uses keyword plus graph. An existing owner FAISS index can be included with evaluate --semantic; that explicit option makes paid query-embedding calls. Offline commands never build an embedding index.

Reranker weights are heuristic and its sigmoid scores are uncalibrated. A score is not a probability that a source is correct.

## Optional Neo4j and PostgreSQL

To run dedicated local services with new independent credentials:

~~~powershell
python scripts/showcase.py service-credentials
docker compose --env-file .env.local -f infra/docker/compose.showcase.yml up -d
python scripts/showcase.py graph --neo4j
~~~

Credentials are written privately to ignored .env.local without being printed. Existing values and feature flags are preserved. Ports bind to 127.0.0.1: PostgreSQL 55432, Bolt 57687, Neo4j Browser 57474. Review occupied ports first. Named volumes retain service data.

After ingestion, set GRAPH_BACKEND=neo4j. For PostgreSQL session state, also set:

~~~dotenv
POSTGRES_ENABLED=true
PERSISTENT_CHAT_HISTORY_ENABLED=true
CHAT_SESSION_TTL_SECONDS=86400
~~~

Restart the backend. PostgreSQL retains bounded accepted turns and quoted user excerpts for compaction, scoped by owner fingerprint and authenticated visitor session. There is no archive endpoint, transcript listing or append-only archive. Profile/document changes create a new scope. Expired rows are inaccessible, and physically removed at initialization or the next save. Unexpired state can survive a backend restart for a still-authenticated visitor.

Use one backend worker. Persistence does not distribute admission control, canary metrics or frontend login state. Graph queries are read-only and version-scoped; old graph versions remain in the owner's private database until deliberate maintenance.

~~~powershell
docker compose --env-file .env.local -f infra/docker/compose.showcase.yml stop
~~~

## Verification and deployment

Run python -m pytest -q and python scripts/release_check.py. GraphSAGE tests run when optional training dependencies are installed. Real database tests require RUN_STACK_SERVICE_TESTS=true and dedicated STACK_TEST_DATABASE_URL, STACK_TEST_NEO4J_URI and STACK_TEST_NEO4J_PASSWORD values. They never use runtime DATABASE_URL as a fallback. GitHub Actions provisions isolated test services.

The API Dockerfile accepts --build-arg INSTALL_OPTIONAL_STACK=true for Neo4j/Psycopg drivers. PyTorch is needed only for training. Private deployment bundles exclude graph/GNN artifacts: generate and evaluate them inside the private context, whose manifest paths have their own fingerprint, before building. Explicitly ingest that context's graph before selecting hosted Neo4j.

Owner benchmark files are excluded from automatic bundles and Docker contexts. To evaluate inside a private deployment context, deliberately copy only the reviewed benchmark there before running evaluation; the generated Docker ignore file excludes it from the image build.

Generated indexes, model artifacts, owner benchmarks, database data and credentials remain ignored. These commands do not modify the original app or enable hosted features.

## References

- [PyTorch Geometric SAGEConv](https://pytorch-geometric.readthedocs.io/en/latest/generated/torch_geometric.nn.conv.SAGEConv.html)
- [Neo4j managed transactions](https://neo4j.com/docs/python-manual/current/transactions/)
- [Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)
