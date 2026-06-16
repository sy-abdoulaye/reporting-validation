from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv
import secrets

load_dotenv()


def _generate_secret_key() -> str:
    return secrets.token_urlsafe(32)


class Settings(BaseSettings):
    SECRET_KEY: str = Field(default_factory=_generate_secret_key)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    AUTH_JWT_AUDIENCE: str = "reporting-app"
    AUTH_JWT_ISSUER: str = "reporting-app"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
