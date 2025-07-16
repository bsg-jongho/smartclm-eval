"""
🔍 쿼리 유틸리티

Soft Delete, 필터링, 정렬 등을 위한 쿼리 헬퍼 함수들
"""

from typing import Type, TypeVar

from sqlmodel import SQLModel, select

T = TypeVar("T", bound=SQLModel)


def filter_not_deleted(model_class: Type[T]):
    """삭제되지 않은 레코드만 필터링하는 조건"""
    return model_class.deleted_at.is_(None)


def filter_deleted_only(model_class: Type[T]):
    """삭제된 레코드만 필터링하는 조건"""
    return model_class.deleted_at.is_not(None)


def include_deleted(model_class: Type[T]):
    """삭제된 레코드도 포함하는 조건 (필터링 없음)"""
    return True


def create_soft_delete_query(
    model_class: Type[T], include_deleted_records: bool = False
):
    """
    Soft Delete를 고려한 기본 쿼리 생성

    Args:
        model_class: 모델 클래스
        include_deleted_records: 삭제된 레코드 포함 여부

    Returns:
        SQLModel select 쿼리
    """
    stmt = select(model_class)

    if not include_deleted_records:
        stmt = stmt.where(model_class.deleted_at.is_(None))

    return stmt


def create_soft_delete_query_with_conditions(
    model_class: Type[T], include_deleted_records: bool = False, **conditions
):
    """
    조건과 Soft Delete를 고려한 쿼리 생성

    Args:
        model_class: 모델 클래스
        include_deleted_records: 삭제된 레코드 포함 여부
        **conditions: 추가 필터링 조건들

    Returns:
        SQLModel select 쿼리
    """
    stmt = select(model_class)

    # Soft Delete 필터링
    if not include_deleted_records:
        stmt = stmt.where(model_class.deleted_at.is_(None))

    # 추가 조건들 적용
    for field_name, value in conditions.items():
        if hasattr(model_class, field_name):
            field = getattr(model_class, field_name)
            stmt = stmt.where(field == value)

    return stmt
