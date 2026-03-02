"""
LLM client module. Handles communication with any OpenAI-compatible API.

Model-agnostic: works with sqlcoder, Llama, Mistral, or any OpenAI-compatible server.
Swap models by changing LLM_MODEL in .env — no code changes needed.
"""

import json
import re

from openai import AsyncOpenAI

from app.config import settings
from app.prompt import build_messages

_MAX_RESPONSE_LEN = 5000

client = AsyncOpenAI(
    base_url=settings.llm_base_url,
    api_key=settings.llm_api_key,
    timeout=120.0,
)


def _parse_response(raw: str) -> dict:
    """
    Parse the LLM's response into a dict with 'type' and 'response' keys.

    Handles three cases:
    1. Valid JSON with type+response keys (expected behavior)
    2. Raw SQL without JSON wrapper (fallback for simpler models)
    3. Plain text message (fallback for everything else)
    """
    cleaned = raw.strip()
    if len(cleaned) > _MAX_RESPONSE_LEN:
        cleaned = cleaned[:_MAX_RESPONSE_LEN]

    # Strip markdown fences if present (common with many models)
    cleaned = re.sub(r"^```(?:json|sql)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    # Try to extract the first JSON object from the response
    # The model may hallucinate multiple JSON objects; we only want the first one
    first_json_match = re.search(r'\{[^{}]*"type"\s*:\s*"[^"]+"[^{}]*"response"\s*:\s*"[^"]*(?:\\.[^"]*)*"[^{}]*\}', cleaned)
    if not first_json_match:
        # Try a simpler brace-matching approach
        brace_start = cleaned.find('{')
        if brace_start != -1:
            depth = 0
            for i, ch in enumerate(cleaned[brace_start:], brace_start):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        first_json_match = cleaned[brace_start:i+1]
                        break
            if isinstance(first_json_match, str):
                try:
                    parsed = json.loads(first_json_match)
                    if isinstance(parsed, dict) and "type" in parsed and "response" in parsed:
                        resp_type = str(parsed["type"]).lower()
                        if resp_type not in ("sql", "message"):
                            resp_type = "message"
                        return {"type": resp_type, "response": str(parsed["response"])[:_MAX_RESPONSE_LEN]}
                except (json.JSONDecodeError, TypeError, KeyError):
                    pass
    else:
        try:
            parsed = json.loads(first_json_match.group())
            if isinstance(parsed, dict) and "type" in parsed and "response" in parsed:
                resp_type = str(parsed["type"]).lower()
                if resp_type not in ("sql", "message"):
                    resp_type = "message"
                return {"type": resp_type, "response": str(parsed["response"])[:_MAX_RESPONSE_LEN]}
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    # Fallback: detect raw SQL
    upper = cleaned.upper().lstrip()
    if upper.startswith(("SELECT", "WITH")):
        return {"type": "sql", "response": cleaned}

    # Fallback: treat as conversational message
    return {"type": "message", "response": cleaned}


async def generate_response(question: str) -> dict:
    """Send user question to LLM and return parsed response."""
    messages = build_messages(question)
    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        temperature=settings.llm_temperature,
        max_tokens=256,
    )
    raw = response.choices[0].message.content or ""
    return _parse_response(raw)
