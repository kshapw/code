import json
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _make_mock_llm(response_dict: dict):
    """Create a mock LLM client that returns the given JSON response."""
    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.choices = [AsyncMock()]
    mock_response.choices[0].message.content = json.dumps(response_dict)
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.fixture
def mock_llm_sql():
    """Mock LLM that returns a SELECT query."""
    response = {
        "type": "sql",
        "response": "SELECT COUNT(*) AS count FROM dbo.registration_details_ksk_v2 WHERE district = 'DHARWAD'",
    }
    with patch("app.llm.client", _make_mock_llm(response)):
        yield


@pytest.fixture
def mock_llm_scheme_sql():
    """Mock LLM that returns a scheme table query."""
    response = {
        "type": "sql",
        "response": "SELECT COUNT(*) AS count FROM dbo.scheme_availed_details_report WHERE Approval_Status = 'Pending'",
    }
    with patch("app.llm.client", _make_mock_llm(response)):
        yield


@pytest.fixture
def mock_llm_message():
    """Mock LLM that returns a greeting message."""
    response = {
        "type": "message",
        "response": "Hello! Welcome to the KBOCWWB Data Assistant.",
    }
    with patch("app.llm.client", _make_mock_llm(response)):
        yield


@pytest.fixture
def mock_llm_write():
    """Mock LLM that returns a dangerous write query (should be blocked)."""
    response = {
        "type": "sql",
        "response": "DELETE FROM dbo.registration_details_ksk_v2 WHERE id = 1",
    }
    with patch("app.llm.client", _make_mock_llm(response)):
        yield
