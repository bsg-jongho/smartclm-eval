"""
🔐 AWS Cognito API 서비스

순수 AWS Cognito API 호출만 담당:
- sign_up: Cognito 사용자 생성
- confirm_sign_up: 이메일 인증 확인
- authenticate: 사용자 인증
"""

from typing import Any, Dict, Optional

import aioboto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, status


class CognitoService:
    """AWS Cognito API 서비스 (순수 AWS 기능만)"""

    def __init__(
        self,
        user_pool_id: str,
        client_id: str,
        region: str,
    ):
        self.user_pool_id = user_pool_id
        self.client_id = client_id
        self.region = region
        self.session = aioboto3.Session()

    async def sign_up(
        self, email: str, password: str, name: str, department: Optional[str] = None
    ) -> Dict[str, Any]:
        """Cognito 사용자 생성"""
        try:
            user_attributes = [
                {"Name": "email", "Value": email},
                {"Name": "name", "Value": name},
            ]

            params = {
                "ClientId": self.client_id,
                "Username": email,
                "Password": password,
                "UserAttributes": user_attributes,
            }

            async with self.session.client(  # type: ignore
                "cognito-idp", region_name=self.region
            ) as cognito:
                response = await cognito.sign_up(**params)

                user_confirmed = response.get("UserConfirmed", False)

                return {
                    "user_id": response["UserSub"],
                    "status": "CONFIRMED" if user_confirmed else "UNCONFIRMED",
                    "message": "회원가입 완료! 바로 로그인하세요! 🎉"
                    if user_confirmed
                    else "회원가입 완료! 이메일에서 인증 코드를 확인하세요. 📧",
                }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]

            if error_code == "UsernameExistsException":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "이미 등록된 이메일입니다",
                        "code": "EMAIL_ALREADY_EXISTS",
                    },
                )
            elif error_code == "InvalidPasswordException":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "비밀번호는 8자 이상이며, 대문자, 소문자, 숫자, 특수문자를 포함해야 합니다",
                        "code": "INVALID_PASSWORD_FORMAT",
                    },
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": f"회원가입 중 오류가 발생했습니다: {str(e)}",
                        "code": "SIGNUP_ERROR",
                    },
                )

    async def confirm_sign_up(
        self, email: str, confirmation_code: str
    ) -> Dict[str, Any]:
        """이메일 인증 코드 확인"""
        try:
            params = {
                "ClientId": self.client_id,
                "Username": email,
                "ConfirmationCode": confirmation_code,
            }

            async with self.session.client(  # type: ignore
                "cognito-idp", region_name=self.region
            ) as cognito:
                await cognito.confirm_sign_up(**params)

            return {"message": "이메일 인증 완료! 이제 로그인하세요! 🎉"}

        except ClientError as e:
            error_code = e.response["Error"]["Code"]

            if error_code == "CodeMismatchException":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "인증 코드가 올바르지 않습니다. 다시 확인해주세요.",
                        "code": "INVALID_CONFIRMATION_CODE",
                    },
                )
            elif error_code == "ExpiredCodeException":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "인증 코드가 만료되었습니다. 새 코드를 요청하세요.",
                        "code": "EXPIRED_CONFIRMATION_CODE",
                    },
                )
            elif error_code == "AliasExistsException":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "이미 인증된 계정입니다. 바로 로그인하세요.",
                        "code": "ALREADY_CONFIRMED",
                    },
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": f"이메일 인증 중 오류가 발생했습니다: {str(e)}",
                        "code": "CONFIRMATION_ERROR",
                    },
                )

    async def resend_confirmation_code(self, email: str) -> Dict[str, Any]:
        """인증 코드 재발송"""
        try:
            params = {
                "ClientId": self.client_id,
                "Username": email,
            }

            async with self.session.client(  # type: ignore
                "cognito-idp", region_name=self.region
            ) as cognito:
                await cognito.resend_confirmation_code(**params)

            return {
                "message": "인증 코드가 재발송되었습니다. 이메일을 확인해주세요. 📧"
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]

            if error_code == "UserNotFoundException":
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "message": "등록되지 않은 이메일입니다.",
                        "code": "USER_NOT_FOUND",
                    },
                )
            elif error_code == "AliasExistsException":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "이미 인증된 계정입니다. 바로 로그인하세요.",
                        "code": "ALREADY_CONFIRMED",
                    },
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": f"인증 코드 재발송 중 오류가 발생했습니다: {str(e)}",
                        "code": "RESEND_ERROR",
                    },
                )

    async def authenticate(self, email: str, password: str) -> Dict[str, Any]:
        """Cognito 사용자 인증"""
        try:
            auth_parameters = {
                "USERNAME": email,
                "PASSWORD": password,
            }

            async with self.session.client(  # type: ignore
                "cognito-idp", region_name=self.region
            ) as cognito:
                response = await cognito.initiate_auth(
                    ClientId=self.client_id,
                    AuthFlow="USER_PASSWORD_AUTH",
                    AuthParameters=auth_parameters,
                )

                if "ChallengeName" in response:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "message": "계정 설정에 문제가 있습니다. 새로 가입해주세요.",
                            "code": "ACCOUNT_SETUP_REQUIRED",
                        },
                    )

                auth_result = response["AuthenticationResult"]
                return {
                    "access_token": auth_result["AccessToken"],
                    "refresh_token": auth_result["RefreshToken"],
                    "message": "로그인 성공",
                }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]

            if error_code == "NotAuthorizedException":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "message": "이메일 또는 비밀번호가 올바르지 않습니다",
                        "code": "INVALID_CREDENTIALS",
                    },
                )
            elif error_code == "UserNotFoundException":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "message": "이메일 또는 비밀번호가 올바르지 않습니다",
                        "code": "INVALID_CREDENTIALS",
                    },
                )
            elif error_code == "UserNotConfirmedException":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "이메일 인증이 필요합니다. 📧 이메일에서 인증 코드를 확인하고 POST /auth/confirm으로 인증을 완료하세요.",
                        "code": "EMAIL_VERIFICATION_REQUIRED",
                    },
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "로그인 중 오류가 발생했습니다",
                        "code": "LOGIN_ERROR",
                    },
                )

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh Token으로 새로운 Access Token 발급"""
        try:
            auth_parameters = {"REFRESH_TOKEN": refresh_token}

            async with self.session.client(  # type: ignore
                "cognito-idp", region_name=self.region
            ) as cognito:
                response = await cognito.initiate_auth(
                    ClientId=self.client_id,
                    AuthFlow="REFRESH_TOKEN_AUTH",
                    AuthParameters=auth_parameters,
                )

            auth_result = response["AuthenticationResult"]
            return {
                "access_token": auth_result["AccessToken"],
                "message": "토큰 갱신 성공",
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]

            if error_code == "NotAuthorizedException":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "message": "유효하지 않은 리프레시 토큰입니다. 다시 로그인하세요.",
                        "code": "INVALID_REFRESH_TOKEN",
                    },
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "토큰 갱신 중 오류가 발생했습니다",
                        "code": "TOKEN_REFRESH_ERROR",
                    },
                )

    async def admin_create_user(
        self, email: str, password: str, name: str, department: str = "시스템 관리팀"
    ) -> Dict[str, Any]:
        """관리자가 사용자 계정을 직접 생성 (이메일 인증 없이)"""
        try:
            user_attributes = [
                {"Name": "email", "Value": email},
                {"Name": "name", "Value": name},
                {"Name": "email_verified", "Value": "true"},  # 이메일 인증 건너뛰기
            ]

            async with self.session.client(  # type: ignore
                "cognito-idp", region_name=self.region
            ) as cognito:
                # 1. 사용자 생성 (CONFIRMED 상태로)
                response = await cognito.admin_create_user(
                    UserPoolId=self.user_pool_id,
                    Username=email,
                    UserAttributes=user_attributes,
                    TemporaryPassword=password,
                    MessageAction="SUPPRESS",  # 이메일 발송 안함
                )

                # 2. 비밀번호를 영구 설정 (임시 비밀번호 → 정식 비밀번호)
                await cognito.admin_set_user_password(
                    UserPoolId=self.user_pool_id,
                    Username=email,
                    Password=password,
                    Permanent=True,
                )

                # 3. ✅ Attributes에서 sub 값 찾기 (AWS 공식 문서 방식)
                user_attributes = response["User"]["Attributes"]
                user_sub = None
                for attr in user_attributes:
                    if attr["Name"] == "sub":
                        user_sub = attr["Value"]
                        break

                return {
                    "user_id": user_sub,  # ✅ 이제 올바른 sub 값 반환
                    "status": "CONFIRMED",
                    "message": "관리자 계정이 생성되었습니다. 바로 로그인 가능합니다! 🎉",
                }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]

            if error_code == "UsernameExistsException":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "이미 존재하는 계정입니다",
                        "code": "USER_ALREADY_EXISTS",
                    },
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": f"관리자 계정 생성 중 오류: {str(e)}",
                        "code": "ADMIN_CREATE_ERROR",
                    },
                )
