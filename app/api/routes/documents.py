import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.rate_limit import check_ai_limit
from app.models import Conversation, ConversationDocument, Document, ImageAttachment
from app.schemas.document import DocumentResponse
from app.services.rag import (
    DocumentProcessingError,
    document_digest,
    ingest_document,
    safe_pdf_filename,
    validate_pdf_upload,
)
from app.services.ingestion import enqueue_ingestion
from app.services.storage import StorageError, object_key, storage


logger = logging.getLogger(__name__)
router = APIRouter(tags=["documents"])


async def get_owned_document(document_id: str, user_id: int, db: DbSession) -> Document:
    document = await db.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == user_id)
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


async def get_owned_conversation(
    conversation_id: str, user_id: int, db: DbSession
) -> Conversation:
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


async def attach_document(
    conversation_id: str, document_id: str, user_id: int, db: DbSession
) -> None:
    await get_owned_conversation(conversation_id, user_id, db)
    document = await get_owned_document(document_id, user_id, db)
    if document.status != "ready":
        raise HTTPException(status_code=409, detail="Document is not ready")
    link = await db.get(
        ConversationDocument,
        {"conversation_id": conversation_id, "document_id": document_id},
    )
    if link is None:
        db.add(
            ConversationDocument(
                conversation_id=conversation_id,
                document_id=document_id,
            )
        )
        await db.commit()


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(user: CurrentUser, db: DbSession):
    result = await db.scalars(
        select(Document)
        .where(Document.user_id == user.id)
        .order_by(Document.created_at.desc())
    )
    return list(result)


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    request: Request,
    response: Response,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
):
    await check_ai_limit(request, user.id)
    data = await file.read(settings.rag_max_pdf_bytes + 1)
    await file.close()
    try:
        validate_pdf_upload(data, file.content_type)
    except DocumentProcessingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    uploads_today = await db.scalar(
        select(func.count(Document.id)).where(
            Document.user_id == user.id, Document.created_at >= day_ago
        )
    )
    if (uploads_today or 0) >= settings.public_daily_uploads:
        raise HTTPException(status_code=429, detail="Daily document upload quota reached")
    document_bytes = await db.scalar(
        select(func.coalesce(func.sum(Document.original_size), 0)).where(Document.user_id == user.id)
    )
    image_bytes = await db.scalar(
        select(func.coalesce(func.sum(ImageAttachment.byte_size), 0)).where(
            ImageAttachment.user_id == user.id
        )
    )
    if int(document_bytes or 0) + int(image_bytes or 0) + len(data) > settings.public_user_storage_bytes:
        raise HTTPException(status_code=413, detail="Account storage quota exceeded")

    digest = document_digest(data)
    existing = await db.scalar(
        select(Document).where(Document.user_id == user.id, Document.sha256 == digest)
    )
    if existing is not None:
        if existing.status == "failed":
            await db.delete(existing)
            await db.commit()
            existing = None
        elif existing.status == "processing":
            raise HTTPException(status_code=409, detail="This PDF is already being processed")
    if existing is not None:
        if conversation_id:
            await attach_document(conversation_id, existing.id, user.id, db)
        response.status_code = status.HTTP_200_OK
        return existing

    if conversation_id:
        await get_owned_conversation(conversation_id, user.id, db)
    document = Document(
        user_id=user.id,
        filename=safe_pdf_filename(file.filename),
        sha256=digest,
        original_size=len(data),
        status="processing",
    )
    storage_key = object_key(user.id, "documents", "pdf")
    try:
        await storage.put(storage_key, data, "application/pdf")
    except StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    document.storage_key = storage_key
    db.add(document)
    await db.commit()
    await db.refresh(document)

    try:
        if settings.environment == "test":
            await ingest_document(db, document, data)
            if conversation_id:
                await attach_document(conversation_id, document.id, user.id, db)
        else:
            await enqueue_ingestion(db, document, conversation_id)
        await db.refresh(document)
        return document
    except DocumentProcessingError as exc:
        await db.rollback()
        failed = await db.get(Document, document.id)
        if failed is not None:
            failed.status = "failed"
            failed.error = str(exc)[:500]
            await db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        failed = await db.get(Document, document.id)
        if failed is not None:
            failed.status = "failed"
            failed.error = "Document processing failed"
            await db.commit()
        logger.exception("Unexpected document processing failure document_id=%s", document.id)
        raise HTTPException(status_code=502, detail="Document processing failed") from exc


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str, user: CurrentUser, db: DbSession):
    document = await get_owned_document(document_id, user.id, db)
    try:
        await storage.delete(document.storage_key)
    except StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await db.delete(document)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/documents/{document_id}/content")
async def document_content(document_id: str, user: CurrentUser, db: DbSession):
    document = await get_owned_document(document_id, user.id, db)
    if not document.storage_key:
        raise HTTPException(status_code=404, detail="Original document is unavailable")
    try:
        content = await storage.get(document.storage_key)
    except StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": f'inline; filename="{document.filename}"',
        },
    )


@router.get(
    "/conversations/{conversation_id}/documents",
    response_model=list[DocumentResponse],
)
async def list_conversation_documents(
    conversation_id: str, user: CurrentUser, db: DbSession
):
    await get_owned_conversation(conversation_id, user.id, db)
    result = await db.scalars(
        select(Document)
        .join(ConversationDocument, ConversationDocument.document_id == Document.id)
        .where(
            ConversationDocument.conversation_id == conversation_id,
            Document.user_id == user.id,
        )
        .order_by(Document.created_at.desc())
    )
    return list(result)


@router.put(
    "/conversations/{conversation_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def add_conversation_document(
    conversation_id: str, document_id: str, user: CurrentUser, db: DbSession
):
    await attach_document(conversation_id, document_id, user.id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/conversations/{conversation_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_conversation_document(
    conversation_id: str, document_id: str, user: CurrentUser, db: DbSession
):
    await get_owned_conversation(conversation_id, user.id, db)
    await get_owned_document(document_id, user.id, db)
    link = await db.get(
        ConversationDocument,
        {"conversation_id": conversation_id, "document_id": document_id},
    )
    if link is not None:
        await db.delete(link)
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
