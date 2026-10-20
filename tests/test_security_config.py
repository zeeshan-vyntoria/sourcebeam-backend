import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize(
    "secret",
    [
        "",
        "too-short",
        "development-only-secret-change-before-production",
        "replace_with_at_least_32_random_characters",
        "development-only-secret-change-before-production-padding",
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "                                            ",
    ],
)
def test_runtime_rejects_unsafe_jwt_secrets(secret):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="development", jwt_secret_key=secret)


def test_runtime_accepts_explicit_strong_secret():
    settings = Settings(
        _env_file=None,
        environment="development",
        jwt_secret_key="7N3yqL9vB2mK8xR4pT6wC1zF5hJ0sD_aG-UeIoiQXcM",
    )
    assert len(settings.jwt_secret_key) >= 43


def test_cookie_cors_rejects_wildcard_origin():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="development",
            jwt_secret_key="7N3yqL9vB2mK8xR4pT6wC1zF5hJ0sD_aG-UeIoiQXcM",
            ALLOWED_ORIGINS="*",
        )
