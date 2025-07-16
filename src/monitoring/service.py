"""
📊 모니터링 서비스

토큰 사용량, 성능 지표, 사용량 분석 등을 담당하는 서비스
"""

import logging
from datetime import datetime

from fastapi import HTTPException
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.documents.schema import (
    TokenUsageDetail,
    TokenUsageListResponse,
    TokenUsageSummary,
)
from src.models import TokenUsage

logger = logging.getLogger(__name__)


class MonitoringService:
    """모니터링 및 분석 서비스"""

    async def get_user_token_usage(
        self, user_id: int, session: AsyncSession, limit: int = 50, offset: int = 0
    ) -> TokenUsageListResponse:
        """사용자별 토큰 사용량 조회"""
        try:
            # 토큰 사용량 목록 조회
            stmt = (
                select(TokenUsage)
                .where(TokenUsage.user_id == user_id)
                .order_by(TokenUsage.created_at)
                .limit(limit)
                .offset(offset)
            )

            result = await session.exec(stmt)
            token_usages = result.all()

            # 요약 정보 조회
            summary_stmt = select(
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.total_cost).label("total_cost"),
                func.avg(TokenUsage.processing_time_ms).label("avg_processing_time_ms"),
                func.count(TokenUsage.id).label("operation_count"),
            ).where(TokenUsage.user_id == user_id)

            summary_result = await session.exec(summary_stmt)
            summary_data = summary_result.first()

            # TokenUsageDetail 객체로 변환
            token_usage_details = []
            for usage in token_usages:
                detail = TokenUsageDetail(
                    id=usage.id or 0,
                    operation_type=usage.operation_type,
                    model_name=usage.model_name,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    total_tokens=usage.total_tokens,
                    total_cost=usage.total_cost,
                    processing_time_ms=usage.processing_time_ms,
                    created_at=usage.created_at or datetime.now(),
                )
                token_usage_details.append(detail)

            # 요약 정보 구성
            summary = TokenUsageSummary(
                total_tokens=summary_data.total_tokens or 0,
                total_cost=summary_data.total_cost or 0.0,
                avg_processing_time_ms=summary_data.avg_processing_time_ms or 0.0,
                operation_count=summary_data.operation_count or 0,
            )

            return TokenUsageListResponse(
                token_usages=token_usage_details,
                summary=summary,
                total_count=len(token_usage_details),
            )

        except Exception as e:
            logger.error(f"❌ 토큰 사용량 조회 실패: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"토큰 사용량 조회에 실패했습니다: {str(e)}"
            )

    async def get_room_token_usage(
        self, room_id: int, session: AsyncSession, limit: int = 50, offset: int = 0
    ) -> TokenUsageListResponse:
        """방별 토큰 사용량 조회"""
        try:
            # 토큰 사용량 목록 조회
            stmt = (
                select(TokenUsage)
                .where(TokenUsage.room_id == room_id)
                .order_by(TokenUsage.created_at)
                .limit(limit)
                .offset(offset)
            )

            result = await session.exec(stmt)
            token_usages = result.all()

            # 요약 정보 조회
            summary_stmt = select(
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.total_cost).label("total_cost"),
                func.avg(TokenUsage.processing_time_ms).label("avg_processing_time_ms"),
                func.count(TokenUsage.id).label("operation_count"),
            ).where(TokenUsage.room_id == room_id)

            summary_result = await session.exec(summary_stmt)
            summary_data = summary_result.first()

            # TokenUsageDetail 객체로 변환
            token_usage_details = []
            for usage in token_usages:
                detail = TokenUsageDetail(
                    id=usage.id or 0,
                    operation_type=usage.operation_type,
                    model_name=usage.model_name,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    total_tokens=usage.total_tokens,
                    total_cost=usage.total_cost,
                    processing_time_ms=usage.processing_time_ms,
                    created_at=usage.created_at or datetime.now(),
                )
                token_usage_details.append(detail)

            # 요약 정보 구성
            summary = TokenUsageSummary(
                total_tokens=summary_data.total_tokens or 0,
                total_cost=summary_data.total_cost or 0.0,
                avg_processing_time_ms=summary_data.avg_processing_time_ms or 0.0,
                operation_count=summary_data.operation_count or 0,
            )

            return TokenUsageListResponse(
                token_usages=token_usage_details,
                summary=summary,
                total_count=len(token_usage_details),
            )

        except Exception as e:
            logger.error(f"❌ 방별 토큰 사용량 조회 실패: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"방별 토큰 사용량 조회에 실패했습니다: {str(e)}",
            )

    async def get_system_token_usage(
        self, session: AsyncSession, limit: int = 50, offset: int = 0
    ) -> TokenUsageListResponse:
        """전체 시스템 토큰 사용량 조회 (어드민용)"""
        try:
            # 토큰 사용량 목록 조회
            stmt = (
                select(TokenUsage)
                .order_by(TokenUsage.created_at)
                .limit(limit)
                .offset(offset)
            )

            result = await session.exec(stmt)
            token_usages = result.all()

            # 요약 정보 조회
            summary_stmt = select(
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.total_cost).label("total_cost"),
                func.avg(TokenUsage.processing_time_ms).label("avg_processing_time_ms"),
                func.count(TokenUsage.id).label("operation_count"),
            )

            summary_result = await session.exec(summary_stmt)
            summary_data = summary_result.first()

            # TokenUsageDetail 객체로 변환
            token_usage_details = []
            for usage in token_usages:
                detail = TokenUsageDetail(
                    id=usage.id or 0,
                    operation_type=usage.operation_type,
                    model_name=usage.model_name,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    total_tokens=usage.total_tokens,
                    total_cost=usage.total_cost,
                    processing_time_ms=usage.processing_time_ms,
                    created_at=usage.created_at or datetime.now(),
                )
                token_usage_details.append(detail)

            # 요약 정보 구성
            summary = TokenUsageSummary(
                total_tokens=summary_data.total_tokens or 0,
                total_cost=summary_data.total_cost or 0.0,
                avg_processing_time_ms=summary_data.avg_processing_time_ms or 0.0,
                operation_count=summary_data.operation_count or 0,
            )

            return TokenUsageListResponse(
                token_usages=token_usage_details,
                summary=summary,
                total_count=len(token_usage_details),
            )

        except Exception as e:
            logger.error(f"❌ 시스템 토큰 사용량 조회 실패: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"시스템 토큰 사용량 조회에 실패했습니다: {str(e)}",
            )


# 싱글톤 인스턴스
monitoring_service = MonitoringService()
