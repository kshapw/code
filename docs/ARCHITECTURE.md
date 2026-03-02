# Architecture

## Overview

Metabase converts natural language questions into valid MS SQL (T-SQL) queries for the KBOCWWB database. It runs as a FastAPI service inside Docker, connecting to an Ollama LLM server on the same network.

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────┐
│   Frontend   │────▶│  Metabase API   │────▶│   Ollama     │
│  (any client)│◀────│  (port 7999)    │◀────│  (sqlcoder)  │
└──────────────┘     └─────────────────┘     └──────────────┘
                              │
                     ┌────────▼────────┐
                     │   MS SQL DB     │
                     │ (query target)  │
                     └─────────────────┘
```

The API does NOT execute SQL. It generates SQL queries that the frontend sends to the database separately.

---

## Request Pipeline

Every request to `POST /sqlgen` passes through 6 stages in order:

```
Request ──▶ [1] Input Validation ──▶ [2] Username Sanitization ──▶ [3] LLM Generation
                                                                          │
Response ◀── [6] Role Filter Injection ◀── [5] Anti-Hallucination ◀── [4] Write Blocking
```

### Stage 1: Input Validation (`schema.py`)

Pydantic validators run automatically on the incoming JSON:

```json
{
  "query": "How many registrations in Dharwad?",  // must be non-empty string
  "role_id": 1,                                    // must be 1, 2, or 3
  "username": "LIDharwad@6"                        // must be non-empty string
}
```

- Empty `query` → 422 error
- `role_id` not in (1, 2, 3) → 422 error
- Empty `username` → 422 error

### Stage 2: Username Sanitization (`security.py`)

The username is checked against a regex whitelist before it touches any SQL:

```
Allowed characters: a-z A-Z 0-9 @ _ . # - space
Maximum length: 200 characters
```

Usernames like `'; DROP TABLE --` are rejected with a 400 error. This prevents SQL injection at the input boundary, before any SQL is generated.

### Stage 3: LLM Generation (`llm.py` + `prompt.py`)

The user's question is sent to the LLM (Ollama sqlcoder) with a system prompt containing:

- Trimmed DDL for both tables (only queryable columns, ~47 + ~52 columns)
- All 31 district names with alias mappings (Bengaluru → BANGALORE URBAN, etc.)
- All 17 scheme names with informal aliases (pension → Pension Scheme, etc.)
- Exact distinct values for every categorical column (from actual DB queries)
- 50+ few-shot examples from curated `examples.json`
- 16 SQL rules (read-only, exact column names, T-SQL syntax, etc.)

The LLM returns JSON:
```json
{"type": "sql", "response": "SELECT COUNT(*) ..."}
```
or
```json
{"type": "message", "response": "Hello! How can I help?"}
```

The `_parse_response()` function has a 3-tier fallback:
1. Parse as JSON → extract type + response
2. If raw text starts with SELECT/WITH → treat as SQL
3. Otherwise → treat as conversational message

This makes the system work with any model, even ones that don't follow JSON instructions perfectly.

### Stage 4: Write Blocking (`security.py`)

If the LLM returned SQL, the response is scanned for dangerous keywords:

```
Blocked: INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, EXEC, EXECUTE,
         MERGE, CREATE, GRANT, REVOKE, DENY, BACKUP, RESTORE, SHUTDOWN,
         DBCC, OPENROWSET, OPENDATASOURCE, xp_cmdshell, sp_executesql,
         BULK INSERT
```

SQL comments (`--` and `/* */`) are stripped first to prevent bypass via comment injection.

If a write query is detected, the SQL is replaced with a polite rejection message. The dangerous SQL never reaches the caller.

### Stage 5: Anti-Hallucination Validation (`validator.py`)

The SQL passes through three validators:

**Table Name Validation**
- Only two tables exist: `dbo.registration_details_ksk_v2` and `dbo.scheme_availed_details_report`
- Any other `dbo.xxx` reference is fuzzy-matched (cutoff 0.5) and auto-corrected
- Example: `dbo.registration_details_ksk` → corrected to `dbo.registration_details_ksk_v2`

**Column Name Validation**
- Every identifier in the SQL is checked against the known column list for the target table
- Misspelled columns are fuzzy-matched (cutoff 0.7) and auto-corrected
- Wrong casing is silently fixed (e.g., `DISTRICT` → `district`)
- Example: `Approval_Staus` → corrected to `Approval_Status`

**Data Type Validation**
- `SUM()` / `AVG()` only allowed on numeric columns (`int`, `bigint`, `decimal`)
- `YEAR()` / `MONTH()` / `DAY()` only allowed on date/datetime columns
- Violations are logged as warnings

All corrections are automatic. Warnings are logged server-side for monitoring.

### Stage 6: Role Filter Injection (`security.py`)

This is the final step — pure code, no LLM involvement. Based on `role_id` and `username`:

| role_id | Role | registration table column | scheme table column |
|---------|------|--------------------------|-------------------|
| 1 | Labour Inspector | `labour_inspector` | `Labour_Inspector` |
| 2 | Labour Officer | `labour_Officer` | `Labour_Officer` |
| 3 | ALC | `ALC` | `ALC` |

The system detects which table the query references and injects the correct WHERE/AND clause:

