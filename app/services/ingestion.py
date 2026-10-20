"""Durable database-backed document ingestion worker."""

import asyncio
from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import SessionFactory
from app.models import ConversationDocument, Document, DocumentIngestionJob
from app.services.rag import DocumentProcessingError, ingest_document
from app.services.storage import StorageError, storage


logger = logging.getLogger(__name__)


async def enqueue_ingestion(
    db: AsyncSession, document: Document, conversation_id: str | None = None
) -> DocumentIngestionJob:
    job = DocumentIngestionJob(document_id=document.id, conversation_id=conversation_id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def _claim_job(db: AsyncSession) -> DocumentIngestionJob | None:
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(minutes=10)
    query = (
        select(DocumentIngestionJob)
        .where(
            or_(
                and_(
                    DocumentIngestionJob.status.in_(["queued", "retry"]),
                    DocumentIngestionJob.available_at <= now,
                ),
                and_(
                    DocumentIngestionJob.status == "processing",
                    DocumentIngestionJob.started_at < stale_before,
                ),
            ),
        )
        .order_by(DocumentIngestionJob.created_at)
        .limit(1)
    )
    if db.get_bind().dialect.name != "sqlite":
        query = query.with_for_update(skip_locked=True)
    job = await db.scalar(query)
    if job is None:
        return None
    job.status = "processing"
    job.attempts += 1
    job.started_at = now
    await db.commit()
    return job


async def process_one_job() -> bool:
    async with SessionFactory() as db:
        job = await _claim_job(db)
        if job is None:
            return False
        document = await db.get(Document, job.document_id)
        if document is None or not document.storage_key:
            job.status = "failed"
            job.error = "Document object is unavailable"
            await db.commit()
            return True
        try:
            data = await storage.get(document.storage_key)
            await ingest_document(db, document, data)
            if job.conversation_id:
                existing = await db.get(
                    ConversationDocument,
                    {"conversation_id": job.conversation_id, "document_id": document.id},
                )
                if existing is None:
                    db.add(
                        ConversationDocument(
                            conversation_id=job.conversation_id,
                            document_id=document.id,
                        )
                    )
            job.status = "complete"
            job.error = None
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()
        except (DocumentProcessingError, StorageError) as exc:
            await db.rollback()
            job = await db.get(DocumentIngestionJob, job.id)
            document = await db.get(Document, job.document_id) if job else None
            if job is None:
                return True
            if job.attempts < settings.ingestion_max_attempts:
                job.status = "retry"
                job.available_at = datetime.now(timezone.utc) + timedelta(
                    seconds=2 ** job.attempts
                )
            else:
                job.status = "failed"
                job.finished_at = datetime.now(timezone.utc)
                if document is not None:
                    document.status = "failed"
                    document.error = str(exc)[:500]
            job.error = str(exc)[:500]
            await db.commit()
        except Exception:
            logger.exception("Unexpected ingestion failure job_id=%s", job.id)
            await db.rollback()
            job = await db.get(DocumentIngestionJob, job.id)
            document = await db.get(Document, job.document_id) if job else None
            if job is not None:
                job.status = "failed"
                job.error = "Unexpected ingestion failure"
                job.finished_at = datetime.now(timezone.utc)
            if document is not None:
                document.status = "failed"
                document.error = "Document processing failed"
            await db.commit()
        return True


async def run_worker() -> None:
    logger.info("Sourcebeam ingestion worker started")
    while True:
        processed = await process_one_job()
        if not processed:
            await asyncio.sleep(settings.ingestion_poll_seconds)
