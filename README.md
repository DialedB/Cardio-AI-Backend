# CardioSmart

## Overview

CardioSmart is a Python backend project for a cardiovascular application. This repository
currently provides a production-oriented starting point: a FastAPI modular monolith,
PostgreSQL session infrastructure, a neutral RAG contract, and an independent SafeRAG wrapper.

The repository contains three separately owned areas. The backend team owns the application
and its integration boundary. The AI team owns the standalone RAG implementation. SafeRAG sits
between them as a security wrapper around a small shared protocol.

## Architecture

The backend is a modular monolith. Its API, application services, persistence, authentication,
jobs, integrations, and observability code run as one deployable application while remaining
separated into small modules.

The intended RAG call path is:

```text
Backend application
        ↓
backend/integrations/rag_client.py
        ↓
SafeRAG
        ↓
shared RAG interface
        ↓
AI implementation supplied at runtime
```

The backend does not implement retrieval or generation. Its `RAGClient` accepts a
protocol-compatible secured RAG object, which should be a `SafeRAG` instance in production.
SafeRAG inspects a request, calls the provided RAG implementation, and inspects the response.
It does not import from `ai/` or depend on AI implementation details.

## Repository Structure

```text
.
├── backend/                 FastAPI modular monolith
│   ├── api/                 HTTP route boundaries
│   ├── auth/                Authentication and authorization boundaries
│   ├── db/                  SQLAlchemy session and future persistence code
│   ├── integrations/        External subsystem adapters
│   ├── jobs/                Future background job entry points
│   ├── observability/       Logging, metrics, and tracing integration points
│   └── services/            Future application services
├── ai/                      AI-team-owned ingestion and standalone RAG pipeline
├── saferag/                 Independent RAG security wrapper
├── shared/contracts/        Coordinated cross-team data contracts
├── infra/docker/            Backend container definition
├── config/                  Local OpenTelemetry, Prometheus, Grafana, and Loki config
├── tests/                   Backend-owned tests and future end-to-end tests
├── docs/                    Future project documentation
└── .github/                 CI, CODEOWNERS, and pull request template
```

Empty directories such as `ai/`, `docs/`, and `tests/e2e/` are present in a working checkout
but are not represented by Git until their owners add content.

## Backend

[`backend/main.py`](backend/main.py) is the small application composition root. It creates the
FastAPI application and registers these routes:

| Route | Current behavior |
| --- | --- |
| `GET /api/health` | Returns HTTP 200 with service status |
| `GET /api/auth` | Returns HTTP 501 |
| `GET /api/users` | Returns HTTP 501 |
| `GET /api/conversations` | Returns HTTP 501 |
| `GET /api/documents` | Returns HTTP 501 |
| `POST /api/query` | Returns HTTP 501 |

The HTTP 501 routes reserve clear API boundaries without inventing business behavior. Domain
models, repositories, identity rules, and background tasks remain intentionally undefined.

Configuration is loaded from environment variables through
[`backend/config.py`](backend/config.py). Supported variables are `APP_NAME`, `APP_ENV`,
`DEBUG`, `DATABASE_URL`, and `LOG_LEVEL`. The example file contains local-only values and no
production credentials.

[`backend/db/session.py`](backend/db/session.py) provides lazy SQLAlchemy engine and session
factory construction for PostgreSQL. Importing the FastAPI app does not connect to the
database. No domain schema or migrations exist yet.

## AI / RAG

The `ai/` directory contains a standalone PDF ingestion and retrieval-augmented
generation (RAG) command-line pipeline. It uses Neon Postgres for stored chunks,
embeddings, and full-text retrieval. It runs separately from the FastAPI backend:
`POST /api/query` is still a placeholder and does not call this pipeline.

### Components

- `ai/ingestion_pipeline.py` loads PDF files, splits them into chunks, creates
  embeddings, and stores them in the configured Neon PGVector collection.
- `ai/full_text_retriever.py` searches chunk text using Postgres full-text
  search and returns ranked documents.