```sql
-- Before injection:
SELECT COUNT(*) AS count FROM dbo.registration_details_ksk_v2 WHERE district = 'DHARWAD'

-- After injection (role_id=1, username=LIDharwad@6):
SELECT COUNT(*) AS count FROM dbo.registration_details_ksk_v2 WHERE district = 'DHARWAD' AND labour_inspector = N'LIDharwad@6'
```

Key details:
- Uses `N'value'` for Unicode-safe string literals
- Single quotes in usernames are escaped (`O'Brien` → `N'O''Brien'`)
- Insertion point is before GROUP BY / ORDER BY / HAVING (not after)
- Column name casing differs between tables — the system handles this automatically

---

## Module Breakdown

```
app/
├── __init__.py      # Package marker
├── main.py          # FastAPI app, endpoint definitions, pipeline orchestration
├── config.py        # Environment config via pydantic-settings
├── llm.py           # OpenAI SDK client, response parsing with 3-tier fallback
├── prompt.py        # System prompt: DDL, districts, schemes, categorical values, few-shots
├── schema.py        # Pydantic request/response models with field validators
├── security.py      # Read-only enforcement, role injection, username sanitization
└── validator.py     # Anti-hallucination: table/column/type validation with fuzzy correction
```

### Dependency Graph

```
main.py
├── llm.py
│   ├── config.py
│   └── prompt.py
├── schema.py
├── security.py
└── validator.py
```

No circular dependencies. Each module has a single responsibility.

---

## Database Schema

Two MS SQL tables in `Reports_Metabase.dbo`:

### `registration_details_ksk_v2` (47 queryable columns)
Worker registration records. Key columns:
- `district`, `taluk`, `Circle_name` — geography
- `Gender`, `Caste`, `Religion` — demographics
- `ApprovalStatus` — workflow (Approved, Pending, Rejected, Draft Approved, etc.)
- `registration_type`, `is_renewal` — registration classification
- `Labour_Active_Status` — ACTIVE, BUFFER, INACTIVE
- `certificate_app_added_date` — used for time-based queries (today, this week, this month)
- `labour_inspector`, `labour_Officer`, `ALC` — role-based access control columns

### `scheme_availed_details_report` (52 queryable columns)
Welfare scheme application and payment records. Key columns:
- `Scheme_Name` — 17 schemes (Pension, Marriage Assistance, Delivery Assistance, etc.)
- `Approval_Status` — 10 statuses including Forwarded, Transferred
- `payment_status` — IN PROGRESS, PAYMENT COMPLETED
- `dbt_status` — 15 DBT payment pipeline statuses
- `sanctioned_Amount` — only numeric column for SUM/AVG
- `Labour_Inspector`, `Labour_Officer`, `ALC` — role columns (capital L, differs from registration table)

Note: ~50 PII/unused columns (names, addresses, Aadhaar, bank details) are excluded from the DDL sent to the LLM. They are not in the prompt and not in the validator's column list.

---

## Docker Architecture

```
┌─────────────────────────────────────────────┐
│              Docker Host (GPU Server)        │
│                                             │
│  ┌─────────────────┐   ┌────────────────┐  │
│  │  sql-rag-api    │   │    ollama       │  │
│  │  (port 7999)    │──▶│  (port 11434)  │  │
│  │  python:3.10    │   │  sqlcoder 4GB  │  │
│  └────────┬────────┘   └────────────────┘  │
│           │              rag-net network    │
│  ┌────────▼────────┐                       │
│  │  Volume mount   │                       │
│  │  ./app:/app/app │                       │
│  └─────────────────┘                       │
└─────────────────────────────────────────────┘
```

- Both containers share the `rag-net` Docker network
- Metabase reaches Ollama at `http://ollama:11434/v1` (container name resolution)
- Volume mount enables hot-reload: edit `app/*.py` → changes reflect immediately without rebuild
- Health check pings `/health` every 30s, restarts after 3 failures

---

## Security Layers (Defense in Depth)

| Layer | Module | What It Does |
|-------|--------|-------------|
| 1. Input validation | `schema.py` | Reject empty/invalid fields before processing |
| 2. Username sanitization | `security.py` | Regex whitelist blocks SQL injection chars |
| 3. Prompt guardrails | `prompt.py` | System prompt + few-shots instruct read-only behavior |
| 4. Write blocking | `security.py` | Regex blocks 22 dangerous SQL keywords after stripping comments |
| 5. Anti-hallucination | `validator.py` | Fuzzy-correct wrong table/column names, flag wrong data types |
| 6. Role injection | `security.py` | Deterministic WHERE clause — no LLM involvement |
| 7. CORS | `main.py` | `allow_credentials=False`, methods limited to GET/POST |

Layers 1-2 run before the LLM. Layers 3-6 run after. Even if the LLM is jailbroken, layers 4+5+6 catch the output.

---

## Model Swapping

The LLM is configured via 3 environment variables:

```
LLM_BASE_URL=http://ollama:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=sqlcoder
```

To switch models, change `LLM_MODEL` in `docker-compose.yml`:

```yaml
environment:
  - LLM_MODEL=devstral:24b     # larger, more accurate
  # or
  - LLM_MODEL=sqlcoder          # smaller, faster
```

Any OpenAI-compatible server works (vLLM, TGI, etc.) — just change `LLM_BASE_URL`.
