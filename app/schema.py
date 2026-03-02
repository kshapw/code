import unicodedata
import re

from pydantic import BaseModel, field_validator

# Strip zero-width and control characters
_DANGEROUS_CHARS = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f\u202a-\u202e\ufeff\u00ad\u2060\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
)


class SQLGenRequest(BaseModel):
    query: str
    role_id: int
    username: str

    @field_validator("query")
    @classmethod
    def query_valid(cls, v: str) -> str:
        v = unicodedata.normalize("NFKD", v)
        v = _DANGEROUS_CHARS.sub("", v)
        v = v.strip()
        if not v:
            raise ValueError("query cannot be empty")
        if len(v) > 2000:
            raise ValueError("query too long (max 2000 characters)")
        return v


class SQLGenResponse(BaseModel):
    query: str
    type: str       # "sql" or "message"
    response: str   # SQL query or conversational message
    role: str       # Human-readable role label
