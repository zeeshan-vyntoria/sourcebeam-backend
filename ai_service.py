"""Compatibility wrapper for the production AI service.

New code should import :mod:`app.services.ai` directly. Keeping this wrapper
prevents older tutorial imports from bypassing the shared timeout and capacity
controls.
"""

from app.services.ai import (
    AIConfigurationError,
    AIServiceError,
    AITemporaryUnavailableError,
    generate_chat_response as _generate_chat_response,
)


async def generate_chat_response(prompt: str) -> tuple[str, str]:
    return await _generate_chat_response([{"role": "user", "content": prompt}])


__all__ = [
    "AIConfigurationError",
    "AIServiceError",
    "AITemporaryUnavailableError",
    "generate_chat_response",
]
