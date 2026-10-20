from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.rate_limit import check_ai_limit
from app.models import Conversation, Document, ImageAttachment
from app.schemas.chat import ImageAttachmentResponse
from app.services.images import (
    ImageProcessingError,
    safe_image_filename,
    sanitize_image,
)
from app.services.storage import StorageError, object_key, storage


router = APIRouter(tags=["images"])


async def get_owned_image(image_id: str, user_id: int, db: DbSession) -> ImageAttachment:
    image = await db.scalar(
        select(ImageAttachment).where(
            ImageAttachment.id == image_id,
            ImageAttachment.user_id == user_id,
        )
    )
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return image


@router.post(
    "/conversations/{conversation_id}/images",
    response_model=ImageAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_image(
    conversation_id: str,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
):
    await check_ai_limit(request, user.id)
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    data = await file.read(settings.image_max_bytes + 1)
    await file.close()
    try:
        sanitized = sanitize_image(data, file.content_type)
    except ImageProcessingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    uploads_today = await db.scalar(
        select(func.count(ImageAttachment.id)).where(
            ImageAttachment.user_id == user.id,
            ImageAttachment.created_at >= day_ago,
        )
    )
    if (uploads_today or 0) >= settings.public_daily_uploads:
        raise HTTPException(status_code=429, detail="Daily image upload quota reached")
    document_bytes = await db.scalar(
        select(func.coalesce(func.sum(Document.original_size), 0)).where(Document.user_id == user.id)
    )
    image_bytes = await db.scalar(
        select(func.coalesce(func.sum(ImageAttachment.byte_size), 0)).where(
            ImageAttachment.user_id == user.id
        )
    )
    if int(document_bytes or 0) + int(image_bytes or 0) + len(sanitized.data) > settings.public_user_storage_bytes:
        raise HTTPException(status_code=413, detail="Account storage quota exceeded")

    extension = sanitized.mime_type.split("/")[-1].replace("jpeg", "jpg")
    storage_key = object_key(user.id, "images", extension)
    try:
        await storage.put(storage_key, sanitized.data, sanitized.mime_type)
    except StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    image = ImageAttachment(
        user_id=user.id,
        conversation_id=conversation.id,
        filename=safe_image_filename(file.filename, sanitized.mime_type),
        mime_type=sanitized.mime_type,
        byte_size=len(sanitized.data),
        width=sanitized.width,
        height=sanitized.height,
        storage_key=storage_key,
        data=None,
    )
    db.add(image)
    await db.commit()
    await db.refresh(image)
    return image


@router.get("/images/{image_id}/content")
async def image_content(image_id: str, user: CurrentUser, db: DbSession):
    image = await get_owned_image(image_id, user.id, db)
    try:
        content = image.data if image.data is not None else await storage.get(image.storage_key or "")
    except StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type=image.mime_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="{image.filename}"',
        },
    )


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pending_image(image_id: str, user: CurrentUser, db: DbSession):
    image = await get_owned_image(image_id, user.id, db)
    if image.message_id is not None:
        raise HTTPException(status_code=409, detail="Images attached to messages cannot be removed")
    try:
        await storage.delete(image.storage_key)
    except StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await db.delete(image)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
