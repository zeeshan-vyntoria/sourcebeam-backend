import logging
import sys


def configure_logging(environment: str) -> None:
    logging.basicConfig(
        level=logging.DEBUG if environment == "development" else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
