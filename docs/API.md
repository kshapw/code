# API Reference

Base URL: `http://localhost:7999`

---

## Endpoints

### `GET /health`

Health check. Returns 200 if the service is running.

**Response:**
```json
{"status": "ok"}
```

---

### `POST /sqlgen`

Convert a natural language question into an MS SQL query with role-based access control.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | Natural language question or greeting |
| `role_id` | integer | Yes | User role: 1, 2, or 3 |
| `username` | string | Yes | System username for role filtering |

**Role IDs:**

| role_id | Role | Filter Column (registration) | Filter Column (scheme) |
|---------|------|------------------------------|----------------------|
| 1 | Labour Inspector | `labour_inspector` | `Labour_Inspector` |
| 2 | Labour Officer | `labour_Officer` | `Labour_Officer` |
| 3 | ALC | `ALC` | `ALC` |

**Response Body:**

| Field | Type | Description |
|-------|------|-------------|
| `query` | string | Original question (echoed back) |
| `type` | string | `"sql"` or `"message"` |
| `response` | string | SQL query or conversational message |
| `role` | string | Human-readable role name |

---

## Response Types

### Type: `sql`

Returned when the question is a data query. The `response` field contains a valid T-SQL SELECT statement with the role filter already injected.

```bash
curl -X POST http://localhost:7999/sqlgen \
  -H 'Content-Type: application/json' \
  -d '{"query": "How many registrations in Dharwad?", "role_id": 1, "username": "LIDharwad@6"}'
```

```json
{
  "query": "How many registrations in Dharwad?",
  "type": "sql",
  "response": "SELECT COUNT(*) AS registration_count FROM dbo.registration_details_ksk_v2 WHERE district = 'DHARWAD' AND labour_inspector = N'LIDharwad@6'",
  "role": "Labour Inspector"
}
```

### Type: `message`

Returned for greetings, out-of-scope questions, or write requests.

**Greeting:**
```bash
curl -X POST http://localhost:7999/sqlgen \
  -H 'Content-Type: application/json' \
  -d '{"query": "hi", "role_id": 1, "username": "LIMysore@2"}'
```

```json
{
  "query": "hi",
  "type": "message",
  "response": "Hello! Welcome to the KBOCWWB Data Assistant. I can help you with reports on worker registrations and welfare schemes...",
  "role": "Labour Inspector"
}
```

**Out-of-scope:**
```json
{
  "query": "what is the weather?",
  "type": "message",
  "response": "I can only help with queries related to construction worker registrations and welfare scheme data...",
  "role": "Labour Inspector"
}
```

**Write request blocked:**
```json
{
  "query": "delete all records",
  "type": "message",
  "response": "I can only generate read-only queries to help you view and analyze data. I cannot modify, delete, or alter any records in the database.",
  "role": "Labour Inspector"
}
```

---

## Error Responses

### 400 Bad Request — Invalid Username

```json
{
  "detail": "Invalid username. Only letters, numbers, @, _, ., #, - and spaces are allowed."
}
```

### 422 Validation Error — Missing/Invalid Fields

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "role_id"],
      "msg": "Value error, role_id must be 1 (Labour Inspector), 2 (Labour Officer), or 3 (ALC)"
    }
  ]
}
```

### 502 Bad Gateway — LLM Unavailable

```json
{
  "detail": "LLM service unavailable"
}
```

Returned when the Ollama server is not reachable. Check that the Ollama container is running and connected to `rag-net`.

---

## Example Queries

### Registration queries

```bash
# Total registrations
{"query": "How many total registrations?", "role_id": 1, "username": "LIDharwad@6"}

# District-wise count
{"query": "Show registration counts by district", "role_id": 2, "username": "LO@Mysore"}

# Gender breakdown
{"query": "How many women registered by district?", "role_id": 3, "username": "ALC@Hubli"}

# Caste breakdown
{"query": "Show SC and ST registrations", "role_id": 1, "username": "LIMysore@2"}

# Time-based
{"query": "How many registrations today?", "role_id": 1, "username": "LIMysore@2"}
{"query": "Show registrations from the last 7 days", "role_id": 1, "username": "LIMysore@2"}
{"query": "How many registrations this month?", "role_id": 1, "username": "LIMysore@2"}
{"query": "Show registrations from current financial year", "role_id": 1, "username": "LIMysore@2"}

# Approval status
{"query": "How many pending applications by district?", "role_id": 1, "username": "LIDharwad@6"}
{"query": "How many draft approved applications?", "role_id": 2, "username": "LO@Dharwad"}

# Registration type
{"query": "How many renewals vs new registrations?", "role_id": 1, "username": "LIMysore@2"}
{"query": "How many online registrations?", "role_id": 1, "username": "LIMysore@2"}
```

### Scheme queries

```bash
# Scheme counts
{"query": "Count total beneficiaries by scheme name", "role_id": 1, "username": "LIMysore@2"}

# Specific scheme
{"query": "How many approved Marriage Assistance?", "role_id": 2, "username": "LO@Mysore"}
{"query": "How many women got Delivery Assistance?", "role_id": 1, "username": "LIMysore@2"}

# Payment status
{"query": "Show payment completed schemes", "role_id": 3, "username": "ALC@Hubli"}
{"query": "How many payments are in progress for Pension Scheme?", "role_id": 1, "username": "LIMysore@2"}

# DBT status
{"query": "Show schemes with BMP success status", "role_id": 1, "username": "LIMysore@2"}
{"query": "List schemes with invalid Aadhaar errors", "role_id": 1, "username": "LIMysore@2"}

# Amounts
{"query": "Show total sanctioned amount by scheme", "role_id": 2, "username": "LO@Mysore"}
```

---

## Interactive Docs

FastAPI auto-generates interactive API docs:

- **Swagger UI**: `http://localhost:7999/docs`
- **ReDoc**: `http://localhost:7999/redoc`
