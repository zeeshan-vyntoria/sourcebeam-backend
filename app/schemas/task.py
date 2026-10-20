from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    completed: bool = False


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    completed: bool | None = None

    @model_validator(mode="after")
    def require_a_change(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class TaskResponse(TaskCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
