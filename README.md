# CardioSmart

## Overview

CardioSmart is a Python backend project for a cardiovascular application. This repository
currently provides a production-oriented starting point: a FastAPI modular monolith,
PostgreSQL session infrastructure, a neutral RAG contract, and an independent SafeRAG wrapper.

The repository contains three separately owned areas. The backend team owns the application
and its integration boundary. The AI team owns the future RAG implementation. SafeRAG sits
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
├── ai/                      AI-team-owned area; intentionally empty
├── saferag/                 Independent RAG security wrapper
├── shared/contracts/        Coordinated cross-team data contracts
├── infra/docker/            Backend container definition
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

`ai/` belongs entirely to the AI team and is intentionally empty after this bootstrap. No RAG
interfaces, ingestion, chunking, embeddings, retrieval, reranking, generation, critic models,
vector storage, configuration, or tests have been created there.

The AI team can build independently against the coordinated contract in
`shared/contracts/rag.py`. Changes to that contract require backend and AI codeowner review.

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

Build and start the FastAPI backend and PostgreSQL:

```bash
docker compose up --build
```

Check the service:

```bash
curl http://localhost:8000/api/health
```

Stop the stack with `Ctrl+C`, then remove its containers:

```bash
docker compose down
```

The named PostgreSQL volume persists local data. Use the local credentials in
`docker-compose.yml` only for development; deployments must provide their own secrets through
the environment.

## Testing

Install development dependencies, then run lint and all backend-owned tests:

```bash
ruff check .
pytest
```

The seven current tests verify that the FastAPI app starts, the health route responds, and SafeRAG
enforces its wrapper order and blocking semantics using a contract-compatible fake RAG. There
are no AI-team tests because `ai/` is intentionally empty.

GitHub Actions runs the same lint and test commands for pull requests.

## Development Workflow

Never work on or push directly to `main`. Every change uses a new branch and a pull request.
PR authors review their diff, run relevant tests, and update this README only after the code
and tests are correct. The appropriate CODEOWNER reviews and merges the PR; authors do not
merge their own changes.

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
- neutral shared RAG contracts;
- a tested SafeRAG decorator architecture;
- local Docker Compose infrastructure for the backend and PostgreSQL;
- pull request CI for lint and backend/SafeRAG tests; and
- ownership, contribution, PR, and agent-development guidance.

## Current Limitations

- Authentication, authorization, users, conversations, documents, and query behavior are not
  implemented.
- No database domain models, migrations, or repositories have been designed.
- SafeRAG guards are pass-through wiring placeholders and provide no real security detection.
- No RAG implementation is present; `ai/` is reserved for the AI team.
- The backend query route has not yet been connected to a runtime-supplied SafeRAG instance.
- Metrics, tracing, background execution, and audit storage are integration points only.
- CODEOWNERS entries contain placeholders that must be replaced with real GitHub users or teams.
