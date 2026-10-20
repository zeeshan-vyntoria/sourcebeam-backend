import asyncio
from collections.abc import AsyncIterator
import logging

import truststore

# Preserve TLS verification while allowing certificates trusted by Windows.
truststore.inject_into_ssl()

from google import genai
from google.genai import errors, types

from app.core.config import settings


logger = logging.getLogger(__name__)
_generation_slots = asyncio.Semaphore(settings.ai_max_concurrency)


class AIConfigurationError(Exception):
    pass


class AIServiceError(Exception):
    pass


class AITemporaryUnavailableError(AIServiceError):
    pass


async def stream_chat_response(
    history: list[dict],
    system_instruction: str | None = None,
) -> AsyncIterator[tuple[str, str]]:
    if not settings.gemini_api_key or settings.gemini_api_key == "your_gemini_api_key":
        raise AIConfigurationError("GEMINI_API_KEY is not configured")

    models = list(dict.fromkeys([settings.gemini_model, *settings.fallback_models]))
    contents = []
    for item in history:
        parts = [types.Part(text=item["content"])]
        for image in item.get("images", []):
            parts.append(
                types.Part.from_bytes(
                    data=image["data"],
                    mime_type=image["mime_type"],
                )
            )
        contents.append(
            {
                "role": "model" if item["role"] == "assistant" else "user",
                "parts": parts,
            }
        )
    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=settings.ai_request_timeout_seconds * 1000),
    )
    last_error: Exception | None = None

    try:
        try:
            await asyncio.wait_for(_generation_slots.acquire(), timeout=1)
        except TimeoutError as exc:
            raise AITemporaryUnavailableError("AI capacity is busy. Please try again shortly.") from exc
        try:
            async with asyncio.timeout(settings.ai_request_timeout_seconds):
                for model in models:
                    model_started = False
                    try:
                        stream = await client.aio.models.generate_content_stream(
                            model=model,
                            contents=contents,
                            config=(
                                types.GenerateContentConfig(
                                    system_instruction=system_instruction
                                )
                                if system_instruction
                                else None
                            ),
                        )
                        async for result in stream:
                            response_text = result.text or ""
                            if response_text:
                                model_started = True
                                yield response_text, model
                    except errors.APIError as exc:
                        last_error = exc
                        # A retired or account-ineligible model returns 404.
                        # Continue through the configured fallback chain just as
                        # we do for temporary provider capacity failures.
                        if not model_started and exc.code in {404, 429, 500, 502, 503, 504}:
                            logger.warning(
                                "Gemini model temporarily unavailable model=%s status=%s",
                                model,
                                exc.code,
                            )
                            continue
                        logger.exception("Gemini rejected request status=%s", exc.code)
                        raise AIServiceError(f"Gemini API error (HTTP {exc.code})") from exc

                    if model_started:
                        return
                    last_error = AIServiceError(f"Gemini model {model} returned an empty response")
        except TimeoutError as exc:
            raise AITemporaryUnavailableError("Gemini request timed out. Please try again.") from exc
        finally:
            _generation_slots.release()
    except asyncio.CancelledError:
        raise
    except (AIServiceError, AIConfigurationError):
        raise
    except Exception as exc:
        logger.exception("Gemini request failed")
        raise AIServiceError("Gemini could not generate a response") from exc
    finally:
        await client.aio.aclose()

    raise AITemporaryUnavailableError(
        "All configured Gemini models are temporarily unavailable. Please try again later."
    ) from last_error


async def generate_chat_response(
    history: list[dict], system_instruction: str | None = None
) -> tuple[str, str]:
    """Collect a streamed response for non-streaming compatibility callers."""
    parts: list[str] = []
    selected_model = ""
    async for text, model in stream_chat_response(history, system_instruction):
        parts.append(text)
        selected_model = model
    return "".join(parts), selected_model
