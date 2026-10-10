from app.core.config import DEFAULT_DATABASE_URL, load_api_token, load_cors_origins, load_database_url


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


def test_api_token_from_env_then_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("API_TOKEN=from-file\n")

    assert load_api_token({"API_TOKEN": "from-env"}, (env_file,)) == "from-env"
    assert load_api_token({}, (env_file,)) == "from-file"
    assert load_api_token({"API_TOKEN": ""}, ()) is None


def test_cors_origins_default_and_list():
    assert load_cors_origins({}) == ["http://localhost:5173"]
    assert load_cors_origins({"CORS_ORIGINS": "http://a:1, http://b:2 ,"}) == ["http://a:1", "http://b:2"]
