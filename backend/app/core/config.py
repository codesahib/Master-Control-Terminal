import os
from collections.abc import Iterable, Mapping
from pathlib import Path

from pydantic import BaseModel

DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/master_terminal"


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
    database_url = (
        environ.get("DATABASE_POOLER_URL")
        or environ.get("DATABASE_URL")
        or _database_url_from_env_file(env_paths or _candidate_env_paths(), "DATABASE_POOLER_URL")
        or _database_url_from_env_file(env_paths or _candidate_env_paths(), "DATABASE_URL")
    )
    return _normalize_database_url(database_url or DEFAULT_DATABASE_URL)


class Settings(BaseModel):
    app_name: str = "Master Terminal API"
    database_url: str = load_database_url()


settings = Settings()
