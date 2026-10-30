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

# SQLite (a file under the git-ignored data/ folder) for development; set a
# PostgreSQL URL such as postgresql+psycopg://user:password@localhost:5432/dbname
# in the environment for a shared or deployed database. Never commit credentials.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")

# Signs login tokens (JWT). Required, with no default: anyone who knows it can
# forge a token for any user. Generate one per environment with
#   python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = os.getenv("SECRET_KEY", "")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
