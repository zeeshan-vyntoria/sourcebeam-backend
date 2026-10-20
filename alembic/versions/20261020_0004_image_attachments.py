"""Add private multimodal image attachments.

Revision ID: 20261020_0004
Revises: 20261019_0003
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261020_0004"
down_revision: str | None = "20261019_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=50), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_image_attachments_user_id", "image_attachments", ["user_id"])
    op.create_index(
        "ix_image_attachments_conversation_id", "image_attachments", ["conversation_id"]
    )
    op.create_index("ix_image_attachments_message_id", "image_attachments", ["message_id"])
    op.create_index(
        "ix_image_attachments_conversation_created",
        "image_attachments",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_image_attachments_conversation_created", table_name="image_attachments"
    )
    op.drop_index("ix_image_attachments_message_id", table_name="image_attachments")
    op.drop_index("ix_image_attachments_conversation_id", table_name="image_attachments")
    op.drop_index("ix_image_attachments_user_id", table_name="image_attachments")
    op.drop_table("image_attachments")
