from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    odoo_url: str
    odoo_db: str
    odoo_username: str
    odoo_api_key: str

    cache_enabled: bool = True
    cache_ttl_seconds: int = 1800
    cache_db_path: str = "cache/reports.db"

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
