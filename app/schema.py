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

    @field_validator("role_id")
    @classmethod
    def role_id_valid(cls, v: int) -> int:
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError("role_id must be an integer")
        if v not in (1, 2, 3):
            raise ValueError("role_id must be 1 (Labour Inspector), 2 (Labour Officer), or 3 (ALC)")
        return v

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("username cannot be empty")
        if len(v) > 200:
            raise ValueError("username too long (max 200 characters)")
        return v


class SQLGenResponse(BaseModel):
    query: str
    type: str       # "sql" or "message"
    response: str   # SQL query or conversational message
    role: str       # Human-readable role label
