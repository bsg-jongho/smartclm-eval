"""
📄 통합 문서 관리 스키마

기존 legal과 contracts 스키마를 새로운 Document 모델에 맞게 통합
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import Field

from src.core.schema import SchemaBase

# 문서 업로드, 검색, 챗봇 등 문서 중심 스키마만 유지
# ═══════════════════════════════════════════════════════════════════════════════
# 🎯 문서 업로드 스키마
# ═══════════════════════════════════════════════════════════════════════════════


class DocumentUploadRequest(SchemaBase):
    """문서 업로드 요청"""

    room_id: int = Field(..., description="방 ID")
    doc_type: str = Field(..., description="문서 유형 (contract, law)")


class AdminDocumentUploadRequest(SchemaBase):
    """어드민 전용 문서 업로드 요청"""

    doc_type: str = Field(
        ..., description="문서 유형 (law, guideline, standard_contract, precedent)"
    )


class ToxicClauseInfo(SchemaBase):
    """독소조항 정보"""

    clause_text: str = Field(..., description="독소조항 내용")
    clause_location: str = Field(..., description="조항 위치")
    legal_issues: List[Dict] = Field(default_factory=list, description="법적 문제점")
    precedents: List[Dict] = Field(default_factory=list, description="관련 판례")
    risk_level: str = Field(..., description="리스크 레벨")
    recommendations: List[str] = Field(
        default_factory=list, description="개선 권장사항"
    )


class ContractReviewAnalysis(SchemaBase):
    """계약서 검토 분석 결과"""

    summary: str = Field(..., description="계약서 핵심 요약")
    toxic_clauses: List[ToxicClauseInfo] = Field(
        default_factory=list, description="독소조항 목록"
    )
    overall_risk_assessment: str = Field(..., description="전체 리스크 평가")
    key_concerns: List[str] = Field(default_factory=list, description="주요 우려사항")
    compliance_status: Dict = Field(default_factory=dict, description="법적 준수 상태")
    recommendations: List[Dict] = Field(
        default_factory=list, description="전체 권장사항"
    )


class DocumentUploadResponse(SchemaBase):
    """문서 업로드 응답"""

    document_id: int = Field(..., description="문서 ID")
    title: str = Field(..., description="문서 제목")
    filename: str = Field(..., description="파일명")
    doc_type: str = Field(..., description="문서 유형")
    room_id: Optional[int] = Field(None, description="방 ID (None = 전역 문서)")
    version: Optional[str] = Field(None, description="버전 (계약서만)")
    processing_status: str = Field(..., description="처리 상태")
    created_at: datetime = Field(..., description="생성 시간")
    review_analysis: Optional[ContractReviewAnalysis] = Field(
        None, description="계약서 검토 분석 결과 (계약서만)"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 🎯 문서 조회 스키마
# ═══════════════════════════════════════════════════════════════════════════════


class DocumentInfo(SchemaBase):
    """문서 정보"""

    id: int = Field(..., description="문서 ID")
    title: Optional[str] = Field(None, description="문서 제목")
    filename: str = Field(..., description="파일명")
    file_size: Optional[int] = Field(None, description="원본 파일 크기")
    pdf_filename: Optional[str] = Field(None, description="PDF 파일명")
    pdf_file_size: Optional[int] = Field(None, description="PDF 파일 크기")
    original_extension: Optional[str] = Field(None, description="원본 파일 확장자")
    doc_type: str = Field(..., description="문서 유형")
    category: Optional[str] = Field(None, description="세부 카테고리")
    room_id: Optional[int] = Field(None, description="방 ID (None = 전역 문서)")
    page_count: Optional[int] = Field(None, description="페이지 수")
    processing_status: str = Field(..., description="처리 상태")
    created_at: datetime = Field(..., description="생성 시간")
    document_metadata: Dict = Field(default_factory=dict, description="메타데이터")
    auto_tags: List[str] = Field(default_factory=list, description="자동 태그")
    version: Optional[str] = Field(None, description="버전 (계약서만)")


class DocumentListResponse(SchemaBase):
    """문서 목록 응답"""

    documents: List[DocumentInfo] = Field(..., description="문서 목록")
    total_count: int = Field(..., description="총 문서 수")


# ═══════════════════════════════════════════════════════════════════════════════
# 💰 토큰 사용량 스키마
# ═══════════════════════════════════════════════════════════════════════════════


class TokenUsageSummary(SchemaBase):
    """토큰 사용량 요약"""

    total_tokens: int = Field(..., description="총 토큰 수")
    total_cost: float = Field(..., description="총 비용 (USD)")
    avg_processing_time_ms: float = Field(..., description="평균 처리 시간 (밀리초)")
    operation_count: int = Field(..., description="작업 수")


class TokenUsageDetail(SchemaBase):
    """토큰 사용량 상세"""

    id: int = Field(..., description="토큰 사용량 ID")
    operation_type: str = Field(..., description="작업 유형")
    model_name: str = Field(..., description="모델명")
    input_tokens: int = Field(..., description="입력 토큰 수")
    output_tokens: int = Field(..., description="출력 토큰 수")
    total_tokens: int = Field(..., description="총 토큰 수")
    total_cost: float = Field(..., description="총 비용 (USD)")
    processing_time_ms: Optional[int] = Field(
        default=None, description="처리 시간 (밀리초)"
    )
    created_at: datetime = Field(..., description="생성 시간")


class TokenUsageListResponse(SchemaBase):
    """토큰 사용량 목록 응답"""

    token_usages: List[TokenUsageDetail] = Field(..., description="토큰 사용량 목록")
    summary: TokenUsageSummary = Field(..., description="요약 정보")
    total_count: int = Field(..., description="총 레코드 수")


class OutlineSection(SchemaBase):
    """문서 outline(조항/청크) 정보"""

    section_id: str = Field(..., description="조항/섹션 고유 ID (parent_id 등)")
    title: str = Field(..., description="조항명(header_1)")
    chunk_index: int = Field(..., description="문서 내 순서")
    preview: Optional[str] = Field(None, description="조항 미리보기")
    page_index: Optional[int] = Field(None, description="PDF 내 페이지 번호")
    bbox: Optional[dict] = Field(None, description="PDF 내 위치 정보")
    dest: Optional[str] = Field(None, description="프론트 outline의 dest와 매핑")
    type: Optional[str] = Field(None, description="조항 유형")
    items: Optional[list] = Field(default_factory=list, description="하위 항목")


class DocumentWithOutlineResponse(SchemaBase):
    """문서 + outline(조항/청크 메타데이터) 응답"""

    document: DocumentInfo = Field(..., description="문서 정보")
    outline: list[OutlineSection] = Field(..., description="조항/청크 outline 리스트")


class DocumentHtmlContent(SchemaBase):
    """문서 HTML 콘텐츠"""

    document_id: int = Field(..., description="문서 ID")
    title: str = Field(..., description="문서 제목")
    filename: str = Field(..., description="파일명")
    html_content: Optional[str] = Field(None, description="HTML 콘텐츠")
    error: Optional[str] = Field(None, description="오류 메시지 (있는 경우)")


class DocumentComparisonRequest(SchemaBase):
    """문서 비교 요청"""

    document_id_1: int = Field(..., description="첫 번째 문서 ID")
    document_id_2: int = Field(..., description="두 번째 문서 ID")


class DocumentComparisonResponse(SchemaBase):
    """문서 비교 응답"""

    document_1: DocumentHtmlContent = Field(..., description="첫 번째 문서")
    document_2: DocumentHtmlContent = Field(..., description="두 번째 문서")
