import os
from typing import List

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 파일 로드
load_dotenv()


class Settings(BaseSettings):
    # 기본 API 설정
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "SmartCLM PoC API Server"
    PROJECT_DESCRIPTION: str = "SmartCLM PoC API Server"
    PROJECT_VERSION: str = "0.1.0"

    # CORS 설정
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",  # web & admin development
        "https://localhost:5174",  # addin development
        "https://dev.smartclm.com",  # web production
        "https://dev-addin.smartclm.com",  # addin production
    ]

    # 데이터베이스 설정
    DATABASE_HOST: str = os.getenv("DATABASE_HOST", "")
    DATABASE_PORT: str = os.getenv("DATABASE_PORT", "")
    DATABASE_USER: str = os.getenv("DATABASE_USER", "")
    DATABASE_PASSWORD: str = os.getenv("DATABASE_PASSWORD", "")
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "")

    # AWS 기본 설정
    AWS_REGION: str = os.getenv("AWS_REGION", "ap-northeast-2")

    # Amazon Cognito 설정
    COGNITO_USER_POOL_ID: str = os.getenv("COGNITO_USER_POOL_ID", "")
    COGNITO_CLIENT_ID: str = os.getenv("COGNITO_CLIENT_ID", "")

    # JWT 설정
    JWT_SECRET_KEY: str = os.getenv(
        "JWT_SECRET_KEY", "your-super-secret-key-for-poc-development-only"
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_HOURS: int = 1

    # S3 설정
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "smartclm-test-contracts")

    @property
    def DATABASE_URL(self) -> str:
        """DATABASE_URL 환경변수가 있으면 사용, 없으면 개별 환경변수로 생성"""
        env_database_url = os.getenv("DATABASE_URL")
        if env_database_url:
            return env_database_url

        # 개별 환경변수로 DATABASE_URL 생성
        return f"postgresql+asyncpg://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=".env",
        extra="ignore",  # 정의되지 않은 환경변수 무시
    )


settings = Settings()
