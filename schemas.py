from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    completed: bool = False


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    completed: bool | None = None


class TaskResponse(TaskCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class TodoCreate(BaseModel):
    todoTitle: str = Field(min_length=1, max_length=255)
    description: str = ""
    isDone: bool = False


class TodoResponse(TodoCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class AIChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)


class AIChatResponse(BaseModel):
    response: str
    model: str
