"""Production-friendly server launcher, including Windows async PostgreSQL support."""

import asyncio
import selectors
import sys

import uvicorn

from app.core.config import settings


async def serve() -> None:
    config = uvicorn.Config("main:app", host=settings.app_host, port=settings.app_port)
    await uvicorn.Server(config).serve()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.run(
            serve(),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(serve())
