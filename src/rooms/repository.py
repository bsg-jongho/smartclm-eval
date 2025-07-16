"""
🏠 방(Room) 관리 리포지토리

계약/업무 단위의 방을 관리하는 리포지토리
"""

from typing import List, Optional

from sqlmodel import desc
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.query_utils import (
    create_soft_delete_query,
    create_soft_delete_query_with_conditions,
)
from src.models import Room


class RoomRepository:
    """방 관리 리포지토리"""

    async def create_room(self, room: Room, session: AsyncSession) -> Room:
        """방 생성"""
        session.add(room)
        await session.commit()
        await session.refresh(room)
        return room

    async def get_room_by_id(
        self, room_id: int, session: AsyncSession, include_deleted: bool = False
    ) -> Optional[Room]:
        """ID로 방 조회"""
        query = create_soft_delete_query_with_conditions(
            Room, include_deleted_records=include_deleted, id=room_id
        )
        result = await session.exec(query)
        return result.first()

    async def get_rooms_by_owner(
        self, owner_id: int, session: AsyncSession, include_deleted: bool = False
    ) -> List[Room]:
        """소유자별 방 목록 조회"""
        query = create_soft_delete_query_with_conditions(
            Room, include_deleted_records=include_deleted, owner_id=owner_id
        ).order_by(desc(Room.created_at))
        result = await session.exec(query)
        return list(result.all())

    async def get_all_rooms(
        self, session: AsyncSession, include_deleted: bool = False
    ) -> List[Room]:
        """모든 방 목록 조회"""
        query = create_soft_delete_query(Room, include_deleted_records=include_deleted)
        result = await session.exec(query)
        return list(result.all())

    async def update_room(self, room: Room, session: AsyncSession) -> Room:
        """방 업데이트"""
        session.add(room)
        await session.commit()
        await session.refresh(room)
        return room

    async def soft_delete_room(self, room_id: int, session: AsyncSession) -> bool:
        """방 Soft Delete"""
        room = await self.get_room_by_id(room_id, session)
        if room:
            room.soft_delete()
            await session.commit()
            return True
        return False

    async def restore_room(self, room_id: int, session: AsyncSession) -> bool:
        """삭제된 방 복구"""
        room = await self.get_room_by_id(room_id, session, include_deleted=True)
        if room and room.is_deleted:
            room.restore()
            await session.commit()
            return True
        return False

    async def hard_delete_room(self, room_id: int, session: AsyncSession) -> bool:
        """방 Hard Delete (영구 삭제)"""
        room = await self.get_room_by_id(room_id, session, include_deleted=True)
        if room:
            await session.delete(room)
            await session.commit()
            return True
        return False

    async def get_deleted_rooms(
        self, owner_id: Optional[int] = None, session: AsyncSession = None
    ) -> List[Room]:
        """삭제된 방 목록 조회"""
        base_query = create_soft_delete_query(Room, include_deleted_records=True)
        query = base_query.where(Room.deleted_at != None)

        if owner_id is not None:
            query = query.where(Room.owner_id == owner_id)

        query = query.order_by(desc(Room.deleted_at))
        result = await session.exec(query)
        return list(result.all())


# 싱글톤 인스턴스
room_repository = RoomRepository()
