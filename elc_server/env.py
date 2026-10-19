"""Load secrets from a local .env file without printing values."""

from __future__ import annotations

import os
from pathlib import Path

# Project root
_ROOT = Path(__file__).resolve().parent.parent
# Prefer .env; also accept key.env if that's what was created locally
_ENV_CANDIDATES = (_ROOT / ".env", _ROOT / "key.env")
# Render Secret Files are mounted here (not the same as Environment Variables)
_SECRET_FILE_CANDIDATES = (
    Path("/etc/secrets/MINDAT_API_KEY"),
    Path("/etc/secrets/mindat_api_key"),
    Path("/etc/secrets/key.env"),
)
_KEY_ENV_NAMES = (
    "MINDAT_API_KEY",
    "MINDAT_TOKEN",
    "MINDAT_KEY",
    "OPENMINDAT_API_KEY",
)


def load_dotenv(path: Path | None = None) -> None:
    """
    Read KEY=VALUE lines into os.environ if the key is not already set.
    Also accepts a bare token (single line, no '=') as MINDAT_API_KEY.
    Skips empty values so a blank file never clobbers a real secret.
    Does not log or return secret values.
    """
    paths = [path] if path is not None else list(_ENV_CANDIDATES)
    for env_file in paths:
        if env_file is None or not env_file.is_file():
            continue
        lines = [
            ln.strip()
            for ln in env_file.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        for line in lines:
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                if key.startswith("export "):
                    key = key[len("export ") :].strip()
                value = value.strip().strip("'").strip('"')
                if key and value and key not in os.environ:
                    os.environ[key] = value
            else:
                # Bare token file (e.g. key.env containing only the secret)
                token = line.strip("'").strip('"')
                if token and "MINDAT_API_KEY" not in os.environ:
                    os.environ["MINDAT_API_KEY"] = token
        break  # first existing file wins


def _read_secret_files() -> str | None:
    """Read Mindat token from Render secret-file mounts if present."""
    for path in _SECRET_FILE_CANDIDATES:
        try:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                continue
            # key.env-style: KEY=value or bare token
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    if k.strip() in _KEY_ENV_NAMES and v.strip():
                        return v.strip().strip("'").strip('"')
                else:
                    return line.strip("'").strip('"')
        except OSError:
            continue
    return None


def mindat_api_key() -> str | None:
    """Return Mindat token from env / secret file, or None if missing."""
    load_dotenv()
    for name in _KEY_ENV_NAMES:
        key = os.environ.get(name, "").strip()
        if key:
            return key
    return _read_secret_files()


def mindat_key_status() -> dict[str, bool | int]:
    """Safe diagnostics (never includes the secret itself)."""
    key = mindat_api_key()
    return {
        "mindat_key_present": key is not None,
        "mindat_key_length": len(key) if key else 0,
    }


def mindat_enabled() -> bool:
    """
    Mindat is on by default on this branch.
    Disable with MINDAT_ENABLED=false in key.env / environment.
    Still requires MINDAT_API_KEY for queries to succeed.
    """
    load_dotenv()
    flag = os.environ.get("MINDAT_ENABLED", "true").strip().lower()
    return flag in {"1", "true", "t", "yes", "y", "on"}


def mindat_configured() -> bool:
    """True only when Mindat is enabled AND a key is present."""
    return mindat_enabled() and mindat_api_key() is not None
