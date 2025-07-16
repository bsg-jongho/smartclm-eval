"""
🔐 인증 비즈니스 로직 서비스

AWS Cognito 기능을 활용한 인증 비즈니스 로직 처리:
- 회원가입 플로우 관리
- 로그인 플로우 관리
- JWT 토큰 생성
- 사용자 정보 관리
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from jose import jwt
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.auth.schema import (
    ConfirmSignUpRequest,
    EmailVerificationData,
    LoginData,
    LoginRequest,
    LogoutData,
    ProfileData,
    RefreshTokenData,
    RefreshTokenRequest,
    ResendConfirmationRequest,
    SignUpData,
    SignUpRequest,
    UserInfo,
)
from src.aws.cognito_service import CognitoService
from src.core.config import settings
from src.models import User  # 새로운 User 모델 사용


class AuthService:
    """인증 비즈니스 로직 서비스"""

    def __init__(self, cognito_service: CognitoService):
        self.cognito = cognito_service

    async def sign_up(
        self, request: SignUpRequest, session: AsyncSession
    ) -> SignUpData:
        """
        회원가입 플로우

        1. DB 중복 체크
        2. Cognito 계정 생성
        3. DB 사용자 정보 저장
        4. 이메일 인증 필요 메시지 반환
        """
        # 1. DB 중복 확인
        existing_user = await session.exec(
            select(User).where(User.email == request.email)
        )
        if existing_user.first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "이미 등록된 이메일입니다",
                    "code": "EMAIL_ALREADY_EXISTS",
                },
            )

        # 2. Cognito 계정 생성
        cognito_result = await self.cognito.sign_up(
            email=request.email,
            password=request.password,
            name=request.name,
            department="",  # 빈 문자열로 전달
        )

        # 3. DB 사용자 정보 저장 (새로운 User 모델 사용)
        new_user = User(
            provider_id=cognito_result["user_id"],  # cognito_user_id → provider_id
            email=request.email,
            name=request.name,
            role="user",  # 기본값 변경: legal_user → user
        )

        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)

        # 4. 이메일 인증 필요 메시지 반환 (바로 로그인 시도하지 않음)
        return SignUpData(
            email=new_user.email,
            name=new_user.name,
            access_token="",  # 인증 후 별도 로그인 필요
            refresh_token="",  # 인증 후 별도 로그인 필요
            status=cognito_result["status"],  # Cognito에서 반환한 상태 사용
        )

    async def confirm_sign_up(
        self, request: ConfirmSignUpRequest, session: AsyncSession
    ) -> EmailVerificationData:
        """이메일 인증 코드 확인"""
        result = await self.cognito.confirm_sign_up(
            email=request.email,
            confirmation_code=request.confirmation_code,
        )

        # DB에서 사용자 정보 조회
        user_result = await session.exec(
            select(User).where(User.email == request.email)
        )
        user = user_result.first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "message": "사용자 정보를 찾을 수 없습니다",
                    "code": "USER_NOT_FOUND",
                },
            )

        # 인증 완료 후 별도 로그인 필요 (보안상 비밀번호 없이 로그인 불가)
        return EmailVerificationData(
            email=user.email,
            name=user.name,
            status="CONFIRMED",  # 인증 완료 상태
            next_step="LOGIN",  # 다음 단계는 로그인
        )

    async def login(self, request: LoginRequest, session: AsyncSession) -> LoginData:
        """
        로그인 플로우

        1. DB에서 사용자 조회
        2. Cognito 인증
        3. 사용자 정보 포함한 JWT 토큰 생성
        """
        # 1. DB에서 사용자 조회
        user_result = await session.exec(
            select(User).where(User.email == request.email)
        )
        user = user_result.first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "message": "이메일 또는 비밀번호가 올바르지 않습니다",
                    "code": "INVALID_CREDENTIALS",
                },
            )

        # 2. Cognito 인증 (UserNotConfirmedException 처리됨)
        try:
            cognito_result = await self.cognito.authenticate(
                email=request.email,
                password=request.password,
            )
        except HTTPException as e:
            # 이메일 인증이 필요한 경우, 사용자 정보와 함께 에러 반환
            if e.detail.get("code") == "EMAIL_VERIFICATION_REQUIRED":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "이메일 인증이 필요합니다. 📧 이메일에서 인증 코드를 확인하고 인증을 완료하세요.",
                        "code": "EMAIL_VERIFICATION_REQUIRED",
                        "email": user.email,  # 이메일 인증 페이지로 이동할 때 사용
                        "name": user.name,
                    },
                )
            raise e

        # 3. 사용자 정보 포함한 JWT 토큰 생성
        access_token = self._create_access_token(user)

        return LoginData(
            access_token=access_token,
            refresh_token=cognito_result["refresh_token"],
            user=UserInfo(
                id=user.id or 0,
                email=user.email,
                name=user.name,
                role=user.role,
            ),
        )

    async def refresh_token(
        self, request: RefreshTokenRequest, session: AsyncSession
    ) -> RefreshTokenData:
        """토큰 갱신"""
        # 1. Cognito로 새 액세스 토큰 발급 (검증용)
        cognito_result = await self.cognito.refresh_access_token(request.refresh_token)

        # 2. Cognito 액세스 토큰에서 사용자 ID 추출
        cognito_payload = jwt.get_unverified_claims(cognito_result["access_token"])
        cognito_user_id = cognito_payload.get("sub")

        if not cognito_user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "message": "토큰에서 사용자 정보를 찾을 수 없습니다",
                    "code": "INVALID_TOKEN",
                },
            )

        # 3. DB에서 사용자 정보 조회 (provider_id로 변경)
        user_result = await session.exec(
            select(User).where(
                User.provider_id == cognito_user_id
            )  # cognito_user_id → provider_id
        )
        user = user_result.first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "message": "사용자를 찾을 수 없습니다",
                    "code": "USER_NOT_FOUND",
                },
            )

        # 4. 새로운 자체 JWT 토큰 생성 (DB 정보 포함)
        new_access_token = self._create_access_token(user)

        return RefreshTokenData(
            access_token=new_access_token,  # ✅ 자체 JWT (DB 정보 포함)
        )

    async def logout(self, access_token: str) -> LogoutData:
        """로그아웃"""
        # 실제로는 클라이언트에서 토큰을 삭제하면 되므로 간단히 처리
        return LogoutData(
            message="로그아웃 완료",
            logged_out_at=datetime.now(timezone.utc).isoformat(),
        )

    async def get_profile(self, user_id: int, session: AsyncSession) -> ProfileData:
        """사용자 프로필 조회"""
        user_result = await session.exec(select(User).where(User.id == user_id))
        user = user_result.first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "message": "사용자를 찾을 수 없습니다",
                    "code": "USER_NOT_FOUND",
                },
            )

        return ProfileData(
            id=user.id or 0,
            email=user.email,
            name=user.name,
            role=user.role,
            created_at=user.created_at.isoformat() if user.created_at else "",
        )

    async def resend_confirmation_code(
        self, request: ResendConfirmationRequest
    ) -> EmailVerificationData:
        """인증 코드 재발송"""
        result = await self.cognito.resend_confirmation_code(request.email)

        return EmailVerificationData(
            email=request.email,
            name="",  # 재발송 시에는 이름을 모름
            status="UNCONFIRMED",  # 아직 인증되지 않은 상태
            next_step="CONFIRM",  # 다음 단계는 인증 코드 입력
        )

    def _create_access_token(self, user: User) -> str:
        """사용자 정보를 포함한 JWT 토큰 생성"""
        payload = {
            "user_id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int(
                datetime.now(timezone.utc).timestamp()
                + (settings.JWT_ACCESS_TOKEN_EXPIRE_HOURS * 3600)
            ),
        }

        return jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
