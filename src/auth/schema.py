"""
🔐 PoC용 Cognito 기반 간편 인증 스키마

사용자가 직접 회원가입하고 바로 로그인할 수 있는 시스템
관리자가 계정 생성해서 나눠주는 방식 ❌
사용자가 직접 가입하는 방식 ✅
"""

from pydantic import EmailStr, Field

from src.core.schema import SchemaBase

# ═══════════════════════════════════════════════════════════════════════════════
# 🎯 회원가입 스키마
# ═══════════════════════════════════════════════════════════════════════════════


class SignUpRequest(SchemaBase):
    email: EmailStr = Field(..., description="이메일 주소")
    password: str = Field(
        ...,
        min_length=8,
        description="비밀번호 (8자 이상, 대소문자+숫자+특수문자 포함)",
    )
    name: str = Field(..., min_length=2, max_length=50, description="이름")


class SignUpData(SchemaBase):
    """회원가입 성공 시 반환 데이터"""

    email: str = Field(..., description="이메일")
    name: str = Field(..., description="이름")
    access_token: str = Field(..., description="JWT 액세스 토큰")
    refresh_token: str = Field(..., description="Cognito 리프레시 토큰")
    status: str = Field(
        ..., description="상태 (UNCONFIRMED: 이메일 인증 필요, CONFIRMED: 인증 완료)"
    )


class ConfirmSignUpRequest(SchemaBase):
    """이메일 인증 코드 확인 (필요시)"""

    email: EmailStr = Field(..., description="이메일 주소")
    confirmation_code: str = Field(..., description="이메일로 받은 인증 코드")


class ResendConfirmationRequest(SchemaBase):
    """인증 코드 재발송 요청"""

    email: EmailStr = Field(..., description="이메일 주소")


class EmailVerificationData(SchemaBase):
    """이메일 인증 완료 시 반환 데이터"""

    email: str = Field(..., description="이메일")
    name: str = Field(..., description="이름")
    status: str = Field(..., description="상태 (CONFIRMED: 인증 완료)")
    next_step: str = Field(..., description="다음 단계 (LOGIN: 로그인 필요)")


# ═══════════════════════════════════════════════════════════════════════════════
# 🎯 로그인 스키마
# ═══════════════════════════════════════════════════════════════════════════════


class LoginRequest(SchemaBase):
    """로그인 요청"""

    email: EmailStr = Field(..., description="이메일 주소")
    password: str = Field(..., description="비밀번호")


class UserInfo(SchemaBase):
    """사용자 정보"""

    id: int = Field(..., description="사용자 ID")
    email: str = Field(..., description="이메일")
    name: str = Field(..., description="이름")
    role: str = Field(default="user", description="권한")


class LoginData(SchemaBase):
    """로그인 성공 시 반환 데이터"""

    access_token: str = Field(..., description="JWT 액세스 토큰")
    refresh_token: str = Field(..., description="Cognito 리프레시 토큰")
    user: UserInfo = Field(..., description="사용자 정보")


# ═══════════════════════════════════════════════════════════════════════════════
# 🎯 토큰 관리 스키마
# ═══════════════════════════════════════════════════════════════════════════════


class RefreshTokenRequest(SchemaBase):
    """토큰 갱신 요청"""

    refresh_token: str = Field(..., description="리프레시 토큰")


class RefreshTokenData(SchemaBase):
    """토큰 갱신 성공 시 반환 데이터"""

    access_token: str = Field(..., description="새 액세스 토큰")


# ═══════════════════════════════════════════════════════════════════════════════
# 🎯 기타 스키마
# ═══════════════════════════════════════════════════════════════════════════════


class ProfileData(SchemaBase):
    """프로필 조회 데이터"""

    id: int = Field(..., description="사용자 ID")
    email: str = Field(..., description="이메일")
    name: str = Field(..., description="이름")
    role: str = Field(..., description="권한")
    created_at: str = Field(..., description="가입일")


class LogoutData(SchemaBase):
    """로그아웃 데이터"""

    message: str = Field(default="로그아웃 완료", description="메시지")
    logged_out_at: str = Field(..., description="로그아웃 시간")


class PasswordChangeRequest(SchemaBase):
    """비밀번호 변경 요청"""

    old_password: str = Field(..., description="현재 비밀번호")
    new_password: str = Field(..., min_length=8, description="새 비밀번호 (8자 이상)")
