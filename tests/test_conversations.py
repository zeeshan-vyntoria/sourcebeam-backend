import json

from httpx import AsyncClient

from app.services.rag import RetrievalResult


async def test_conversation_history_and_stream(
    authenticated_client: AsyncClient, monkeypatch
):
    client = authenticated_client
    created = await client.post("/api/conversations", json={})
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    async def fake_ai(history):
        assert history[-1] == {"role": "user", "content": "Explain async Python"}
        for chunk in ("Async Python lets ", "other work run while awaiting I/O."):
            yield chunk, "test-model"

    monkeypatch.setattr(
        "app.api.routes.conversations.stream_chat_response", fake_ai
    )
    streamed = await client.post(
        f"/api/conversations/{conversation_id}/messages/stream",
        json={"content": "Explain async Python"},
    )
    assert streamed.status_code == 200
    events = [json.loads(line) for line in streamed.text.splitlines()]
    assert [event["type"] for event in events] == [
        "start",
        "meta",
        "delta",
        "delta",
        "done",
    ]
    assert "awaiting I/O" in "".join(
        event.get("text", "") for event in events if event["type"] == "delta"
    )
    assert events[-1]["type"] == "done"

    history = await client.get(f"/api/conversations/{conversation_id}")
    assert history.status_code == 200
    assert [message["role"] for message in history.json()["messages"]] == [
        "user",
        "assistant",
    ]
    assert history.json()["title"] == "Explain async Python"


async def test_conversations_are_private(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={
            "email": "first@example.com",
            "display_name": "First",
            "password": "first-secure-password",
        },
    )
    created = await client.post("/api/conversations", json={})
    conversation_id = created.json()["id"]
    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/register",
        json={
            "email": "second@example.com",
            "display_name": "Second",
            "password": "second-secure-password",
        },
    )
    assert (await client.get(f"/api/conversations/{conversation_id}")).status_code == 404
    assert (await client.delete(f"/api/conversations/{conversation_id}")).status_code == 404


async def test_rag_stream_returns_and_persists_sources(
    authenticated_client: AsyncClient, monkeypatch
):
    client = authenticated_client
    created = await client.post("/api/conversations", json={})
    conversation_id = created.json()["id"]
    citation = {
        "document_id": "doc-1",
        "document_name": "manual.pdf",
        "page_number": 7,
        "chunk_id": "chunk-1",
        "excerpt": "FastAPI supports dependency injection.",
        "score": 0.91,
    }

    async def fake_retrieval(db, requested_conversation_id, user_id, query):
        assert requested_conversation_id == conversation_id
        assert query == "What does the manual say?"
        return RetrievalResult(
            has_documents=True,
            context="[Source 1: manual.pdf, page 7]\nFastAPI supports dependency injection.",
            citations=[citation],
        )

    async def fake_ai(history, system_instruction=None):
        assert "untrusted reference data" in system_instruction
        yield "It supports dependency injection [1].", "test-model"

    monkeypatch.setattr(
        "app.api.routes.conversations.retrieve_context", fake_retrieval
    )
    monkeypatch.setattr(
        "app.api.routes.conversations.stream_chat_response", fake_ai
    )
    response = await client.post(
        f"/api/conversations/{conversation_id}/messages/stream",
        json={"content": "What does the manual say?"},
    )
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["type"] for event in events] == [
        "start",
        "sources",
        "meta",
        "delta",
        "done",
    ]
    assert events[1]["sources"] == [citation]

    history = await client.get(f"/api/conversations/{conversation_id}")
    assistant = history.json()["messages"][-1]
    assert assistant["citations"] == [citation]
    assert assistant["content"].endswith("[1].")
