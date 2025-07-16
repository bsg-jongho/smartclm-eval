"""
🔍 검색 스키마

문서 검색 및 RAG 관련 스키마를 정의합니다.
"""

from typing import List, Optional

from pydantic import Field

from src.core.schema import SchemaBase


class DocumentSearchRequest(SchemaBase):
    """문서 검색 요청 (시스템 RAG용)"""

    query: str = Field(..., description="검색 쿼리")
    doc_types: Optional[List[str]] = Field(
        None,
        description="문서 유형 필터 (law, guideline, standard_contract, precedent)",
    )
    top_k: int = Field(default=5, description="검색 결과 수")


class SearchResult(SchemaBase):
    """검색 결과"""

    document_id: int = Field(..., description="문서 ID")
    title: str = Field(..., description="문서 제목")
    doc_type: str = Field(..., description="문서 유형")
    category: Optional[str] = Field(None, description="세부 카테고리")
    content: str = Field(..., description="관련 내용")
    similarity_score: float = Field(..., description="유사도 점수")
    chunk_id: Optional[int] = Field(None, description="청크 ID")
    parent_context: Optional[str] = Field(None, description="전체 맥락")


class DocumentSearchResponse(SchemaBase):
    """문서 검색 응답"""

    query: str = Field(..., description="검색 쿼리")
    results: List[SearchResult] = Field(..., description="검색 결과")
    total_found: int = Field(..., description="총 검색 결과 수")
    search_time_ms: float = Field(..., description="검색 시간 (ms)")
