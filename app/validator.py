"""
SQL validation and correction — anti-hallucination layer.

Catches and corrects LLM-generated SQL that uses wrong table names, column names,
or invalid operations on data types. Uses fuzzy matching to auto-correct typos.

Column definitions match the TRIMMED DDL (PII/unused columns removed per user spec).
"""

import re
from difflib import get_close_matches

# ---------------------------------------------------------------------------
# Known tables (only these two exist)
# ---------------------------------------------------------------------------

VALID_TABLES = {
    "registration_details_ksk_v2",
    "scheme_availed_details_report",
}

# ---------------------------------------------------------------------------
# Column definitions per table — TRIMMED (only queryable columns)
# Type categories: "str", "int", "date", "datetime", "decimal", "bigint"
# ---------------------------------------------------------------------------

REG_COLUMNS: dict[str, str] = {
    "id": "int",
    "gram_panchayat": "str",
    "village_name": "str",
    "Ration_Card_Type": "str",
    "Interstate_Migrant_Worker": "str",
    "Migrat_State_Name": "str",
    "Profession_Name": "str",
    "Qualification": "str",
    "approval_desciption": "str",
    "Employment_Status": "str",
    "Labour_Active_Status": "str",
    "district": "str",
    "taluk": "str",
    "Circle_name": "str",
    "circle_code": "str",
    "NatureOfWork": "str",
    "Martial_Status": "str",
    "Gender": "str",
    "validity_from_date": "date",
    "validity_to_date": "date",
    "Submission_date": "datetime",
    "Regitration_date": "datetime",
    "Caste": "str",
    "Religion": "str",
    "date_of_birth": "date",
    "ApprovalStatus": "str",
    "approved_inspector_username": "str",
    "Approved_by_name": "str",
    "application_no": "str",
    "approved_labour_inspector_name": "str",
    "employer_company_name": "str",
    "employer_nature_of_work": "str",
    "certificate_issuer_type": "str",
    "union_name": "str",
    "labour_inspector": "str",
    "labour_Officer": "str",
    "ALC": "str",
    "registration_type": "str",
    "Freezed_status": "str",
    "row_count": "bigint",
    "is_renewal": "str",
    "registration_location": "str",
    "static_center": "str",
    "certificate_app_added_date": "datetime",
    "onfield_pending": "str",
    "isfieldverificationperformed": "str",
    "onfield_verification_status": "str",
    "sakala_remaining_days": "int",
}

SCHEME_COLUMNS: dict[str, str] = {
    "rluid": "int",
    "district": "str",
    "taluk": "str",
    "gram_panchayat_name": "str",
    "village_area_name": "str",
    "Circle_name": "str",
    "circle_code": "str",
    "Gender": "str",
    "date_of_birth": "date",
    "Scheme_Name": "str",
    "applied_date": "datetime",
    "Onfield_Verificaton_Status": "str",
    "Labour_Registration_Number": "str",
    "validity_from_date": "date",
    "validity_to_date": "date",
    "Approval_Status": "str",
    "Approved_Rejected_By": "str",
    "Action_Date": "datetime",
    "Labour_Inspector": "str",
    "Labour_Officer": "str",
    "ALC": "str",
    "is_kutumba_verified": "int",
    "labour_union_id": "int",
    "certificate_issuer_type": "str",
    "issued_union_name": "str",
    "issuer_name": "str",
    "issuer_designation": "str",
    "issue_date": "date",
    "dbt_status": "str",
    "payment_count": "int",
    "current_payment_month": "int",
    "last_payment_month": "int",
    "kutumba_occupation": "str",
    "payment_status": "str",
    "row_count": "bigint",
    "sanctioned_Amount": "decimal",
    "dbt_xml_sent_file_date": "datetime",
    "dbt_xml_sent_file_name": "str",
    "caste": "str",
    "labour_permanant_state": "str",
    "sakala_remaining_days": "int",
    "registration_location": "str",
    "static_center": "str",
    "Labour_Active_Status": "str",
    "txn_no": "str",
    "txn_date": "date",
    "payment_from_date": "date",
    "payment_to_date": "date",
    "ddo_approval": "str",
    "ddo_approval_date": "date",
    "benificiary_amount": "str",
    "payment_date": "date",
    "bmp_remarks": "str",
    "row_bmp": "bigint",
}

