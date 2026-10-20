from io import BytesIO
import json

from httpx import AsyncClient
from PIL import Image


def sample_png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (24, 16), color=(24, 140, 132)).save(output, format="PNG")
    return output.getvalue()


async def test_image_upload_content_and_multimodal_stream(
    authenticated_client: AsyncClient, monkeypatch
):
    client = authenticated_client
    conversation = await client.post("/api/conversations", json={})
    conversation_id = conversation.json()["id"]

    uploaded = await client.post(
        f"/api/conversations/{conversation_id}/images",
        files={"file": ("diagram.png", sample_png(), "image/png")},
    )
    assert uploaded.status_code == 201
    image = uploaded.json()
    assert image["filename"] == "diagram.png"
    assert image["mime_type"] == "image/png"
    assert (image["width"], image["height"]) == (24, 16)

    content = await client.get(f"/api/images/{image['id']}/content")
    assert content.status_code == 200
    assert content.headers["content-type"] == "image/png"
    assert content.content.startswith(b"\x89PNG")

    async def fake_ai(history, system_instruction=None):
        assert history[-1]["content"] == "What is in this image?"
        assert history[-1]["images"][0]["mime_type"] == "image/png"
        assert history[-1]["images"][0]["data"].startswith(b"\x89PNG")
        assert "untrusted data" in system_instruction
        yield "The image is a teal rectangle.", "vision-test-model"

    monkeypatch.setattr("app.api.routes.conversations.stream_chat_response", fake_ai)
    response = await client.post(
        f"/api/conversations/{conversation_id}/messages/stream",
        json={"content": "What is in this image?", "image_ids": [image["id"]]},
    )
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert any(event.get("model") == "vision-test-model" for event in events)

    history = await client.get(f"/api/conversations/{conversation_id}")
    user_message = history.json()["messages"][0]
    assert user_message["image_attachments"][0]["id"] == image["id"]
    assert "data" not in user_message["image_attachments"][0]


async def test_invalid_image_is_rejected(authenticated_client: AsyncClient):
    conversation = await authenticated_client.post("/api/conversations", json={})
    response = await authenticated_client.post(
        f"/api/conversations/{conversation.json()['id']}/images",
        files={"file": ("fake.png", b"not-an-image", "image/png")},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "The uploaded file is not a valid image"


async def test_other_user_cannot_read_private_image(client: AsyncClient):
    await client.post(
        "/api/auth/register",
        json={
            "email": "image-owner@example.com",
            "display_name": "Owner",
            "password": "owner-secure-password",
        },
    )
    conversation = await client.post("/api/conversations", json={})
    uploaded = await client.post(
        f"/api/conversations/{conversation.json()['id']}/images",
        files={"file": ("private.png", sample_png(), "image/png")},
    )
    image_id = uploaded.json()["id"]
    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/register",
        json={
            "email": "image-reader@example.com",
            "display_name": "Reader",
            "password": "reader-secure-password",
        },
    )

    assert (await client.get(f"/api/images/{image_id}/content")).status_code == 404
