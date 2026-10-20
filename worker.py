"""Run the durable Sourcebeam document-ingestion worker."""

import asyncio
import selectors
import sys

from app.services.ingestion import run_worker


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.run(run_worker(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
    else:
        asyncio.run(run_worker())
