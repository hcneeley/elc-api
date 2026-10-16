"""Load secrets from a local .env file without printing values."""

from __future__ import annotations

import os
from pathlib import Path

# Project root: .../APIs/
_ROOT = Path(__file__).resolve().parent.parent
# Prefer .env; also accept key.env if that's what was created locally
_ENV_CANDIDATES = (_ROOT / ".env", _ROOT / "key.env")


def load_dotenv(path: Path | None = None) -> None:
    """
    Read KEY=VALUE lines into os.environ if the key is not already set.
    Also accepts a bare token (single line, no '=') as MINDAT_API_KEY.
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
                if key and key not in os.environ:
                    os.environ[key] = value
            else:
                # Bare token file (e.g. key.env containing only the secret)
                if "MINDAT_API_KEY" not in os.environ:
                    os.environ["MINDAT_API_KEY"] = line.strip("'").strip('"')
        break  # first existing file wins


def mindat_api_key() -> str | None:
    """Return Mindat token from env, or None if missing."""
    load_dotenv()
    key = os.environ.get("MINDAT_API_KEY", "").strip()
    return key or None


def mindat_enabled() -> bool:
    """
    Mindat is opt-in. Default OFF until the Mindat account/API access works.
    Enable later with MINDAT_ENABLED=true in key.env / environment.
    """
    load_dotenv()
    flag = os.environ.get("MINDAT_ENABLED", "false").strip().lower()
    return flag in {"1", "true", "t", "yes", "y", "on"}


def mindat_configured() -> bool:
    """True only when Mindat is enabled AND a key is present."""
    return mindat_enabled() and mindat_api_key() is not None
