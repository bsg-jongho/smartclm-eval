"""
🤖 채팅 스키마

AI 챗봇 및 대화 관련 스키마를 정의합니다.
"""

from typing import List, Optional

from pydantic import Field

from src.core.schema import SchemaBase


class StreamingChatRequest(SchemaBase):
    """스트리밍 채팅 요청 (일반)"""

    question: str = Field(..., description="질문")
    document_id: int = Field(..., description="질문 기준이 되는 문서 ID")
    model: Optional[str] = Field(default="claude-3-sonnet", description="사용할 모델")
    max_tokens: Optional[int] = Field(default=2000, description="최대 토큰 수")


class StreamingChatResponse(SchemaBase):
    """스트리밍 채팅 응답"""

    chunk: str = Field(..., description="응답 청크")
    is_complete: bool = Field(..., description="완료 여부")
    token_usage: Optional[dict] = Field(None, description="토큰 사용량")
    sources: Optional[List[dict]] = Field(None, description="참고 자료 (완료 시에만)")


class StreamingContractDraftImprovementRequest(SchemaBase):
    """계약서 초안 작성 및 조항 개선 스트리밍 요청"""

    question: str = Field(..., description="질문 또는 요청")
    document_id: Optional[int] = Field(None, description="표준계약서 원본 문서 ID")
    context_text: Optional[str] = Field(
        None, description="작성/개선하려는 조항 또는 문맥"
    )
    room_id: Optional[int] = Field(None, description="방 ID (선택)")
    model: Optional[str] = Field(default="claude-3-sonnet", description="사용할 모델")
    max_tokens: Optional[int] = Field(default=2000, description="최대 토큰 수")


class StreamingContractLegalAnalysisRequest(SchemaBase):
    """계약서 조항 분석 및 법적 위험 분석 스트리밍 요청"""

    question: str = Field(..., description="질문 또는 요청")
    document_id: Optional[int] = Field(None, description="분석할 계약서 문서 ID")
    context_text: Optional[str] = Field(None, description="분석할 조항/부분의 원문")
    room_id: Optional[int] = Field(None, description="방 ID (선택)")
    model: Optional[str] = Field(default="claude-3-sonnet", description="사용할 모델")
    max_tokens: Optional[int] = Field(default=2000, description="최대 토큰 수")


class StreamingContractResponse(SchemaBase):
    """계약서 관련 스트리밍 응답"""

    chunk: str = Field(..., description="응답 청크")
    is_complete: bool = Field(..., description="완료 여부")
    token_usage: Optional[dict] = Field(None, description="토큰 사용량")
    sources: Optional[List[dict]] = Field(None, description="참고 자료 (완료 시에만)")