# Merged lookup: lowercase → original case
_ALL_COLUMNS_LOWER: dict[str, str] = {}
for _col in REG_COLUMNS:
    _ALL_COLUMNS_LOWER[_col.lower()] = _col
for _col in SCHEME_COLUMNS:
    _ALL_COLUMNS_LOWER[_col.lower()] = _col

# All original-case column names for fuzzy matching
_ALL_COLUMN_NAMES = sorted(set(REG_COLUMNS.keys()) | set(SCHEME_COLUMNS.keys()))

# Numeric types that support SUM/AVG
NUMERIC_TYPES = {"int", "bigint", "decimal"}
DATE_TYPES = {"date", "datetime"}

# SQL keywords/functions to ignore during column validation
_SQL_KEYWORDS = {
    "select", "from", "where", "and", "or", "not", "in", "is", "null",
    "as", "on", "join", "left", "right", "inner", "outer", "cross",
    "group", "by", "order", "asc", "desc", "having", "top", "distinct",
    "count", "sum", "avg", "min", "max", "case", "when", "then", "else",
    "end", "between", "like", "exists", "all", "any", "union", "except",
    "intersect", "with", "into", "values", "set", "cast", "convert",
    "year", "month", "day", "getdate", "datepart", "datediff", "dateadd",
    "datefromparts", "len", "upper", "lower", "trim", "ltrim", "rtrim",
    "replace", "isnull", "coalesce", "nullif", "over", "partition",
    "row_number", "rank", "dense_rank", "dbo", "nvarchar", "varchar",
    "int", "date", "datetime", "decimal", "bigint", "bit", "float", "n",
}

# ---------------------------------------------------------------------------
# Table name validation
# ---------------------------------------------------------------------------

_TABLE_PATTERN = re.compile(r"dbo\.(\w+)", re.IGNORECASE)


def validate_table_names(sql: str) -> tuple[str, list[str]]:
    """
    Check that all dbo.tablename references use valid table names.
    Returns (corrected_sql, list_of_warnings).
    """
    warnings: list[str] = []
    corrected = sql

    for match in _TABLE_PATTERN.finditer(sql):
        table = match.group(1)
        if table not in VALID_TABLES:
            close = get_close_matches(table, VALID_TABLES, n=1, cutoff=0.5)
            if close:
                corrected = corrected.replace(f"dbo.{table}", f"dbo.{close[0]}")
                warnings.append(f"Corrected table 'dbo.{table}' → 'dbo.{close[0]}'")
            else:
                warnings.append(f"Unknown table 'dbo.{table}'")

    return corrected, warnings


# ---------------------------------------------------------------------------
# Column name validation and correction
# ---------------------------------------------------------------------------

_IDENTIFIER_PATTERN = re.compile(r"\b([A-Za-z_]\w*)\b")


def _get_table_columns(sql: str) -> dict[str, str]:
    """Determine which table's columns to validate against based on SQL content."""
    has_reg = bool(re.search(r"registration_details_ksk_v2", sql, re.IGNORECASE))
    has_scheme = bool(re.search(r"scheme_availed_details_report", sql, re.IGNORECASE))

    if has_scheme and not has_reg:
        return SCHEME_COLUMNS
    if has_reg and not has_scheme:
        return REG_COLUMNS
    # Both or neither — merge
    merged = {}
    merged.update(REG_COLUMNS)
    merged.update(SCHEME_COLUMNS)
    return merged


