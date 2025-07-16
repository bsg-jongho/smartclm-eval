from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel.ext.asyncio.session import AsyncSession

from src.auth.dependency import require_role
from src.core.database import get_session
from src.core.schema import ApiResponse, create_success_response
from src.documents.admin_service import admin_document_service
from src.documents.schema import (
    AdminDocumentUploadRequest,
    DocumentInfo,
    DocumentUploadResponse,
)

router = APIRouter(prefix="/admin/documents", tags=["📚 어드민 문서 관리"])


def to_camel_case(s):
    parts = s.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


def dict_keys_to_camel(d):
    if isinstance(d, dict):
        return {to_camel_case(k): dict_keys_to_camel(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [dict_keys_to_camel(i) for i in d]
    else:
        return d


# ═══════════════════════════════════════════════════════════════════════════════
# 📚 시스템 RAG용 문서 업로드 (어드민 전용)
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/upload", response_model=ApiResponse[DocumentUploadResponse])
async def upload_system_document(
    file: UploadFile = File(..., description="업로드할 문서 파일"),
    doc_type: str = Form(
        ...,
        description="문서 유형 (law, guideline, standard_contract, executed_contract, precedent)",
    ),
    user: dict = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    """
    📚 시스템 RAG용 문서 업로드 (어드민 전용)

    시스템 RAG에 사용될 신뢰할 수 있는 문서들을 업로드합니다.
    업로드된 문서는 전역적으로 모든 사용자가 검색할 수 있습니다.

    **지원 문서 유형:**
    - `law`: 법령 (민법, 상법, 노동법 등)
    - `guideline`: 가이드라인 (정부 지침, 업계 표준 등)
    - `standard_contract`: 표준계약서 (업계 표준 템플릿)
    - `executed_contract`: 체결된 계약서 (기존에 체결된 실제 계약서들)
    - `precedent`: 판례 (법원 판결문, 해석례 등)

    **특징:**
    - 전역 문서로 저장
    - 버전 관리 없음
    - LLM이 자동으로 제목, 카테고리, 설명 분석
    - 모든 사용자의 검색에 포함됨

    **문서 크기 제한:**
    - 최대 50MB 파일 크기
    - 문서 유형별 내용 제한 (토큰 효율성)
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

        # 문서 유형 검증
        valid_doc_types = [
            "law",
            "guideline",
            "standard_contract",
            "executed_contract",
            "precedent",
        ]
        if doc_type not in valid_doc_types:
            raise HTTPException(
                status_code=400,
                detail=f"지원하지 않는 문서 유형입니다. 지원 유형: {', '.join(valid_doc_types)}",
            )

        request = AdminDocumentUploadRequest(doc_type=doc_type)

        result = await admin_document_service.upload_system_document(
            file=file,
            request=request,
            user_id=user["user_id"],
            session=session,
        )

        return create_success_response(
            data=result,
            message=f"시스템 RAG용 문서 '{result.title}'이 성공적으로 업로드되었습니다",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# 📋 시스템 RAG용 문서 목록 (어드민 전용)
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/list")
async def list_system_documents(
    doc_type: Optional[str] = None,
    user: dict = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    """
    📋 시스템 RAG용 문서 목록 조회 (어드민 전용)

    시스템 RAG에 등록된 문서들의 목록을 조회합니다.
    문서 유형별로 필터링할 수 있습니다.

    **조회 대상:**
    - 전역 문서들 (room_id = NULL)
    - 법령, 가이드라인, 표준계약서, 체결된 계약서, 판례

    **지원 문서 유형:**
    - law: 법령
    - guideline: 가이드라인
    - standard_contract: 표준계약서
    - executed_contract: 체결된 계약서
    - precedent: 판례
    """
    try:
        from src.documents.admin_service import AdminDocumentService

        admin_service = AdminDocumentService()
        documents_data = await admin_service.list_global_documents(
            doc_type=doc_type, session=session
        )

        # DocumentInfo 형태로 변환
        documents = []
        for doc_data in documents_data:
            original_extension = (
                doc_data["filename"].split(".")[-1].lower()
                if doc_data["filename"]
                else None
            )
            doc_dict = DocumentInfo(
                id=doc_data["id"],
                title=doc_data["title"],
                filename=doc_data["filename"],
                pdf_filename=doc_data.get("pdf_filename"),
                pdf_file_size=doc_data.get("pdf_file_size"),
                original_extension=original_extension,
                doc_type=doc_data["doc_type"],
                category=doc_data["category"],
                room_id=doc_data["room_id"],  # None (전역 문서)
                file_size=doc_data["file_size"],
                page_count=doc_data["page_count"],
                processing_status=doc_data["processing_status"],
                created_at=doc_data["created_at"],
                document_metadata=doc_data["document_metadata"],
                auto_tags=doc_data["auto_tags"],
            ).dict()
            documents.append(doc_dict)

        # 문서 리스트 전체를 카멜케이스로 변환
        documents = [dict_keys_to_camel(doc) for doc in documents]

        # docType별로 정리된 메시지 생성
        if doc_type:
            message = f"📋 {doc_type} 문서 목록: {len(documents)}개"
        else:
            doc_type_counts = {}
            for doc in documents:
                dt = dict(doc).get("docType", "")
                doc_type_counts[dt] = doc_type_counts.get(dt, 0) + 1
            type_summary = ", ".join(
                [f"{k}: {v}개" for k, v in doc_type_counts.items()]
            )
            message = f"📋 전역 문서 목록: 총 {len(documents)}개 ({type_summary})"

        return {
            "data": documents,
            "total": len(documents),
            "message": message,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
