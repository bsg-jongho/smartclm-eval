from collections.abc import Sized
from typing import Generic, Optional, TypeVar

from sqlmodel import SQLModel

from src.core.utill import to_camel


class SchemaBase(SQLModel):
    class Config:
        populate_by_name = True
        alias_generator = to_camel
        extra = "forbid"


T = TypeVar("T")


class ApiResponse(SchemaBase, Generic[T]):
    """기본 API 응답 스키마"""

    data: T | None = None
    message: str | None = None


class PaginatedApiResponse(SchemaBase, Generic[T]):
    """페이지네이션이 포함된 API 응답 스키마"""

    data: T | None = None
    total: Optional[int] = None
    page: Optional[int] = None
    page_size: Optional[int] = None
    total_pages: Optional[int] = None
    message: Optional[str] = None


class ListApiResponse(SchemaBase, Generic[T]):
    """리스트 데이터용 API 응답 스키마"""

    data: T | None = None
    total: Optional[int] = None
    message: Optional[str] = None


# 헬퍼 함수들
def create_success_response(data: T, message: str = "성공") -> ApiResponse[T]:
    """성공 응답 생성"""
    return ApiResponse(data=data, message=message)


def create_list_response(
    data: T, total: int | None = None, message: str = "성공"
) -> ListApiResponse[T]:
    """리스트 응답 생성"""
    if total is None and isinstance(data, Sized):
        total = len(data)
    return ListApiResponse(data=data, total=total, message=message)


def create_paginated_response(
    data: T, total: int, page: int, page_size: int, message: str = "성공"
) -> PaginatedApiResponse[T]:
    """페이지네이션 응답 생성"""
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return PaginatedApiResponse(
        data=data,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        message=message,
    )
