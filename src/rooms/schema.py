from datetime import datetime
from typing import List, Optional

from src.core.schema import SchemaBase
from src.documents.schema import DocumentInfo


class RoomCreate(SchemaBase):
    """방 생성 요청"""

    pass


class RoomResponse(SchemaBase):
    """방 응답"""

    id: int
    title: Optional[str] = None
    description: Optional[str] = None
    owner_id: Optional[int] = None
    document_count: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RoomDetailResponse(SchemaBase):
    """방 상세 응답 (문서 정보 포함)"""

    id: int
    title: Optional[str] = None
    description: Optional[str] = None
    owner_id: Optional[int] = None
    document_count: int = 0
    created_at: Optional[datetime] = None
    documents: List[DocumentInfo] = []

    class Config:
        from_attributes = True


class RoomListResponse(SchemaBase):
    """방 목록 응답"""

    rooms: list[RoomResponse]
    total: int
