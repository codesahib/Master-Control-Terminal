import os
from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "Master Terminal API"
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@db:5432/master_terminal",
    )


settings = Settings()
