from sqlmodel import select

# === 관리자 계정 초기 데이터 ===
INITIAL_ADMIN_ACCOUNT = {
    "email": "admin@smartclm.com",
    "password": "SmartCLM2025!",  # 강력한 기본 비밀번호
    "name": "시스템 관리자",
    "role": "admin",  # 새로운 User 모델의 role 필드
}


async def insert_initial_admin_account(session):
    """초기 관리자 계정 생성 (이메일 인증 없이)"""
    from src.aws.cognito_service import CognitoService
    from src.core.config import settings
    from src.models import User  # 새로운 User 모델 사용

    # 관리자 계정이 이미 있는지 확인
    admin_query = select(User).where(User.role == "admin")
    result = await session.exec(admin_query)
    admin_user = result.first()

    if not admin_user:
        print("🔧 초기 관리자 계정 생성 중...")

        cognito_service = CognitoService(
            user_pool_id=settings.COGNITO_USER_POOL_ID,
            client_id=settings.COGNITO_CLIENT_ID,
            region=settings.AWS_REGION,
        )

        try:
            # Cognito에 관리자 계정 생성 (이메일 인증 없이)
            cognito_result = await cognito_service.admin_create_user(
                email=INITIAL_ADMIN_ACCOUNT["email"],
                password=INITIAL_ADMIN_ACCOUNT["password"],
                name=INITIAL_ADMIN_ACCOUNT["name"],
                department="",  # 빈 문자열로 전달 (새로운 User 모델에는 department 필드 없음)
            )

            # DB에도 저장 (새로운 User 모델 사용)
            admin_user = User(
                provider_id=cognito_result["user_id"],  # cognito_user_id → provider_id
                email=INITIAL_ADMIN_ACCOUNT["email"],
                name=INITIAL_ADMIN_ACCOUNT["name"],
                role=INITIAL_ADMIN_ACCOUNT["role"],  # enum 대신 문자열 사용
            )

            session.add(admin_user)
            await session.commit()
            print("✅ 초기 관리자 계정 생성 완료!")
            print(f"📧 이메일: {INITIAL_ADMIN_ACCOUNT['email']}")
            print(f"🔑 비밀번호: {INITIAL_ADMIN_ACCOUNT['password']}")
            print("🎯 이메일 인증 없이 바로 로그인 가능합니다!")

        except Exception as e:
            print(f"❌ 관리자 계정 생성 실패: {str(e)}")
    else:
        print("✅ 관리자 계정이 이미 존재합니다.")


# 새로운 통합 초기화 함수
async def insert_all_initial_data(session):
    """모든 초기 데이터 삽입"""
    # DocType 관련 제거 (새로운 모델에서는 metadata 필드 사용)
    await insert_initial_admin_account(session)
