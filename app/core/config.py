from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "PostFlow"
    APP_ENV: str = "dev"
    CORS_ORIGINS: str = ""
    TZ: str = "Asia/Seoul"

    SERPAPI_API_KEY: str = ""
    DATABASE_URL: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()

def cors_origins():
    if not settings.CORS_ORIGINS:
        return []
    return [x.strip() for x in settings.CORS_ORIGINS.split(",") if x.strip()]
