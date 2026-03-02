# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Metabase is a production-grade FastAPI service that converts natural language questions into valid MS SQL (T-SQL) queries for the Karnataka KBOCWWB (Building & Other Construction Workers Welfare Board) database. It handles greetings, rejects out-of-scope questions, enforces read-only SQL, validates against hallucinated table/column names, and injects role-based access control filters.

The LLM backend is Ollama with sqlcoder (or any OpenAI-compatible server). Model-agnostic — swap models by changing `LLM_MODEL` in environment.

## Commands

```bash
# Local development
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 7999
pytest
pytest tests/test_security.py
pytest tests/test_validator.py
ruff check app/ tests/
ruff format app/ tests/

# Docker (production)
docker compose build
docker compose up -d
docker compose logs -f sql-rag-api
```

## API

**`POST /sqlgen`** (port 7999)
```json
{
  "query": "How many registrations in Dharwad?",
  "role_id": 1,
  "username": "LIDharwad@6"
}
```

Response:
```json
{
  "query": "How many registrations in Dharwad?",
  "type": "sql",
  "response": "SELECT COUNT(*) AS registration_count FROM dbo.registration_details_ksk_v2 WHERE district = 'DHARWAD' AND labour_inspector = N'LIDharwad@6'",
  "role": "Labour Inspector"
}
```

**Role IDs**: 1 = Labour Inspector, 2 = Labour Officer, 3 = ALC

## Architecture

```
app/
├── main.py        # FastAPI app: POST /sqlgen, GET /health, CORS, pipeline orchestration
├── config.py      # Settings from env vars (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL)
├── llm.py         # AsyncOpenAI client, _parse_response() with 3-tier fallback
├── prompt.py      # System prompt, trimmed DDL, district/scheme/categorical mappings, 50+ few-shot examples
├── schema.py      # SQLGenRequest (with validators), SQLGenResponse
├── security.py    # Read-only enforcement, role filter injection, input sanitization
└── validator.py   # Anti-hallucination: table/column name validation + fuzzy correction, data type checks
```

**Pipeline**: `POST /sqlgen` → validate input (schema.py) → validate username (security.py) → LLM generates SQL (llm.py + prompt.py) → block write queries (security.py) → validate & correct table/column names (validator.py) → inject role WHERE filter (security.py) → return

**Key design**: Role-based filtering is pure code in `security.py` — NOT done by the LLM. The LLM generates clean SQL, then `inject_role_filter()` deterministically adds `AND labour_inspector = N'username'` (or `labour_Officer`/`ALC` based on role_id).

## Docker Deployment

The app deploys as container `sql-rag-api` on port 7999, connecting to Ollama via the `rag-net` Docker network.

```
docker compose up -d        # Start (builds if needed)
docker compose down          # Stop
docker compose up -d --build # Rebuild and start
```

- **Ollama connection**: `http://ollama:11434/v1` (container name on rag-net)
- **Hot reload**: Volume mount `./app:/app/app` enables code changes without rebuild
- **Health check**: `curl http://localhost:7999/health`

## LLM Configuration

| Variable | Docker (default) | Local dev |
|----------|-----------------|-----------|
| `LLM_BASE_URL` | `http://ollama:11434/v1` | `http://localhost:11434/v1` |
| `LLM_API_KEY` | `ollama` | `ollama` |
| `LLM_MODEL` | `sqlcoder` | `sqlcoder` |

Docker env vars are set in `docker-compose.yml`. Local dev uses `.env` file.

## Key Files to Modify

- **Prompt/schema/examples**: `app/prompt.py` — `SCHEMA_DDL`, `FEW_SHOT_EXAMPLES`, `DISTRICT_NAMES`, `SCHEME_NAMES`, `CATEGORICAL_VALUES`
- **Column definitions for validator**: `app/validator.py` — `REG_COLUMNS`, `SCHEME_COLUMNS` (must match trimmed DDL in prompt.py)
- **Role mappings**: `app/security.py` — `ROLE_COLUMN_MAP`, `ROLE_LABELS`
- **Adding roles**: Update `ROLE_COLUMN_MAP` in `security.py` and `role_id_valid` validator in `schema.py`
- **LLM parameters**: `app/llm.py` (temperature, max_tokens) or `app/config.py`
- **Blocked SQL keywords**: `app/security.py` — `_BLOCKED_SQL` regex
