from typing import Any, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

from src.auth.service import AuthService
from src.aws.cognito_service import CognitoService
from src.aws.dependency import get_cognito_service
from src.core.config import settings

# HTTP Bearer 토큰 스키마
oauth2_scheme = HTTPBearer()


def get_auth_service(
    cognito_service: CognitoService = Depends(get_cognito_service),
) -> AuthService:
    """AuthService 인스턴스 생성"""
    return AuthService(cognito_service)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
) -> Dict[str, Any]:
    """
    현재 로그인된 사용자 정보 추출 (토큰에서 바로!)

    사용법:
    - user["user_id"] : 사용자 ID
    - user["email"] : 이메일
    - user["name"] : 이름
    - user["role"] : 권한
    """
    try:
        token = credentials.credentials

        # 우리가 생성한 JWT 토큰에서 사용자 정보 추출
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )

        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "message": "토큰에 사용자 정보가 없습니다",
                    "code": "INVALID_TOKEN",
                },
            )

        return {
            "user_id": user_id,
            "email": payload.get("email"),
            "name": payload.get("name"),
            "role": payload.get("role"),
        }

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "토큰이 만료되었습니다", "code": "TOKEN_EXPIRED"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "유효하지 않은 토큰입니다", "code": "INVALID_TOKEN"},
        )


# 나중에 role 기반 권한 체크용 데코레이터들
def require_role(required_role: str):
    """특정 role이 필요한 API를 위한 dependency"""

    def role_checker(user: Dict[str, Any] = Depends(get_current_user)):
        if user["role"] != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": f"이 기능은 {required_role} 권한이 필요합니다",
                    "code": "INSUFFICIENT_PERMISSIONS",
                },
            )
        return user

    return role_checker


def require_roles(required_roles: list[str]):
    """여러 role 중 하나가 필요한 API를 위한 dependency"""

    def role_checker(user: Dict[str, Any] = Depends(get_current_user)):
        if user["role"] not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": f"이 기능은 다음 권한 중 하나가 필요합니다: {', '.join(required_roles)}",
                    "code": "INSUFFICIENT_PERMISSIONS",
                },
            )
        return user

    return role_checker
