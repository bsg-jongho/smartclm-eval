"""
📄 통합 문서 관리 라우터

사용자 문서 업로드, 시스템 RAG 검색, AI 챗봇 기능을 제공합니다.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel.ext.asyncio.session import AsyncSession

from src.auth.dependency import get_current_user
from src.core.database import get_session
from src.core.schema import ApiResponse, create_success_response
from src.documents.schema import (
    DocumentComparisonRequest,
    DocumentComparisonResponse,
    DocumentUploadRequest,
    DocumentUploadResponse,
    DocumentWithOutlineResponse,
)
from src.documents.service import document_service

router = APIRouter(prefix="/documents", tags=["📄 사용자 문서 관리"])


# ═══════════════════════════════════════════════════════════════════════════════
# 📄 문서 업로드 (통합)
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/upload", response_model=ApiResponse[DocumentUploadResponse])
async def upload_document(
    file: UploadFile = File(..., description="업로드할 문서 파일"),
    room_id: int = Form(..., description="방 ID"),
    doc_type: str = Form(..., description="문서 유형 (contract)"),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    📄 계약서 업로드 및 처리

    사용자가 계약서를 업로드하면 서버에서 상세 분석을 수행합니다.
    방별로 버전 관리가 자동으로 이루어집니다.

    **지원 문서 유형:**
    - `contract`: 계약서 (모든 종류) - 자동 버전 관리 (v1, v2, v3...)

    **분석 항목:**
    - 문서 제목 및 카테고리
    - 상세 메타데이터 (당사자, 금액, 기간, 조항 등)
    - 독소조항 분석 및 법적 근거
    - 방별 버전 관리

    **문서 크기 제한:**
    - 최대 80페이지 (Claude 200K 토큰 제한 기준)
    - 최대 50MB 파일 크기
    """
    try:
        # 파일 형식 검증
        if not file.filename or not file.filename.lower().endswith(
            (".pdf", ".docx", ".doc", ".hwp", ".xlsx", ".xls", ".pptx", ".ppt")
        ):
            raise HTTPException(
                status_code=400,
                detail="PDF, DOCX, DOC, HWP, XLSX, XLS, PPTX, PPT 파일만 업로드 가능합니다",
            )

        # 계약서만 업로드 가능
        if doc_type != "contract":
            raise HTTPException(
                status_code=400,
                detail="일반 사용자는 계약서만 업로드할 수 있습니다. 시스템 RAG용 문서는 어드민이 관리합니다.",
            )

        request = DocumentUploadRequest(
            room_id=room_id,
            doc_type=doc_type,
        )

        result = await document_service.upload_document(
            file=file,
            request=request,
            user_id=user["user_id"],
            session=session,
        )

        return create_success_response(
            data=result,
            message=f"계약서 '{result.title}'이 성공적으로 업로드되었습니다 (버전: {result.version})",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_id}", response_model=DocumentWithOutlineResponse)
async def get_document_with_outline(
    document_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    📄 문서 상세 + outline(조항/청크 메타데이터) 반환
    """
    try:
        result = await document_service.get_document_with_outline(document_id, session)
        return result
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/compare-html", response_model=DocumentComparisonResponse)
async def compare_documents_html(
    request: DocumentComparisonRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    두 문서의 HTML 콘텐츠를 비교용으로 반환
    """
    try:
        result = await document_service.get_documents_for_comparison(
            document_id_1=request.document_id_1,
            document_id_2=request.document_id_2,
            session=session,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
