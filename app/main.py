"""
Metabase API — Natural language to MS SQL query converter.

Production endpoint: POST /sqlgen
Pipeline: validate → sanitize → LLM → block writes → block complex SQL → validate SQL → inject role → return
"""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.llm import generate_response
from app.schema import SQLGenRequest, SQLGenResponse
from app.security import (
    COMPLEX_SQL_REJECTION,
    INJECTION_REJECTION,
    READONLY_REJECTION,
    ROLE_LABELS,
    detect_prompt_injection,
    inject_role_filter,
    is_complex_query,
    is_write_query,
    validate_username,
)
from app.validator import validate_sql

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Metabase",
    description="Natural language to MS SQL query converter for KBOCWWB",
    version="1.0.0",
)
app.state.limiter = limiter

origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Too many requests. Please try again later."})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def _redact(value: str) -> str:
    """Redact a value for safe logging."""
    if len(value) <= 3:
        return "***"
    return value[:3] + "***"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/sqlgen", response_model=SQLGenResponse)
@limiter.limit("30/minute")
async def sqlgen(request: Request, req: SQLGenRequest):
    role_label = ROLE_LABELS.get(req.role_id, f"Role {req.role_id}")
    logger.info("sqlgen | role=%s user=%s", role_label, _redact(req.username))

    # Detect prompt injection before sending to LLM
    if detect_prompt_injection(req.query):
        return SQLGenResponse(
            type="message",
            sql=INJECTION_REJECTION,
            valid=False,
        )

    try:
        result = await generate_response(req.query)
    except Exception as e:
        logger.error("LLM request failed for role=%s: %s", role_label, str(e), exc_info=True)
        raise HTTPException(status_code=502, detail="LLM service unavailable")

    # If LLM returned SQL, apply security + validation pipeline
    if result["type"] == "sql":
        sql = result["response"]

        # Block write queries
        if is_write_query(sql):
            return SQLGenResponse(
                type="message",
                sql=READONLY_REJECTION,
                valid=False,
            )

        # Block complex SQL (UNION, JOIN, CTE, subqueries)
        if is_complex_query(sql):
            return SQLGenResponse(
                type="message",
                sql=COMPLEX_SQL_REJECTION,
                valid=False,
            )

        # Validate and auto-correct table/column names (anti-hallucination)
        sql, warnings = validate_sql(sql)
        if warnings:
            logger.warning("SQL corrections: %s", "; ".join(warnings))

        # Inject role-based WHERE filter (pure code, no LLM)
        sql = inject_role_filter(sql, req.role_id, req.username)
        result["response"] = sql

    return SQLGenResponse(
        type=result["type"],
        sql=result["response"],
        valid=result["type"] == "sql",
    )