- `ai/rag_service.py` is the stateless pipeline. `RagService.answer(question, history)`
  combines full-text and vector retrieval, generates query variations, merges
  results with reciprocal-rank fusion, and creates answers using retrieved source
  excerpts. It returns a structured `AnswerResult` and keeps no conversation state.
  Importing it makes no OpenAI or Neon connection; `RagService.from_settings()` does
  that. If retrieval, answer generation, or the safety review fails, it returns the
  fail-closed "safety checks are unavailable" message instead of raising; query
  rewriting and query variations fall back to the original question. OpenAI calls
  time out after `OPENAI_TIMEOUT_SECONDS` (default 30) with `OPENAI_MAX_RETRIES`
  retries (default 2). Only the most recent `RAG_MAX_HISTORY_MESSAGES` messages
  (default 20) are sent to the models.
- `ai/rag_adapter.py` implements the shared `RAGInterface` on top of `RagService`.
  Callers pass history as `metadata["history"]`, a list of
  `{"role": "user" | "assistant", "content": str}` items, and should store an
  exchange only when the response metadata has `record_in_history` set to true.
  Sources are returned only for answered questions and never include absolute paths.
- `ai/RAG_Pipeline.py` is the interactive test CLI. It holds the chat history for
  one session and prints each result.
- `ai/settings.py` provides the shared model, chunking, collection, and database
  settings.
- `ai/migrations/0001_add_full_text_search.sql` adds the database schema needed
  by the full-text retriever.

### Ingestion behavior

The ingestion script reads top-level PDF files from `ai/docs/` in filename
order. PDFs and the `docs/` directory are ignored by Git, so add source PDFs
locally.

Each loaded PDF page is split into chunks. The default chunk size is 1,000
characters with 100 characters of overlap. These values can be changed with
`RAG_CHUNK_SIZE` and `RAG_CHUNK_OVERLAP`.

Chunk IDs are based on the collection name, the PDF path relative to `ai/docs/`,
and a SHA-256 hash of the chunk text. They do not depend on chunk position.
Unchanged IDs already in the collection are skipped. Repeated identical chunks
within one source are collapsed; identical text in different source files
remains stored as separate chunks, though its embedding is reused within an
ingestion run.

By default, ingestion deletes rows in the collection that are not present in the
current PDF input. Treat the configured collection as belonging to this corpus
when using the default behavior. Pass `--no-prune` to retain rows absent from
the current input.

Ingestion now embeds batches asynchronously, with up to four concurrent batches
by default. Set `EMBEDDING_CONCURRENCY` to change this limit. Neon writes remain
bounded and are applied after each concurrent embedding group. The reported
embedding wall time measures elapsed time across those groups; combined worker
time is the sum of their individual embedding durations.

`--dry-run` reports the current, new, unchanged, and stale chunk counts and
estimates embedding tokens without requesting embeddings or writing data. It
still connects to Neon to look up existing chunk IDs. If `tiktoken` is not
available, the token estimate is approximate.

### Comparing synchronous and asynchronous embedding throughput

The benchmark compares sync and async embedding on the same local PDF chunks,
without connecting to or writing to Neon. This sample uses four batches so the
async run can use all four concurrent slots:

```powershell
python ai/benchmark_embeddings.py --max-chunks 400 --batch-size 100 --concurrency 4 --repeats 2
```

The JSON output reports elapsed time and texts per second for each mode, plus
the async speedup. Adjust `--max-chunks`, `--batch-size`, `--concurrency`, or
`--repeats` as needed. Each mode and repeat sends embedding requests to the
configured API and may incur charges. Use the same settings when comparing runs.

### Neon full-text search schema

The full-text retriever queries the generated `search_vector` column on
`langchain_pg_embedding`. The SQL migration adds that column using the English
text-search configuration and creates a GIN index for searching it. PostgreSQL
keeps the generated column synchronized with chunk text.

The SQL migration is tracked at `ai/migrations/0001_add_full_text_search.sql`. On a normal ingestion
run, PGVector initializes its tables and the pipeline applies this idempotent migration before
embedding or writing chunks. It creates a missing `search_vector` generated column and GIN index;
existing objects are left in place. `--dry-run` does not apply the migration. RAG startup checks
that the table, column, and index exist and reports an actionable error if they do not.

For a manual setup or recovery, you can still run the migration from the repository root with `psql`:

```bash
psql "<Neon connection string>" \
  -f ai/migrations/0001_add_full_text_search.sql
```

### AI/RAG setup

Install the AI dependencies separately from the backend:

```bash
cd ai
python -m venv .venv
# Activate the virtual environment for your shell
python -m pip install -r requirements.txt
```

