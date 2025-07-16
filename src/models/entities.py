from datetime import datetime
from typing import Dict, List, Optional

from pgvector.sqlalchemy import Vector
from sqlmodel import JSON, Column, Field, Relationship, Text

from src.core.model import Base


class User(Base, table=True):
    """사용자 정보"""

    id: Optional[int] = Field(default=None, primary_key=True)
    provider_id: str = Field(unique=True, max_length=255, description="Cognito User ID")
    email: str = Field(max_length=255, unique=True, index=True)
    name: str = Field(max_length=100)
    role: str = Field(default="user", max_length=20, description="권한(admin/user 등)")

    # 관계: User -> Room (1:N)
    rooms: List["Room"] = Relationship(back_populates="owner")

    # 관계: User -> TokenUsage (1:N)
    token_usages: List["TokenUsage"] = Relationship(back_populates="user")


class Room(Base, table=True):
    """계약/업무 단위의 방(Room)"""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None)

    # 외래키: Room -> User (N:1)
    owner_id: Optional[int] = Field(default=None, foreign_key="users.id")
    owner: Optional[User] = Relationship(back_populates="rooms")

    # 관계: Room -> Document (1:N)
    documents: List["Document"] = Relationship(back_populates="room")

    # 관계: Room -> Chunk (1:N) - 청크도 방에 속함
    # chunks: List["Chunk"] = Relationship(back_populates="room")


class Document(Base, table=True):
    """업로드된 모든 문서(계약서, 법령, 참고자료 등)"""

    id: Optional[int] = Field(default=None, primary_key=True)

    # 외래키: Document -> Room (N:1) - NULL = 전역 문서, 숫자 = 방별 문서
    room_id: Optional[int] = Field(default=None, foreign_key="rooms.id")

    doc_type: str = Field(max_length=50, index=True)  # 문서 유형 (contract, law 등)
    category: Optional[str] = Field(
        default=None, max_length=100, index=True
    )  # 세부 카테고리
    processing_status: str = Field(
        default="completed", max_length=20, index=True
    )  # 처리 상태

    filename: str = Field(max_length=255)  # 원본 파일명
    s3_bucket: str = Field(max_length=255)  # 원본 S3 버킷
    s3_key: str = Field(max_length=500)  # 원본 S3 키
    pdf_s3_bucket: str = Field(max_length=255)  # PDF S3 버킷
    pdf_s3_key: str = Field(max_length=500)  # PDF S3 키
    file_size: Optional[int] = Field(default=None)  # 원본 크기
    pdf_file_size: Optional[int] = Field(default=None)  # PDF 크기
    page_count: Optional[int] = Field(default=None)
    document_metadata: Optional[Dict] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    auto_tags: Optional[List[str]] = Field(default_factory=list, sa_column=Column(JSON))
    version: Optional[str] = Field(default=None, max_length=20)
    html_content: Optional[str] = Field(default=None, sa_column=Column(Text))
    markdown_content: Optional[str] = Field(default=None, sa_column=Column(Text))

    # 관계: Document -> Room (N:1)
    room: Optional[Room] = Relationship(back_populates="documents")

    # 관계: Document -> Chunk (1:N)
    chunks: List["Chunk"] = Relationship(back_populates="document")


class Chunk(Base, table=True):
    """모든 문서의 청크(RAG/AI 검색용)"""

    id: Optional[int] = Field(default=None, primary_key=True)

    # 외래키: Chunk -> Document (N:1)
    document_id: int = Field(foreign_key="documents.id")

    content: str = Field(sa_column=Column(Text))
    chunk_index: int = Field()
    header_1: Optional[str] = Field(default=None, max_length=200)
    header_2: Optional[str] = Field(default=None, max_length=200)
    header_3: Optional[str] = Field(default=None, max_length=200)
    header_4: Optional[str] = Field(default=None, max_length=200)
    parent_id: Optional[str] = Field(default=None, max_length=200)
    child_id: Optional[str] = Field(default=None, max_length=200)
    chunk_type: str = Field(default="child", max_length=20)
    embedding: Optional[List[float]] = Field(sa_type=Vector(1024), default=None)
    word_count: Optional[int] = Field(default=None)
    char_count: Optional[int] = Field(default=None)
    chunk_metadata: Optional[Dict] = Field(default_factory=dict, sa_column=Column(JSON))
    auto_tags: Optional[List[str]] = Field(default_factory=list, sa_column=Column(JSON))

    # 관계: Chunk -> Document (N:1)
    document: Optional[Document] = Relationship(back_populates="chunks")


class TokenUsage(Base, table=True):
    """LLM 토큰 사용량 및 비용 추적"""

    id: Optional[int] = Field(default=None, primary_key=True)

    # 외래키: TokenUsage -> User (N:1)
    user_id: int = Field(foreign_key="users.id")
    user: Optional[User] = Relationship(back_populates="token_usages")

    # 외래키: TokenUsage -> Room (N:1) - NULL = 전역 작업
    room_id: Optional[int] = Field(default=None, foreign_key="rooms.id")

    # 외래키: TokenUsage -> Document (N:1) - NULL = 문서 외 작업
    document_id: Optional[int] = Field(default=None, foreign_key="documents.id")

    # LLM 호출 정보
    operation_type: str = Field(
        max_length=50,
        description="작업 유형 (document_analysis, chat, translation, etc.)",
    )
    model_name: str = Field(max_length=100, description="사용된 LLM 모델명")

    # 토큰 사용량
    input_tokens: int = Field(description="입력 토큰 수")
    output_tokens: int = Field(description="출력 토큰 수")
    total_tokens: int = Field(description="총 토큰 수")

    # 비용 정보 (USD)
    input_cost: float = Field(description="입력 토큰 비용 (USD)")
    output_cost: float = Field(description="출력 토큰 비용 (USD)")
    total_cost: float = Field(description="총 비용 (USD)")

    # 성능 추적
    request_started_at: Optional[datetime] = Field(
        default=None, description="LLM 요청 시작 시간"
    )
    response_received_at: Optional[datetime] = Field(
        default=None, description="LLM 응답 수신 시간"
    )
    processing_time_ms: Optional[int] = Field(
        default=None, description="처리 시간 (밀리초)"
    )

    # 추가 메타데이터
    usage_metadata: Optional[Dict] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="추가 정보 (프롬프트 길이, 응답 길이 등)",
    )

    # 상태 정보
    status: str = Field(
        default="completed",
        max_length=20,
        description="상태 (completed, failed, cancelled)",
    )
    error_message: Optional[str] = Field(
        default=None, max_length=500, description="오류 메시지 (실패 시)"
    )
