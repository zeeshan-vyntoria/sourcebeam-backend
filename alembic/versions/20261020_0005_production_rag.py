"""Add durable ingestion, object storage metadata, and hybrid search.

Revision ID: 20261020_0005
Revises: 20261020_0004
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261020_0005"
down_revision: str | None = "20261020_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("storage_key", sa.String(500), nullable=True))
    op.add_column("documents", sa.Column("original_size", sa.Integer(), server_default="0", nullable=False))
    op.add_column("documents", sa.Column("progress", sa.Integer(), server_default="0", nullable=False))
    op.add_column("image_attachments", sa.Column("storage_key", sa.String(500), nullable=True))
    op.alter_column("image_attachments", "data", nullable=True)
    op.create_table(
        "document_ingestion_jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id"),
    )
    op.create_index("ix_document_ingestion_jobs_document_id", "document_ingestion_jobs", ["document_id"])
    op.create_index("ix_document_ingestion_jobs_status", "document_ingestion_jobs", ["status"])
    op.execute(
        "CREATE INDEX ix_document_chunks_content_fts ON document_chunks "
        "USING gin (to_tsvector('simple', content))"
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_content_fts", table_name="document_chunks")
    op.drop_index("ix_document_ingestion_jobs_status", table_name="document_ingestion_jobs")
    op.drop_index("ix_document_ingestion_jobs_document_id", table_name="document_ingestion_jobs")
    op.drop_table("document_ingestion_jobs")
    op.alter_column("image_attachments", "data", nullable=False)
    op.drop_column("image_attachments", "storage_key")
    op.drop_column("documents", "progress")
    op.drop_column("documents", "original_size")
    op.drop_column("documents", "storage_key")
