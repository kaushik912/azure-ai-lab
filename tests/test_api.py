import os

os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://x.openai.azure.com")
os.environ.setdefault("AZURE_SEARCH_ENDPOINT", "https://x.search.windows.net")

from fastapi.testclient import TestClient

from app.agent import State, build_messages
from app.main import app


def test_healthz():
    assert TestClient(app).get("/healthz").json() == {"status": "ok"}


def test_ask_validates_input():
    assert TestClient(app).post("/ask", json={"question": ""}).status_code == 422


def test_build_messages_grounds_on_context():
    state: State = {"question": "q", "context": [{"source": "a.pdf", "content": "hello"}]}
    msgs = build_messages(state)
    assert "a.pdf" in msgs[0]["content"] and "hello" in msgs[0]["content"]


def test_build_messages_direct():
    assert build_messages({"question": "q"})[0]["content"] == "Answer concisely."