The pipeline reads its secrets from the process environment, the repository-root
`.env.local`, then `ai/.env.local` and `ai/.env`. Configure `OPENAI_API_KEY` and
`DATABASE_URL` (or `DATABASE_URL_UNPOOLED`) before starting it. Run from the `ai/`
directory:

```bash
python RAG_Pipeline.py
```

The observability stack is optional. Without a running Collector the pipeline still
works, but exporters log connection errors; set `CARDIO_RAG_TELEMETRY_DISABLED=true`
to turn exports off.

### RAG telemetry

`ai/rag_telemetry.py` configures OpenTelemetry traces, metrics, and logs for the
RAG pipeline and exports them to the local Collector. Traces cover the request,
moderation, query generation, retrieval, rank
fusion, answer generation, and response review. Metrics include request outcomes and
duration, operation latency and errors, search-result/fused/selected document counts,
LLM calls, and provider-reported token usage. Token metrics are emitted only when the
model response includes usage metadata. Prometheus and Grafana show no RAG series until
the pipeline has processed requests.

The instrumented code does not attach prompt, answer, or retrieved-text content to span
attributes. Pipeline logs name the failed step and error type only. Importing
`ai/rag_service.py` still configures this telemetry globally, because `ai/rag_telemetry.py`
sets it up at import time. The interactive CLI prints the question, queries, document
previews with their file and page, and answer to the console together once the answer is
ready, followed by a line such as `[outcome: safety_rejected | decided by: safety review]`
that names the step which decided the result.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://127.0.0.1:4317` | Collector OTLP endpoint; use `http://otel-collector:4317` when the RAG process runs in the Compose network |
| `OTEL_SERVICE_NAME` | `cardio-rag` | Telemetry service name |
| `APP_VERSION` | `unknown` | Service version resource attribute |
| `APP_ENVIRONMENT` / `APP_ENV` | `dev` | Deployment environment resource attribute |
| `OTEL_METRIC_EXPORT_INTERVAL_MS` | `5000` | Metric export interval in milliseconds |
| `CARDIO_RAG_TELEMETRY_DISABLED` | unset | Set to `true`, `1`, or `yes` to disable telemetry exports |
| `RAG_MODEL_NAME` | `gpt-6-astra` | Main RAG model |
| `SAFETY_REVIEW_MODEL` | `gpt-4o-mini` | Safety reviewer model |
| `RAG_MAX_HISTORY_MESSAGES` | `20` | Most recent chat messages sent to the models |

The telemetry stack is part of the root `docker-compose.yml`. Its configuration and
the provisioned **Cardio RAG Pipeline** dashboard are under `config/`. See Grafana at
`http://localhost:3000/d/cardio-rag-overview/cardio-rag-pipeline`, Jaeger at
`http://localhost:16686`, Prometheus at `http://localhost:9090`, and Loki at
`http://localhost:3100`. Grafana's local Compose credentials default to `admin` / `admin`;
set `GRAFANA_ADMIN_PASSWORD` before the first start to choose a different password.

## SafeRAG

SafeRAG is an independent decorator around any object that satisfies `RAGInterface`:

```python
from saferag import SafeRAG

secured_rag = SafeRAG(their_rag)
response = await secured_rag.query(request)
```

The wrapper always calls its input guard before the provided RAG and its output guard after a
response. A blocked input prevents the RAG call. A blocked output raises an explicit error
instead of returning the response as approved.

The initial input and output guards are deterministic pass-through placeholders that
demonstrate composition and control flow. **They do not provide production security.** Actual
detectors, policies, and audit behavior require separate security design and review.

## Shared Contracts

`shared/contracts/rag.py` defines small Pydantic models for `RAGRequest`, `RAGResponse`,
`RAGSource`, and optional critic metadata, plus the asynchronous `RAGInterface` protocol.
These are data and interface definitions only; they contain no business or RAG logic.

The shared contract is the coordination boundary between backend, SafeRAG, and the AI team.
Contract changes can break several owned areas and therefore require explicit coordination and
review from both backend and AI codeowners.

## Running Locally

### Python development server

Requirements:

- Python 3.12 or newer
- PostgreSQL, if exercising future persistence behavior

