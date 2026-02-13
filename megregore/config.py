"""
Megregore Configuration — loads settings from environment variables.

Uses python-dotenv to load .env files. All settings have sensible defaults
for local development. Override via environment variables for production.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root if it exists
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


# Server
HOST: str = os.getenv("MEGREGORE_HOST", "127.0.0.1")
PORT: int = int(os.getenv("MEGREGORE_PORT", "3000"))

# Security
SECRET: str | None = os.getenv("MEGREGORE_SECRET")  # None = auto-generate
CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv("MEGREGORE_CORS_ORIGINS", f"http://localhost:{PORT}").split(",")
    if o.strip()
]
TOKEN_EXPIRY_HOURS: int = int(os.getenv("MEGREGORE_TOKEN_EXPIRY_HOURS", "24"))
RATE_LIMIT: int = int(os.getenv("MEGREGORE_RATE_LIMIT", "200"))

# Proxy / Production
TRUSTED_PROXY: bool = os.getenv("MEGREGORE_TRUSTED_PROXY", "false").lower() in ("true", "1", "yes")
SECURE: bool = os.getenv("MEGREGORE_SECURE", "false").lower() in ("true", "1", "yes")

# Admin
ADMIN_USERNAME: str = os.getenv("MEGREGORE_ADMIN_USERNAME", "admin")

# Paths
DATA_DIR: Path = _PROJECT_ROOT / "data"
SECRET_FILE: Path = DATA_DIR / ".secret"
AUTH_FILE: Path = DATA_DIR / "auth.json"
SECURITY_LOG: Path = DATA_DIR / "security.log"
