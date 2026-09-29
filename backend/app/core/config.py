import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel

DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/master_terminal"
LOCAL_DATABASE_URL_KEYS = ("LOCAL_DATABASE_URL", "APP_DATABASE_URL")
DATABASE_URL_KEYS = ("DATABASE_POOLER_URL", "DATABASE_URL")
EXTERNAL_DATABASE_URL_KEYS = ("EXTERNAL_DATABASE_URL", "SYNC_DATABASE_URL", "DATABASE_POOLER_URL", "DATABASE_URL", "DATABSE_URL")


def _candidate_env_paths() -> tuple[Path, ...]:
    backend_dir = Path(__file__).resolve().parents[2]
    repo_dir = backend_dir.parent
    return (
        Path.cwd() / ".env",
        Path.cwd().parent / ".env",
        backend_dir / ".env",
        repo_dir / ".env",
    )


def _database_url_from_env_file(env_paths: Iterable[Path], key_name: str) -> str | None:
    for env_path in dict.fromkeys(env_paths):
        if not env_path.exists():
            continue

        for raw_line in env_path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            key, separator, value = line.partition("=")
            if separator and key.strip() == key_name:
                return value.strip().strip("\"'") or None

    return None


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    return database_url


def load_database_url(
    environ: Mapping[str, str] = os.environ,
    env_paths: Iterable[Path] | None = None,
) -> str:
    paths = env_paths if env_paths is not None else _candidate_env_paths()
    database_url = (
        next((environ.get(key) for key in LOCAL_DATABASE_URL_KEYS if environ.get(key)), None)
        or next(
            (
                value
                for key in LOCAL_DATABASE_URL_KEYS
                for value in [_database_url_from_env_file(paths, key)]
                if value
            ),
            None,
        )
        or next((environ.get(key) for key in DATABASE_URL_KEYS if environ.get(key)), None)
    )
    return _normalize_database_url(database_url or DEFAULT_DATABASE_URL)


def load_external_database_url(
    environ: Mapping[str, str] = os.environ,
    env_paths: Iterable[Path] | None = None,
) -> str | None:
    paths = env_paths if env_paths is not None else _candidate_env_paths()
    database_url = next((environ.get(key) for key in EXTERNAL_DATABASE_URL_KEYS if environ.get(key)), None)
    if not database_url:
        database_url = next(
            (
                value
                for key in EXTERNAL_DATABASE_URL_KEYS
                for value in [_database_url_from_env_file(paths, key)]
                if value
            ),
            None,
        )
    return _normalize_database_url(database_url) if database_url else None


def is_local_database_url(database_url: str) -> bool:
    parsed = urlparse(database_url)
    if parsed.scheme.startswith("sqlite"):
        return True
    return (parsed.hostname or "").lower() in {"localhost", "127.0.0.1", "::1", "db"}


def is_same_database_url(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    left_parsed = urlparse(left)
    right_parsed = urlparse(right)
    return (
        left_parsed.scheme.split("+", 1)[0] == right_parsed.scheme.split("+", 1)[0]
        and (left_parsed.hostname or "").lower() == (right_parsed.hostname or "").lower()
        and (left_parsed.port or default_database_port(left_parsed.scheme)) == (right_parsed.port or default_database_port(right_parsed.scheme))
        and left_parsed.path == right_parsed.path
    )


def default_database_port(scheme: str) -> int | None:
    if scheme.startswith("postgres"):
        return 5432
    return None


class Settings(BaseModel):
    app_name: str = "Master Terminal API"
    database_url: str = load_database_url()
    external_database_url: str | None = load_external_database_url()


settings = Settings()
