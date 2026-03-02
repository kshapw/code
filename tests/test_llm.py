"""Tests for llm.py — LLM response parsing (model-agnostic)."""

from app.llm import _parse_response


# --- Valid JSON responses ---


def test_parse_valid_sql_json():
    raw = '{"type": "sql", "response": "SELECT COUNT(*) FROM dbo.registration_details_ksk_v2"}'
    result = _parse_response(raw)
    assert result["type"] == "sql"
    assert "SELECT" in result["response"]


def test_parse_valid_message_json():
    raw = '{"type": "message", "response": "Hello! How can I help?"}'
    result = _parse_response(raw)
    assert result["type"] == "message"
    assert "Hello" in result["response"]


def test_parse_normalizes_type_to_lowercase():
    raw = '{"type": "SQL", "response": "SELECT 1"}'
    result = _parse_response(raw)
    assert result["type"] == "sql"


def test_parse_unknown_type_becomes_message():
    raw = '{"type": "unknown", "response": "something"}'
    result = _parse_response(raw)
    assert result["type"] == "message"


# --- Markdown fence stripping ---


def test_parse_json_with_json_fences():
    raw = '```json\n{"type": "sql", "response": "SELECT 1"}\n```'
    result = _parse_response(raw)
    assert result["type"] == "sql"
    assert result["response"] == "SELECT 1"


def test_parse_json_with_sql_fences():
    raw = '```sql\nSELECT 1\n```'
    result = _parse_response(raw)
    assert result["type"] == "sql"


# --- Fallbacks for simpler models ---


def test_parse_fallback_raw_sql():
    raw = "SELECT COUNT(*) FROM dbo.registration_details_ksk_v2;"
    result = _parse_response(raw)
    assert result["type"] == "sql"
    assert "SELECT" in result["response"]


def test_parse_fallback_with_query():
    raw = "WITH cte AS (SELECT 1) SELECT * FROM cte"
    result = _parse_response(raw)
    assert result["type"] == "sql"


def test_parse_fallback_message():
    raw = "I can only help with KBOCWWB data queries."
    result = _parse_response(raw)
    assert result["type"] == "message"


def test_parse_strips_whitespace():
    raw = '  {"type": "sql", "response": "SELECT 1"}  '
    result = _parse_response(raw)
    assert result["type"] == "sql"
