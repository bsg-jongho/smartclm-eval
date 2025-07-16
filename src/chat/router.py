"""
🤖 채팅 라우터

AI 챗봇 및 대화 기능을 제공하는 라우터입니다.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from src.auth.dependency import get_current_user
from src.core.database import get_session

from .schema import (
    StreamingChatRequest,
    StreamingContractDraftImprovementRequest,
    StreamingContractLegalAnalysisRequest,
)
from .service import chat_service

router = APIRouter(prefix="/chat", tags=["문서 AI"])


# ═══════════════════════════════════════════════════════════════════════════════
# 🔄 스트리밍 채팅
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/qa/stream")
async def streaming_chat_with_documents(
    request: StreamingChatRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    🔄 스트리밍 채팅 (일반)

    실시간으로 AI 응답을 스트리밍으로 받을 수 있습니다.

    **특징:**
    - 실시간 응답 스트리밍
    - 긴 응답도 빠르게 시작
    - 토큰별 실시간 전송
    - 문서 기반 질의응답 (RAG)
    - 기록 저장 안함
    """
    try:

        async def generate_stream():
            async for chunk in chat_service.streaming_chat(
                request=request,
                user_id=user["user_id"],
                session=session,
            ):
                yield f"data: {chunk.model_dump_json()}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/draft/stream")
async def streaming_contract_draft_improvement(
    request: StreamingContractDraftImprovementRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    계약서 초안 작성 및 조항 개선 스트리밍

    **주요 기능:**
    - 계약서 초안 작성 및 조항 생성
    - 기존 조항의 개선 및 보완
    - 표준 계약서 조항 제안
    - 법적 요구사항을 반영한 조항 작성

    **특징:**
    - 실시간 스트리밍 응답
    - 방별 문서 + 시스템 문서 하이브리드 RAG
    - 표준계약서, 가이드라인, 법령 기반
    """
    try:

        async def generate_stream():
            async for chunk in chat_service.streaming_contract_draft_improvement(
                request=request,
                user_id=user["user_id"],
                session=session,
            ):
                yield f"data: {chunk.model_dump_json()}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/legal-analysis/stream")
async def streaming_contract_legal_analysis(
    request: StreamingContractLegalAnalysisRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    계약서 조항 분석 및 법적 위험 분석 스트리밍

    **주요 기능:**
    - 계약서 조항별 상세 분석
    - 법적 유효성 및 위험요소 진단
    - 무효 조항 및 취소 가능 조항 식별
    - 불공정 약관 여부 판단
    - 분쟁 가능성 및 예방 방안 검토

    **특징:**
    - 실시간 스트리밍 응답
    - 방별 문서 + 시스템 문서 하이브리드 RAG
    - 법령, 판례, 가이드라인 기반
    - 위험도 평가 (높음/중간/낮음/안전)
    """
    try:

        async def generate_stream():
            async for chunk in chat_service.streaming_contract_legal_analysis(
                request=request,
                user_id=user["user_id"],
                session=session,
            ):
                yield f"data: {chunk.model_dump_json()}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
