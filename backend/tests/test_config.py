from app.core.config import DEFAULT_DATABASE_URL, is_local_database_url, is_same_database_url, load_database_url, load_external_database_url


def test_database_url_uses_env_var_first(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("LOCAL_DATABASE_URL=postgresql://from-file/db\n")

    assert load_database_url({"DATABASE_URL": "postgresql://from-env/db"}, (env_file,)) == (
        "postgresql+psycopg://from-file/db"
    )


def test_database_url_reads_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# local settings\nLOCAL_DATABASE_URL='postgres://from-file/db'\n")

    assert load_database_url({}, (env_file,)) == "postgresql+psycopg://from-file/db"


def test_process_database_url_is_used_for_runtime_injection(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://direct/db\n"
        "DATABASE_POOLER_URL=postgresql://pooler/db\n"
    )

    assert load_database_url({"DATABASE_POOLER_URL": "postgresql://runtime-pooler/db"}, (env_file,)) == "postgresql+psycopg://runtime-pooler/db"


def test_database_url_falls_back_to_local():
    assert load_database_url({}, ()) == DEFAULT_DATABASE_URL


def test_external_database_url_reads_env_var_first(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("EXTERNAL_DATABASE_URL=postgresql://from-file/db\n")

    assert load_external_database_url({"SYNC_DATABASE_URL": "postgres://from-env/db"}, (env_file,)) == (
        "postgresql+psycopg://from-env/db"
    )


def test_external_database_url_reads_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SYNC_DATABASE_URL=postgresql://from-file/db\n")

    assert load_external_database_url({}, (env_file,)) == "postgresql+psycopg://from-file/db"


def test_external_database_url_reads_existing_database_env_file_keys(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://direct/db\n"
        "DATABASE_POOLER_URL=postgresql://pooler/db\n"
    )

    assert load_database_url({}, (env_file,)) == DEFAULT_DATABASE_URL
    assert load_external_database_url({}, (env_file,)) == "postgresql+psycopg://pooler/db"


def test_external_database_url_supports_database_typo_key(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DATABSE_URL=postgresql://typo/db\n")

    assert load_external_database_url({}, (env_file,)) == "postgresql+psycopg://typo/db"


def test_local_database_url_detection():
    assert is_local_database_url("sqlite:///local.db")
    assert is_local_database_url(DEFAULT_DATABASE_URL)
    assert is_local_database_url("postgresql+psycopg://postgres:postgres@db:5432/master_terminal")
    assert not is_local_database_url("postgresql+psycopg://postgres:postgres@example.com:5432/master_terminal")


def test_same_database_url_ignores_driver_and_default_port():
    assert is_same_database_url(
        "postgresql+psycopg://postgres:postgres@db:5432/master_terminal",
        "postgresql://other:secret@db/master_terminal",
    )
    assert not is_same_database_url(
        "postgresql+psycopg://postgres:postgres@db:5432/master_terminal",
        "postgresql://postgres:postgres@example.com:5432/master_terminal",
    )
