"""
📊 모니터링 API 라우터

토큰 사용량, 성능 지표, 사용량 분석 등을 위한 API 엔드포인트
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from src.auth.dependency import get_current_user
from src.core.database import get_session
from src.core.schema import ApiResponse, create_success_response
from src.documents.schema import TokenUsageListResponse
from src.monitoring.service import monitoring_service

router = APIRouter(prefix="/monitoring", tags=["📊 모니터링"])


# ═══════════════════════════════════════════════════════════════════════════════
# 💰 사용자별 토큰 사용량 조회
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/token-usage/user", response_model=ApiResponse[TokenUsageListResponse])
async def get_user_token_usage(
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    💰 사용자별 토큰 사용량 조회

    현재 사용자의 LLM 토큰 사용량과 비용을 조회합니다.
    """
    try:
        result = await monitoring_service.get_user_token_usage(
            user_id=user["id"], session=session, limit=limit, offset=offset
        )
        return create_success_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 💰 방별 토큰 사용량 조회
# ═══════════════════════════════════════════════════════════════════════════════


@router.get(
    "/token-usage/room/{room_id}", response_model=ApiResponse[TokenUsageListResponse]
)
async def get_room_token_usage(
    room_id: int,
    limit: int = 50,
    offset: int = 0,
    # user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    💰 방별 토큰 사용량 조회

    특정 방의 LLM 토큰 사용량과 비용을 조회합니다.
    """
    try:
        result = await monitoring_service.get_room_token_usage(
            room_id=room_id, session=session, limit=limit, offset=offset
        )
        return create_success_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 💰 시스템 전체 토큰 사용량 조회 (어드민 전용)
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/token-usage/system", response_model=ApiResponse[TokenUsageListResponse])
async def get_system_token_usage(
    limit: int = 50,
    offset: int = 0,
    # user: dict = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    """
    💰 시스템 전체 토큰 사용량 조회 (어드민 전용)

    전체 시스템의 LLM 토큰 사용량과 비용을 조회합니다.
    """
    try:
        result = await monitoring_service.get_system_token_usage(
            session=session, limit=limit, offset=offset
        )
        return create_success_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
