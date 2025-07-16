from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from src.auth.dependency import get_auth_service, get_current_user
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
)
from src.auth.service import AuthService
from src.core.database import get_session
from src.core.schema import ApiResponse, create_success_response

router = APIRouter(prefix="/auth", tags=["🔐 인증"])
security = HTTPBearer()


# ═══════════════════════════════════════════════════════════════════════════════
# 🎯 회원가입 & 이메일 인증
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/signup", response_model=ApiResponse[SignUpData])
async def sign_up(
    request: SignUpRequest,
    session: AsyncSession = Depends(get_session),
    auth_service: AuthService = Depends(get_auth_service),
):
    try:
        result = await auth_service.sign_up(request, session)
        return create_success_response(data=result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"회원가입 중 오류가 발생했습니다: {str(e)}",
                "code": "SIGNUP_ERROR",
            },
        )


@router.post("/confirm", response_model=ApiResponse[EmailVerificationData])
async def confirm_sign_up(
    request: ConfirmSignUpRequest,
    session: AsyncSession = Depends(get_session),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    📧 이메일 인증 코드 확인

    회원가입 후 이메일로 받은 6자리 인증 코드를 입력하세요.
    인증 완료 후 바로 로그인할 수 있습니다! 🎉
    """
    try:
        result = await auth_service.confirm_sign_up(request, session)
        return create_success_response(
            data=result, message="이메일 인증 완료! 이제 로그인하세요! 🎉"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"이메일 인증 중 오류가 발생했습니다: {str(e)}",
                "code": "CONFIRMATION_ERROR",
            },
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 🎯 로그인 & 토큰 관리
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/login", response_model=ApiResponse[LoginData])
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_session),
    auth_service: AuthService = Depends(get_auth_service),
):
    try:
        result = await auth_service.login(request, session)
        return create_success_response(
            data=result, message=f"환영합니다, {result.user.name}님! 🎉"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"로그인 중 오류가 발생했습니다: {str(e)}",
                "code": "LOGIN_ERROR",
            },
        )


@router.post("/refresh", response_model=ApiResponse[RefreshTokenData])
async def refresh_token(
    request: RefreshTokenRequest,
    session: AsyncSession = Depends(get_session),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    🔄 토큰 갱신

    Access Token이 만료되면 Refresh Token으로 새로운 Access Token을 받으세요.
    재로그인 없이 계속 서비스를 이용할 수 있습니다!
    """
    try:
        result = await auth_service.refresh_token(request, session)
        return create_success_response(data=result, message="토큰 갱신 완료")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"토큰 갱신 중 오류가 발생했습니다: {str(e)}",
                "code": "REFRESH_ERROR",
            },
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 🎯 사용자 정보 & 로그아웃
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/me", response_model=ApiResponse[ProfileData])
async def get_profile(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    👤 내 프로필 조회

    로그인한 사용자의 정보를 확인할 수 있습니다.
    """
    try:
        result = await auth_service.get_profile(user["user_id"], session)
        return create_success_response(data=result, message="프로필 조회 성공")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"프로필 조회 중 오류가 발생했습니다: {str(e)}",
                "code": "PROFILE_ERROR",
            },
        )


@router.post("/logout", response_model=ApiResponse[LogoutData])
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    🚪 로그아웃

    클라이언트에서 토큰을 삭제하면 로그아웃됩니다.
    """
    try:
        access_token = credentials.credentials
        result = await auth_service.logout(access_token)
        return create_success_response(data=result, message="로그아웃 완료")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"로그아웃 중 오류가 발생했습니다: {str(e)}",
                "code": "LOGOUT_ERROR",
            },
        )


@router.post("/resend-confirmation", response_model=ApiResponse[EmailVerificationData])
async def resend_confirmation_code(
    request: ResendConfirmationRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    📧 인증 코드 재발송

    이메일 인증 코드를 받지 못했거나 만료된 경우 재발송할 수 있습니다.
    """
    try:
        result = await auth_service.resend_confirmation_code(request)
        return create_success_response(
            data=result,
            message="인증 코드가 재발송되었습니다. 이메일을 확인해주세요. 📧",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"인증 코드 재발송 중 오류가 발생했습니다: {str(e)}",
                "code": "RESEND_ERROR",
            },
        )
