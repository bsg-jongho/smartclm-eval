from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.auth.dependency import require_role
from src.core.database import get_session
from src.core.schema import ListApiResponse
from src.models import User

router = APIRouter(
    prefix="/users",
    tags=["👤 사용자"],
)


@router.get("", response_model=ListApiResponse[List[User]])
async def get_all_users(
    current_user: Dict[str, Any] = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_session),
) -> ListApiResponse[List[User]]:
    """
    🧑‍💼 모든 사용자 목록 조회 (관리자 전용)
    """
    users = (await db.exec(select(User))).all()

    return ListApiResponse(
        data=list(users),
        total=len(users),
        message="사용자 목록을 성공적으로 조회했습니다",
    )
