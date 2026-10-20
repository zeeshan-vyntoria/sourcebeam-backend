from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import Task
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(payload: TaskCreate, user: CurrentUser, db: DbSession):
    task = Task(user_id=user.id, **payload.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.get("", response_model=list[TaskResponse])
async def list_tasks(user: CurrentUser, db: DbSession):
    result = await db.scalars(
        select(Task).where(Task.user_id == user.id).order_by(Task.id)
    )
    return list(result)


async def owned_task(task_id: int, user_id: int, db: DbSession) -> Task:
    task = await db.scalar(
        select(Task).where(Task.id == task_id, Task.user_id == user_id)
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, user: CurrentUser, db: DbSession):
    return await owned_task(task_id, user.id, db)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: int, payload: TaskUpdate, user: CurrentUser, db: DbSession):
    task = await owned_task(task_id, user.id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, user: CurrentUser, db: DbSession):
    task = await owned_task(task_id, user.id, db)
    await db.delete(task)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
