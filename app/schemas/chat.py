from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=120)


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    image_ids: list[str] = Field(default_factory=list, max_length=3)


class ImageAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    mime_type: str
    byte_size: int
    width: int
    height: int
    created_at: datetime


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    model: str | None
    citations: list[dict] = Field(default_factory=list)
    image_attachments: list[ImageAttachmentResponse] = Field(default_factory=list)
    created_at: datetime


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[MessageResponse]
