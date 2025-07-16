from datetime import datetime, timezone
from typing import Optional

from inflection import pluralize
from sqlalchemy.orm import declared_attr
from sqlmodel import BigInteger, DateTime, Field, SQLModel, func

from src.core.utill import camel_to_snake_case, to_camel


class Base(SQLModel):
    """
    모든 모델의 베이스 클래스

    공통 필드:
    - id: 자동 증가하는 기본 키
    - created_at: 생성 시간 (자동 설정)
    - updated_at: 수정 시간 (자동 업데이트)
    - deleted_at: 삭제 시간 (Soft Delete 지원)
    """

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_type=BigInteger,
        sa_column_kwargs={"autoincrement": True},
        description="기본 키",
    )
    created_at: datetime | None = Field(
        sa_type=DateTime(timezone=True),  # type: ignore
        sa_column_kwargs={
            "server_default": func.now(),
            "index": True,  # 인덱스 추가
        },
        default_factory=lambda: datetime.now(timezone.utc),
        description="생성 시간",
    )
    updated_at: datetime | None = Field(
        sa_type=DateTime(timezone=True),  # type: ignore
        sa_column_kwargs={
            "server_default": func.now(),
            "index": True,  # 인덱스 추가
        },
        default_factory=lambda: datetime.now(timezone.utc),
        description="수정 시간",
    )
    deleted_at: Optional[datetime] = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
        sa_column_kwargs={"index": True},  # 인덱스 추가
        description="삭제 시간 (Soft Delete)",
    )

    class Config:
        populate_by_name = True
        alias_generator = to_camel

    @declared_attr.directive
    def __tablename__(cls) -> str:
        """테이블명을 자동으로 생성 (복수형, snake_case)"""
        return pluralize(camel_to_snake_case(cls.__name__))

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    def soft_delete(self) -> None:
        """Soft Delete - deleted_at 필드만 설정"""
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self) -> None:
        """Soft Delete 복구 - deleted_at 필드를 None으로 설정"""
        self.deleted_at = None

    @property
    def is_deleted(self) -> bool:
        """삭제 여부 확인"""
        return self.deleted_at is not None
