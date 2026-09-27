from app.core.config import DEFAULT_DATABASE_URL, load_database_url


def test_database_url_uses_env_var_first(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql://from-file/db\n")

    assert load_database_url({"DATABASE_URL": "postgresql://from-env/db"}, (env_file,)) == (
        "postgresql+psycopg://from-env/db"
    )


def test_database_url_reads_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# local settings\nDATABASE_URL='postgres://from-file/db'\n")

    assert load_database_url({}, (env_file,)) == "postgresql+psycopg://from-file/db"


def test_pooler_url_wins(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://direct/db\n"
        "DATABASE_POOLER_URL=postgresql://pooler/db\n"
    )

    assert load_database_url({}, (env_file,)) == "postgresql+psycopg://pooler/db"


def test_database_url_falls_back_to_local():
    assert load_database_url({}, ()) == DEFAULT_DATABASE_URL
