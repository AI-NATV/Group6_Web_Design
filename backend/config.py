"""Small, environment-based configuration surface for the API."""

from __future__ import annotations

import os


def _origins_from_environment() -> list[str]:
    """Return explicitly configured development/browser origins.

    The `null` entry supports opening the prototype HTML directly from disk in
    development. Deployments should set ALLOWED_ORIGINS to their real HTTPS
    frontend origin(s), and should normally serve the included frontend at
    `/app/` instead.
    """

    default = (
        "http://127.0.0.1:8000,http://localhost:8000,"
        "http://127.0.0.1:5500,http://localhost:5500,null"
    )
    raw_origins = os.getenv("ALLOWED_ORIGINS", default)
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_BYTES", str(10 * 1024 * 1024)))
ALLOWED_ORIGINS = _origins_from_environment()
