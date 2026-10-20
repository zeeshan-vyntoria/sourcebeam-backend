from httpx import AsyncClient


async def test_pdf_upload_attaches_to_conversation_and_can_be_deleted(
    authenticated_client: AsyncClient, monkeypatch
):
    client = authenticated_client
    conversation = await client.post("/api/conversations", json={})
    conversation_id = conversation.json()["id"]

    async def fake_ingest(db, document, data):
        assert data.startswith(b"%PDF-")
        document.status = "ready"
        document.page_count = 2
        document.chunk_count = 4
        await db.commit()

    monkeypatch.setattr("app.api.routes.documents.ingest_document", fake_ingest)
    uploaded = await client.post(
        "/api/documents",
        data={"conversation_id": conversation_id},
        files={"file": ("guide.pdf", b"%PDF-1.7\ntest", "application/pdf")},
    )
    assert uploaded.status_code == 201
    document = uploaded.json()
    assert document["status"] == "ready"
    assert document["filename"] == "guide.pdf"

    attached = await client.get(f"/api/conversations/{conversation_id}/documents")
    assert attached.status_code == 200
    assert [item["id"] for item in attached.json()] == [document["id"]]

    original = await client.get(f"/api/documents/{document['id']}/content")
    assert original.status_code == 200
    assert original.headers["content-type"] == "application/pdf"
    assert original.content.startswith(b"%PDF-")

    removed = await client.delete(f"/api/documents/{document['id']}")
    assert removed.status_code == 204
    assert (await client.get("/api/documents")).json() == []


async def test_pdf_upload_rejects_non_pdf(authenticated_client: AsyncClient):
    response = await authenticated_client.post(
        "/api/documents",
        files={"file": ("notes.txt", b"not a pdf", "text/plain")},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Only PDF files are supported"


async def test_other_user_cannot_attach_document(client: AsyncClient, monkeypatch):
    await client.post(
        "/api/auth/register",
        json={
            "email": "document-owner@example.com",
            "display_name": "Owner",
            "password": "owner-secure-password",
        },
    )

    async def fake_ingest(db, document, data):
        document.status = "ready"
        document.page_count = 1
        document.chunk_count = 1
        await db.commit()

    monkeypatch.setattr("app.api.routes.documents.ingest_document", fake_ingest)
    uploaded = await client.post(
        "/api/documents",
        files={"file": ("private.pdf", b"%PDF-1.7\ntest", "application/pdf")},
    )
    document_id = uploaded.json()["id"]
    await client.post("/api/auth/logout")

    await client.post(
        "/api/auth/register",
        json={
            "email": "other-reader@example.com",
            "display_name": "Reader",
            "password": "reader-secure-password",
        },
    )
    conversation = await client.post("/api/conversations", json={})
    response = await client.put(
        f"/api/conversations/{conversation.json()['id']}/documents/{document_id}"
    )
    assert response.status_code == 404
