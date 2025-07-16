"""
🏠 방(Room) 관리 라우터

계약/업무 단위의 방을 관리하는 라우터
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from src.auth.dependency import get_current_user, require_role
from src.core.database import get_session
from src.core.schema import (
    ApiResponse,
    ListApiResponse,
    create_list_response,
    create_success_response,
)
from src.core.utill import dict_keys_to_camel

from .schema import RoomCreate, RoomDetailResponse, RoomResponse
from .service import RoomService

router = APIRouter(prefix="/rooms", tags=["🏠 계약 방 관리"])


@router.post("", response_model=ApiResponse[RoomResponse])
async def create_room(
    room_create: RoomCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    🏠 계약 방 생성

    새로운 계약/업무 단위의 방을 생성합니다.
    방은 "Untitled" 제목으로 생성되며, 나중에 계약서를 업로드할 때 제목과 설명을 업데이트할 수 있습니다.
    """
    try:
        service = RoomService(session)
        room = await service.create_room(
            owner_id=user["user_id"], room_create=room_create
        )

        return create_success_response(
            data=room,
            message=f"방 '{room.title}'이 성공적으로 생성되었습니다",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=ListApiResponse[RoomResponse])
async def list_rooms(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    skip: int = 0,
    limit: int = 100,
):
    """
    🏠 내 방 목록 조회

    현재 사용자가 소유한 방 목록을 조회합니다.
    각 방의 문서 개수도 함께 표시됩니다.
    """
    try:
        print(f"user: {user}")
        service = RoomService(session)

        # 관리자인 경우 모든 방 조회, 일반 사용자는 자신의 방만 조회
        if user["role"] == "admin":
            result = await service.get_all_rooms(skip=skip, limit=limit)
        else:
            result = await service.get_rooms(
                owner_id=user["user_id"], skip=skip, limit=limit
            )

        return create_list_response(
            data=result,
            total=len(result),
            message=f"총 {len(result)}개의 방을 찾았습니다",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/user/{user_id}", response_model=ListApiResponse[RoomResponse])
async def list_user_rooms_admin(
    user_id: int,
    user: dict = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
    skip: int = 0,
    limit: int = 100,
):
    """
    🏠 특정 사용자의 방 목록 조회 (관리자 전용)

    관리자가 특정 사용자가 소유한 방 목록을 조회합니다.
    """
    try:
        service = RoomService(session)
        result = await service.get_rooms(owner_id=user_id, skip=skip, limit=limit)

        return create_list_response(
            data=result,
            total=len(result),
            message=f"사용자 ID {user_id}의 방 {len(result)}개를 찾았습니다",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{room_id}", response_model=ApiResponse[RoomDetailResponse])
async def get_room(
    room_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    🏠 방 상세 조회

    특정 방의 상세 정보를 조회합니다.
    방 소유자 또는 관리자만 조회 가능합니다.
    """
    try:
        service = RoomService(session)
        room = await service.get_room(
            room_id, user_id=user["user_id"], user_role=user["role"]
        )

        if not room:
            raise HTTPException(status_code=404, detail="방을 찾을 수 없습니다")

        # 각 문서의 document_metadata를 camelCase로 변환
        for doc in room.documents:
            if hasattr(doc, "document_metadata") and isinstance(
                doc.document_metadata, dict
            ):
                converted = dict_keys_to_camel(doc.document_metadata)
                if isinstance(converted, dict):
                    doc.document_metadata = converted

        return create_success_response(
            data=room,
            message=f"방 '{room.title}' 정보를 조회했습니다",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    🏠 방 삭제

    방을 삭제합니다. 방 내의 모든 문서도 함께 삭제됩니다.
    방 소유자 또는 관리자만 삭제 가능합니다.
    """
    try:
        service = RoomService(session)
        success = await service.delete_room(
            room_id, user_id=user["user_id"], user_role=user["role"]
        )

        if not success:
            raise HTTPException(status_code=404, detail="방을 찾을 수 없습니다")

        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
