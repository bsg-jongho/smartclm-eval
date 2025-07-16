"""
🔍 검색 라우터

문서 검색 및 RAG 기능을 제공하는 라우터입니다.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from src.auth.dependency import get_current_user
from src.core.database import get_session
from src.core.schema import ApiResponse, create_success_response

from .schema import DocumentSearchRequest, DocumentSearchResponse
from .service import search_service

router = APIRouter(prefix="/search", tags=["🔍 문서 검색"])


# ═══════════════════════════════════════════════════════════════════════════════
# 🔍 기본 문서 검색
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/documents", response_model=ApiResponse[DocumentSearchResponse])
async def search_documents(
    request: DocumentSearchRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    🔍 시스템 RAG 문서 검색

    시스템 RAG용 문서들(법령, 가이드라인, 표준계약서, 판례)에서 의미 기반 검색을 수행합니다.

    **검색 범위:**
    - 전역 문서만 (시스템 RAG용)
    - 모든 사용자가 동일한 검색 결과

    **검색 기능:**
    - 벡터 기반 의미 검색
    - 문서 유형별 필터링 (law, guideline, standard_contract, precedent)
    - Parent-Child 청크 구조로 전체 맥락 제공
    """
    try:
        result = await search_service.search_documents(request=request, session=session)

        return create_success_response(
            data=result,
            message=f"'{request.query}' 검색 결과: {result.total_found}개 문서",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
