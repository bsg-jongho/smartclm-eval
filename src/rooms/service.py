"""
🏠 방(Room) 관리 서비스

계약/업무 단위의 방을 관리하는 서비스
"""

from typing import Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.utill import dict_keys_to_camel
from src.documents.repository import DocumentRepository
from src.documents.schema import DocumentInfo
from src.models import Document, Room

from .repository import room_repository
from .schema import RoomCreate, RoomDetailResponse, RoomResponse


class RoomService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_room(self, owner_id: int, room_create: RoomCreate) -> RoomResponse:
        """방 생성"""
        room = Room(
            name="Untitled",
            description=None,
            owner_id=owner_id,
        )
        room = await room_repository.create_room(room, self.session)
        return RoomResponse(
            id=room.id,
            title=room.name,
            description=room.description,
            owner_id=room.owner_id,
            document_count=0,
            created_at=room.created_at,
        )

    async def get_room(
        self, room_id: int, user_id: int, user_role: str = "user"
    ) -> Optional["RoomDetailResponse"]:
        """방 조회 (권한 검증 포함)"""
        room = await room_repository.get_room_by_id(room_id, self.session)
        if not room:
            return None

        # 권한 검증: 방 소유자 또는 관리자만 조회 가능
        if room.owner_id != user_id and user_role != "admin":
            return None

        # 문서 개수 및 문서 정보 조회
        document_repo = DocumentRepository()
        documents = await document_repo.get_documents_by_room(room_id, self.session)
        document_infos = []
        for doc in documents:
            ext = (
                doc.filename.split(".")[-1]
                if doc.filename and "." in doc.filename
                else None
            )
            pdf_filename = None
            if doc.filename and "." in doc.filename:
                pdf_filename = doc.filename.rsplit(".", 1)[0] + ".pdf"
            doc_info = DocumentInfo.from_orm(doc)
            doc_info.title = doc.filename  # filename을 title로 사용
            doc_info.original_extension = ext
            doc_info.pdf_filename = pdf_filename
            doc_info.version = doc.version
            # document_metadata를 camelCase로 변환
            if hasattr(doc_info, "document_metadata") and isinstance(
                doc_info.document_metadata, dict
            ):
                converted = dict_keys_to_camel(doc_info.document_metadata)
                if isinstance(converted, dict):
                    doc_info.document_metadata = converted
            document_infos.append(doc_info)

        return RoomDetailResponse(
            id=room.id,
            title=room.name,
            description=room.description,
            owner_id=room.owner_id,
            document_count=len(document_infos),
            created_at=room.created_at,
            documents=document_infos,
        )

    async def get_rooms(
        self, owner_id: Optional[int] = None, skip: int = 0, limit: int = 100
    ) -> list[RoomResponse]:
        """사용자별 방 목록 조회"""
        if owner_id is None:
            return []

        rooms = await room_repository.get_rooms_by_owner(owner_id, self.session)

        # 문서 개수 포함하여 응답 생성
        room_responses = []
        for room in rooms[skip : skip + limit]:
            if room.id is not None:
                document_count = await self._get_room_document_count(room.id)
                room_responses.append(
                    RoomResponse(
                        id=room.id,
                        title=room.name,
                        description=room.description,
                        owner_id=room.owner_id,
                        document_count=document_count,
                        created_at=room.created_at,
                    )
                )

        return room_responses

    async def get_all_rooms(
        self, skip: int = 0, limit: int = 100
    ) -> list[RoomResponse]:
        """모든 방 목록 조회 (관리자용)"""
        rooms = await room_repository.get_all_rooms(self.session)

        # 문서 개수 포함하여 응답 생성
        room_responses = []
        for room in rooms[skip : skip + limit]:
            if room.id is not None:
                document_count = await self._get_room_document_count(room.id)
                room_responses.append(
                    RoomResponse(
                        id=room.id,
                        title=room.name,
                        description=room.description,
                        owner_id=room.owner_id,
                        document_count=document_count,
                        created_at=room.created_at,
                    )
                )

        return room_responses

    async def delete_room(
        self, room_id: int, user_id: int, user_role: str = "user"
    ) -> bool:
        """방 삭제 (권한 검증 포함)"""
        room = await room_repository.get_room_by_id(room_id, self.session)
        if not room:
            return False

        # 권한 검증: 방 소유자 또는 관리자만 삭제 가능
        if room.owner_id != user_id and user_role != "admin":
            return False

        return await room_repository.soft_delete_room(room_id, self.session)

    async def _get_room_document_count(self, room_id: int) -> int:
        """방의 문서 개수 조회"""
        from sqlmodel import func, select

        from src.core.query_utils import create_soft_delete_query

        query = create_soft_delete_query(Document, include_deleted_records=False)
        query = query.where(Document.room_id == room_id)
        query = select(func.count()).select_from(query.subquery())

        result = await self.session.exec(query)
        return result.first() or 0
