from fastapi import APIRouter

from app.api.routes import auth, conversations, documents, images, tasks


api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(conversations.router)
api_router.include_router(documents.router)
api_router.include_router(images.router)
api_router.include_router(tasks.router)
