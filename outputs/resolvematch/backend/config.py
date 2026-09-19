"""Local secrets never leave the backend; model credentials stay in TrueForge."""

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
LOCAL = ROOT / ".local"
LOCAL.mkdir(mode=0o700, exist_ok=True)


def local_secret(name: str) -> str:
    path = LOCAL / name
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text().strip()
    value = secrets.token_urlsafe(48)
    with os.fdopen(fd, "w") as handle:
        handle.write(value)
    return value


DB_PATH = Path(os.getenv("RESOLVEMATCH_DB", str(LOCAL / "resolvematch.sqlite3")))
MCP_TOKEN = os.getenv("RESOLVEMATCH_MCP_TOKEN") or local_secret("mcp-token")
SESSION_KEY = local_secret("session-key")
PASSWORD = os.getenv("RESOLVEMATCH_ADMIN_PASSWORD", "")
TRUEFORGE_URL = os.getenv("TRUEFORGE_URL", "http://localhost:8790").rstrip("/")
TRUEFORGE_TOKEN = os.getenv("TRUEFORGE_TOKEN", "")
AGENT_NAME = os.getenv("TRUEFORGE_AGENT_NAME", "resolve-match")
PUBLIC_ORIGIN = os.getenv("RESOLVEMATCH_ORIGIN", "http://localhost:8000")
MCP_URL = os.getenv("RESOLVEMATCH_MCP_URL", "http://127.0.0.1:8000/mcp")
