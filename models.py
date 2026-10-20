from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    completed: Mapped[bool] = mapped_column(Boolean, default=False)


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(primary_key=True)
    todoTitle: Mapped[str] = mapped_column("todo_title", String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    isDone: Mapped[bool] = mapped_column("is_done", Boolean, default=False)
