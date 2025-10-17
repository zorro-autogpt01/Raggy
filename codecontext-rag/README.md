# CodeContext RAG

An intelligent code repository analysis system that identifies relevant files for implementing new features using Retrieval-Augmented Generation (RAG).

This repository contains a FastAPI-based backend implementing the initial API surface and scaffolding described in the project documentation and OpenAPI spec.

## Quickstart

- Python: 3.10+
- OS: Linux/macOS/Windows

### 1) Create virtual environment

```
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
```

### 2) Install dependencies

```
pip install -U pip
pip install -r requirements.txt
```

Note: Some optional dependencies (tree-sitter, lancedb, pygraphviz) may require system packages. You can comment them out in `requirements.txt` if you only want to run the API skeleton.

### 3) Configure environment

Copy `.env.example` to `.env` and adjust values as needed (or set environment variables directly).

### 4) Run the API

```
uvicorn src.codecontext.main:app --reload --port 8000
```

Open: http://localhost:8000/docs

### 5) Run tests
## Frontend (optional UI)

A minimal React + Vite UI is provided under `frontend/` to exercise the API.

### Run locally

- Install deps:
```
cd frontend && npm install
```
- Start dev server:
```
npm run dev
```
- Open: http://localhost:5173

Set API base via env:
```
VITE_API_BASE=http://localhost:8000 npm run dev
```

### Docker Compose

```
docker compose up --build
```
- API: http://localhost:8000
- Web: http://localhost:5173


```
pytest -q
```

## What's implemented (MVP skeleton)

- Health check endpoint
- Repository registration/listing/get/delete and indexing job skeleton (in-memory)
- Recommendations endpoint with stubbed ranking and session tracking
- Feedback and refine endpoints (stubs)
- Dependency graph endpoint (stub)
- Impact analysis endpoint (stub)
- Consistent response envelope with metadata and X-Request-Id header
- Basic API key auth (optional via env)
- Modular project structure ready for core engines (parser, embedder, graph, ranker)

## Next steps
## Docker

Build and run locally:

```
docker compose up --build
```

Or using plain Docker:

```
docker build -t codecontext-rag:dev .
docker run -p 8000:8000 codecontext-rag:dev
```


- Wire core engines to real implementations (Tree-sitter, LanceDB, NetworkX, GitPython)
- Replace in-memory stores with persistent stores
- Add caching (Redis) and background workers (Celery/RQ) for indexing
- Implement real ranking logic and confidence scoring
- Expand tests (unit, integration, performance)

## License

MIT
## Docker
