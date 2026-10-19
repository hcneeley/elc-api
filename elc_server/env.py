"""Load secrets from a local .env file without printing values."""

from __future__ import annotations

import os
from pathlib import Path

# Project root
_ROOT = Path(__file__).resolve().parent.parent
# Prefer .env; also accept key.env if that's what was created locally
_ENV_CANDIDATES = (_ROOT / ".env", _ROOT / "key.env")
# Render Secret Files mount here: /etc/secrets/<filename-from-dashboard>
_SECRETS_DIR = Path("/etc/secrets")
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
        _apply_secret_text(env_file.read_text(encoding="utf-8"), into_environ=True)
        break  # first existing file wins


def _parse_token_from_text(text: str) -> str | None:
    """Extract a Mindat token from KEY=value lines or a bare token file."""
    lines = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not lines:
        return None

    bare: str | None = None
    for line in lines:
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export ") :].strip()
            value = value.strip().strip("'").strip('"')
            if key in _KEY_ENV_NAMES and value:
                return value
        else:
            token = line.strip("'").strip('"')
            if token and bare is None:
                bare = token
    return bare


def _apply_secret_text(text: str, *, into_environ: bool) -> str | None:
    """Optionally load KEY=VALUE into environ; always return a token if found."""
    token = _parse_token_from_text(text)
    if into_environ:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export ") :].strip()
            value = value.strip().strip("'").strip('"')
            if key and value and key not in os.environ:
                os.environ[key] = value
        if token and "MINDAT_API_KEY" not in os.environ:
            # Bare-token file → expose as the canonical env name
            if _parse_token_from_text(text) == token and "=" not in text.splitlines()[0]:
                os.environ["MINDAT_API_KEY"] = token
    return token


def _secret_file_paths() -> list[Path]:
    """Candidate secret-file paths (Render mount + optional override)."""
    paths: list[Path] = []
    override = (os.environ.get("MINDAT_SECRET_FILE") or "").strip()
    if override:
        paths.append(Path(override))
    # Preferred filenames
    for name in (
        "MINDAT_API_KEY",
        "mindat_api_key",
        "key.env",
        ".env",
        "mindat.env",
        "mindat",
    ):
        paths.append(_SECRETS_DIR / name)
    # Any other files Render mounted under /etc/secrets
    try:
        if _SECRETS_DIR.is_dir():
            for p in sorted(_SECRETS_DIR.iterdir()):
                if p.is_file() and p not in paths:
                    paths.append(p)
    except OSError:
        pass
    return paths


def list_secret_filenames() -> list[str]:
    """Filenames visible under /etc/secrets (for diagnostics; no contents)."""
    try:
        if not _SECRETS_DIR.is_dir():
            return []
        return sorted(p.name for p in _SECRETS_DIR.iterdir() if p.is_file())
    except OSError:
        return []


def _read_secret_files() -> str | None:
    """Read Mindat token from Render secret-file mounts if present."""
    for path in _secret_file_paths():
        try:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            token = _parse_token_from_text(text)
            if token:
                return token
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


def mindat_key_status() -> dict[str, object]:
    """Safe diagnostics (never includes the secret itself)."""
    key = mindat_api_key()
    return {
        "mindat_key_present": key is not None,
        "mindat_key_length": len(key) if key else 0,
        "mindat_secret_files": list_secret_filenames(),
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
