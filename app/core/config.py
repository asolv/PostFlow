from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # 앱 기본
    APP_NAME: str = "PostFlow"
    APP_ENV: str = "dev"
    CORS_ORIGINS: str = ""
    TZ: str = "Asia/Seoul"

    # 외부 키/엔드포인트
    SERPAPI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""   # ChatGPT 호출용 (필요 시 .env 에서 설정)
    OPENAI_MODEL: str = "gpt-4o"

    # DB
    DATABASE_URL: str = ""

    # 내부 작업 토큰(있다면 충돌 방지용으로 선언)
    JOB_TOKEN: str = ""        # .env 에 존재해도 에러 안 나도록 추가

    # RSS 기본값( .env 가 있으면 .env 값이 우선 )
    RSS_TITLE: str = "Internal Trend Feed"
    RSS_LINK: str = "https://example.com"
    RSS_DESCRIPTION: str = "Auto-generated RSS feed"

    # pydantic-settings v2
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",       # 정의되지 않은 환경 변수는 무시
    )

settings = Settings()

def cors_origins():
    if not settings.CORS_ORIGINS:
        return []
    return [x.strip() for x in settings.CORS_ORIGINS.split(",") if x.strip()]
