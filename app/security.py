"""
Server-side security: read-only enforcement, role-based filter injection,
input sanitization, prompt injection defense, complex SQL blocking.

All role filtering is pure code — no LLM involvement.
"""

import re
import unicodedata

# ---------------------------------------------------------------------------
# Unicode normalization (fixes CRITICAL #3, HIGH #7)
# ---------------------------------------------------------------------------

# Zero-width and control characters to strip
_DANGEROUS_UNICODE = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f\u202a-\u202e\ufeff\u00ad\u2060\u2061-\u2064\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
)


def normalize_text(text: str) -> str:
    """Normalize Unicode and strip dangerous invisible characters."""
    text = unicodedata.normalize("NFKD", text)
    text = _DANGEROUS_UNICODE.sub("", text)
    return text


# ---------------------------------------------------------------------------
# Prompt injection detection (fixes CRITICAL #2)
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = re.compile(
    r"(?:ignore|forget|disregard|override|bypass)\s+(?:previous|all|above|prior|system)\s+(?:instructions|rules|prompts|context)"
    r"|you\s+are\s+(?:now\s+)?(?:an?\s+)?(?:admin|unrestricted|jailbroken|unfiltered)"
    r"|(?:system|assistant)\s*(?:prompt|message)\s*:"
    r"|pretend\s+(?:you\s+are|to\s+be)"
    r"|(?:enter|switch\s+to|activate)\s+(?:admin|developer|debug|god)\s+mode"
    r"|do\s+not\s+(?:follow|obey)\s+(?:your|the)\s+(?:rules|instructions)"
    r"|respond\s+(?:without|ignoring)\s+(?:restrictions|rules|guidelines)",
    re.IGNORECASE,
)

INJECTION_REJECTION = (
    "I'm sorry, I can only help with data queries about worker registrations "
    "and welfare schemes. Could you rephrase your question?"
)


def detect_prompt_injection(query: str) -> bool:
    """Return True if the query contains prompt injection patterns."""
    return bool(_INJECTION_PATTERNS.search(query))


# ---------------------------------------------------------------------------
# Role → column mapping (exact column names per table)
# ---------------------------------------------------------------------------

ROLE_COLUMN_MAP = {
    1: {
        "registration_details_ksk_v2": "labour_inspector",
        "scheme_availed_details_report": "Labour_Inspector",
    },
    2: {
        "registration_details_ksk_v2": "labour_Officer",
        "scheme_availed_details_report": "Labour_Officer",
    },
    3: {
        "registration_details_ksk_v2": "ALC",
        "scheme_availed_details_report": "ALC",
    },
}

ROLE_LABELS = {1: "Labour Inspector", 2: "Labour Officer", 3: "ALC"}

# ---------------------------------------------------------------------------
# Read-only enforcement (fixes CRITICAL #3 with normalize_text)
# ---------------------------------------------------------------------------

_BLOCKED_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|EXEC|EXECUTE|MERGE|CREATE|"
    r"GRANT|REVOKE|DENY|BACKUP|RESTORE|SHUTDOWN|DBCC|OPENROWSET|OPENDATASOURCE|"
    r"xp_cmdshell|sp_executesql|sp_adduser|sp_dropuser|BULK\s+INSERT)\b",
    re.IGNORECASE,
)

READONLY_REJECTION = (
    "I can only generate read-only queries to help you view and analyze data. "
    "I cannot modify, delete, or alter any records in the database."
)


def strip_sql_comments(sql: str) -> str:
    """Remove single-line (--) and block (/* */) comments from SQL."""
    result = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
    result = re.sub(r"/\*.*?\*/", "", result, flags=re.DOTALL)
    return result


def is_write_query(sql: str) -> bool:
    """Return True if the SQL contains any write/destructive operation."""
    normalized = normalize_text(sql)
    return bool(_BLOCKED_SQL.search(strip_sql_comments(normalized)))


# ---------------------------------------------------------------------------
# Complex SQL detection (fixes CRITICAL #1, #5)
# ---------------------------------------------------------------------------

_COMPLEX_SQL = re.compile(
    r"\bUNION\b|\bJOIN\b|\bINTO\b|\bEXISTS\s*\("
    r"|\bWITH\s+\w+\s+AS\s*\(",
    re.IGNORECASE,
)

# Subquery detection: SELECT inside parentheses (but not in IN (...) with values)
_SUBQUERY = re.compile(r"\(\s*SELECT\b", re.IGNORECASE)

COMPLEX_SQL_REJECTION = (
    "I can only generate simple data queries. Could you rephrase your question "
    "so I can create a straightforward report for you?"
)


def is_complex_query(sql: str) -> bool:
    """Return True if SQL contains UNION, JOIN, CTE, or subqueries."""
    stripped = strip_sql_comments(sql)
    if _COMPLEX_SQL.search(stripped):
        return True
    if _SUBQUERY.search(stripped):
        return True
    return False


# ---------------------------------------------------------------------------
# Input sanitization
# ---------------------------------------------------------------------------

_SAFE_USERNAME = re.compile(r"^[a-zA-Z0-9@_. ]+$")


def validate_username(username: str) -> bool:
    """Check username contains only safe characters. Rejects null bytes and unicode tricks."""
    normalized = normalize_text(username)
    if normalized != username:
        return False
    return bool(_SAFE_USERNAME.match(username)) and 1 <= len(username) <= 200


def escape_sql_string(value: str) -> str:
    """Escape single quotes for safe SQL string interpolation."""
    return value.replace("'", "''")


# ---------------------------------------------------------------------------
# Role-based WHERE clause injection (pure code, no LLM)
# ---------------------------------------------------------------------------

_TABLE_REG = re.compile(r"dbo\.registration_details_ksk_v2", re.IGNORECASE)
_TABLE_SCHEME = re.compile(r"dbo\.scheme_availed_details_report", re.IGNORECASE)

_INSERTION_POINT = re.compile(
    r"\b(GROUP\s+BY|ORDER\s+BY|HAVING)\b",
    re.IGNORECASE,
)


def _get_role_column(sql: str, role_id: int) -> str:
    """Determine the correct column name based on which table the query uses."""
    mapping = ROLE_COLUMN_MAP[role_id]
    has_reg = bool(_TABLE_REG.search(sql))
    has_scheme = bool(_TABLE_SCHEME.search(sql))

    if has_scheme and not has_reg:
        return mapping["scheme_availed_details_report"]
    return mapping["registration_details_ksk_v2"]


def inject_role_filter(sql: str, role_id: int, username: str) -> str:
    """
    Inject a WHERE/AND clause for role-based access control.

    If the SQL already has a WHERE clause, appends AND.
    Otherwise, inserts WHERE before GROUP BY/ORDER BY/HAVING or at end.
    """
    column = _get_role_column(sql, role_id)
    safe_username = escape_sql_string(username)
    filter_expr = f"{column} = N'{safe_username}'"

    trimmed = sql.rstrip().rstrip(";")

    has_where = bool(re.search(r"\bWHERE\b", trimmed, re.IGNORECASE))

    keyword = "AND" if has_where else "WHERE"

    match = _INSERTION_POINT.search(trimmed)
    if match:
        pos = match.start()
        return f"{trimmed[:pos].rstrip()} {keyword} {filter_expr} {trimmed[pos:]}"

    return f"{trimmed} {keyword} {filter_expr}"