def validate_column_names(sql: str) -> tuple[str, list[str]]:
    """
    Check that column names in the SQL exist in the target table.
    Fuzzy-corrects misspelled column names.
    Returns (corrected_sql, list_of_warnings).
    """
    warnings: list[str] = []
    corrected = sql
    table_cols = _get_table_columns(sql)
    table_cols_lower = {k.lower(): k for k in table_cols}

    identifiers = set(_IDENTIFIER_PATTERN.findall(sql))

    for ident in identifiers:
        lower = ident.lower()

        # Skip SQL keywords, functions, table names
        if lower in _SQL_KEYWORDS:
            continue
        if lower in {"registration_details_ksk_v2", "scheme_availed_details_report"}:
            continue
        # Skip if it's a known column (case-insensitive)
        if lower in table_cols_lower:
            correct_name = table_cols_lower[lower]
            if ident != correct_name:
                corrected = re.sub(rf"\b{re.escape(ident)}\b", correct_name, corrected)
            continue
        # Skip purely numeric, very short aliases, or common aliases
        if ident.isdigit() or len(ident) <= 2:
            continue
        if lower in {"count", "cnt", "total", "registration_count", "worker_count",
                      "approved_count", "application_count", "pending_count",
                      "total_sanctioned", "total_amount", "total_registrations",
                      "registrations_last_7_days", "registrations_this_month",
                      "total_today_registrations", "registrations_current_financial_year",
                      "sc_count", "migrant_worker_count", "total_beneficiaries",
                      "total_approvals", "scheme_count", "schemes_applied_this_month",
                      "onfield_verification_pending", "application_type"}:
            continue

        # Unknown identifier — try fuzzy match against column names
        close = get_close_matches(ident, _ALL_COLUMN_NAMES, n=1, cutoff=0.7)
        if close:
            corrected = re.sub(rf"\b{re.escape(ident)}\b", close[0], corrected)
            warnings.append(f"Corrected column '{ident}' → '{close[0]}'")

    return corrected, warnings


# ---------------------------------------------------------------------------
# Data type validation
# ---------------------------------------------------------------------------

_SUM_AVG_PATTERN = re.compile(r"\b(SUM|AVG)\s*\(\s*(\w+)\s*\)", re.IGNORECASE)
_DATE_FUNC_PATTERN = re.compile(
    r"\b(YEAR|MONTH|DAY|DATEPART|DATEDIFF|DATEADD)\s*\(\s*(\w+)",
    re.IGNORECASE,
)


def validate_data_types(sql: str) -> list[str]:
    """
    Check that aggregate and date functions are applied to correct column types.
    Returns list of warnings (empty if all valid).
    """
    warnings: list[str] = []
    table_cols = _get_table_columns(sql)
    cols_lower = {k.lower(): v for k, v in table_cols.items()}

    for match in _SUM_AVG_PATTERN.finditer(sql):
        func, col = match.group(1), match.group(2)
        col_type = cols_lower.get(col.lower())
        if col_type and col_type not in NUMERIC_TYPES:
            warnings.append(
                f"{func}({col}) used on '{col_type}' column — expected numeric type"
            )

    for match in _DATE_FUNC_PATTERN.finditer(sql):
        func, col = match.group(1), match.group(2)
        col_type = cols_lower.get(col.lower())
        if col_type and col_type not in DATE_TYPES:
            warnings.append(
                f"{func}({col}) used on '{col_type}' column — expected date/datetime type"
            )

    return warnings


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------

def validate_sql(sql: str) -> tuple[str, list[str]]:
    """
    Run all validations on the SQL. Returns (corrected_sql, all_warnings).
    Corrections are applied automatically. Warnings are informational.
    """
    all_warnings: list[str] = []

    sql, table_warnings = validate_table_names(sql)
    all_warnings.extend(table_warnings)

    sql, col_warnings = validate_column_names(sql)
    all_warnings.extend(col_warnings)

    type_warnings = validate_data_types(sql)
    all_warnings.extend(type_warnings)

    return sql, all_warnings
