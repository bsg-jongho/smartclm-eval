from src.aws.cognito_service import CognitoService
from src.aws.s3_service import S3Service
from src.core.config import settings


def get_cognito_service() -> CognitoService:
    return CognitoService(
        user_pool_id=settings.COGNITO_USER_POOL_ID,
        client_id=settings.COGNITO_CLIENT_ID,
        region=settings.AWS_REGION,
    )


def get_s3_service() -> S3Service:
    """S3 서비스 의존성 (기본 설정 사용)"""
    return S3Service(
        region_name=settings.AWS_REGION,
        default_bucket=settings.S3_BUCKET_NAME,
    )