Create a virtual environment and install the project with development tools:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
uvicorn backend.main:app --reload
```

The API is available at `http://localhost:8000`, the health endpoint at
`http://localhost:8000/api/health`, and generated API documentation at
`http://localhost:8000/docs`.

### Docker Compose

Requirements:

- Docker with Docker Compose

Build and start the FastAPI backend, PostgreSQL, and local observability stack:

```bash
docker compose up --build -d
```

The Collector accepts OTLP gRPC on port `4317` and OTLP HTTP on `4318`. Prometheus,
Grafana, and Jaeger are exposed on ports `9090`, `3000`, and `16686`. Loki's API is
bound to host loopback on port `3100`; other Compose services reach it over the
internal network. Loki stores data in the `loki_data` volume mounted at `/loki`.
The RAG CLI runs separately on the host; its default OTLP endpoint reaches the published
Collector port. Run the CLI and submit a question to populate the RAG dashboard.

Apply database migrations from the project root:

```bash
docker compose run --rm --build -v "$PWD:/app" backend alembic upgrade head
```

Check the service:

```bash
curl http://localhost:8000/api/health
```

Stop the stack with `Ctrl+C`, then remove its containers:

```bash
docker compose down
```

The named PostgreSQL, Prometheus, Grafana, and Loki volumes persist local data. Use the local
credentials in `docker-compose.yml` only for development; deployments must provide their own
secrets through the environment.

## Testing

Install the backend development dependencies and AI pipeline dependencies, then run the tests:

```bash
python -m pip install -e ".[dev]"
python -m pip install -r ai/requirements.txt
```

Run only the Neon full-text retriever unit tests:

```bash
python -m pytest tests/ai/test_full_text_retriever.py -q
```

Run all tests and lint checks:

```bash
python -m pytest
ruff check backend saferag shared tests
```

The AI tests do not require a live Neon database. The retriever tests check query parameters,
collection filtering, database-row mapping, and the no-results case. The ingestion tests check
stable chunk IDs, deduplication within one source, and keeping identical text from separate sources.
The RAG pipeline tests build `RagService` with fake models, retrievers, and moderation, and check
the fail-closed and fallback behavior of each query step, conversation isolation, safety review
outcomes, the `RAGInterface` adapter, and the CLI.
At pytest session start, `conftest.py` checks Grafana's health endpoint and the configured OTLP
Collector port. If either is unavailable, RAG telemetry exporters are disabled for that test run
to prevent exporter retry noise. Pytest prints both availability results in its session header.
GitHub Actions installs the AI requirements and runs the test suite for pull requests.

## Development Workflow

Never work on or push directly to `main`. Every change uses a new branch and a pull request.
PR authors review their diff, run relevant tests, and update this README only after the code
and tests are correct. Authors who are not an appropriate CODEOWNER do not merge their own
changes. A CODEOWNER author may self-review and merge after required automated checks pass; no
additional human approval is required.

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) for beginner-friendly commands and the full workflow.
Agents must also follow [`AGENTS.md`](AGENTS.md), including subsystem ownership boundaries and
the mandatory implementation, testing, documentation, and hand-off sequence.

## Current Status

The repository currently contains:

- a working FastAPI application and health endpoint;
- explicit placeholder routes for planned backend capabilities;
- environment-based settings;
- PostgreSQL-ready SQLAlchemy session construction;
- a thin backend RAG integration adapter;
- a standalone Neon-backed AI RAG pipeline with OpenTelemetry traces, metrics, and logs;
- neutral shared RAG contracts;
- a tested SafeRAG decorator architecture;
- local Docker Compose infrastructure for the backend, PostgreSQL, and telemetry services;
- a provisioned Grafana dashboard for RAG pipeline metrics;
- pull request CI for lint and backend/SafeRAG tests; and
- ownership, contribution, PR, and agent-development guidance.

## Current Limitations

- Authentication, authorization, users, conversations, documents, and query behavior are not
  implemented.
- No database domain models, migrations, or repositories have been designed.
- SafeRAG guards are pass-through wiring placeholders and provide no real security detection.
- The standalone AI pipeline is not yet connected to the backend query route.
- The backend query route has not yet been connected to a runtime-supplied SafeRAG instance.
- Backend `backend/observability/` remains an integration point; the standalone AI pipeline has its own telemetry setup.
- CODEOWNERS entries contain placeholders that must be replaced with real GitHub users or teams.
