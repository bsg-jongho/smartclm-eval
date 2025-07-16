"""
💰 토큰 사용량 및 비용 추적 서비스

모든 LLM 호출의 토큰 사용량과 비용을 추적하고 데이터베이스에 저장합니다.
"""

import logging
import time
from datetime import datetime
from typing import Dict, Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from src.models import TokenUsage

logger = logging.getLogger(__name__)


class TokenTracker:
    """토큰 사용량 및 비용 추적 서비스"""

    # Claude 3 Sonnet 가격 (2024년 기준, USD per 1K tokens)
    CLAUDE_3_SONNET_INPUT_COST_PER_1K = 0.003
    CLAUDE_3_SONNET_OUTPUT_COST_PER_1K = 0.015

    # Claude 3 Haiku 가격 (2024년 기준, USD per 1K tokens)
    CLAUDE_3_HAIKU_INPUT_COST_PER_1K = 0.00025
    CLAUDE_3_HAIKU_OUTPUT_COST_PER_1K = 0.00125

    # Titan Embedding 가격 (2024년 기준, USD per 1K tokens)
    TITAN_EMBEDDING_COST_PER_1K = 0.0001

    @classmethod
    def calculate_cost(
        cls, model_name: str, input_tokens: int, output_tokens: int
    ) -> Dict[str, float]:
        """토큰 사용량에 따른 비용 계산"""

        # 모델별 가격 결정
        if "claude-3-sonnet" in model_name.lower():
            input_cost_per_1k = cls.CLAUDE_3_SONNET_INPUT_COST_PER_1K
            output_cost_per_1k = cls.CLAUDE_3_SONNET_OUTPUT_COST_PER_1K
        elif "claude-3-haiku" in model_name.lower():
            input_cost_per_1k = cls.CLAUDE_3_HAIKU_INPUT_COST_PER_1K
            output_cost_per_1k = cls.CLAUDE_3_HAIKU_OUTPUT_COST_PER_1K
        elif "titan-embed" in model_name.lower():
            # 임베딩은 입력 토큰만 있음
            input_cost_per_1k = cls.TITAN_EMBEDDING_COST_PER_1K
            output_cost_per_1k = 0.0
        else:
            # 기본값 (Claude 3 Sonnet)
            input_cost_per_1k = cls.CLAUDE_3_SONNET_INPUT_COST_PER_1K
            output_cost_per_1k = cls.CLAUDE_3_SONNET_OUTPUT_COST_PER_1K

        # 비용 계산
        input_cost = (input_tokens / 1000) * input_cost_per_1k
        output_cost = (output_tokens / 1000) * output_cost_per_1k
        total_cost = input_cost + output_cost

        return {
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(total_cost, 6),
        }

    @classmethod
    async def record_token_usage(
        cls,
        session: AsyncSession,
        user_id: int,
        operation_type: str,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        room_id: Optional[int] = None,
        document_id: Optional[int] = None,
        usage_metadata: Optional[Dict] = None,
        status: str = "completed",
        error_message: Optional[str] = None,
        request_started_at: Optional[datetime] = None,
        response_received_at: Optional[datetime] = None,
        processing_time_ms: Optional[int] = None,
    ) -> TokenUsage:
        """토큰 사용량을 데이터베이스에 기록"""

        try:
            # 비용 계산
            cost_info = cls.calculate_cost(model_name, input_tokens, output_tokens)

            # TokenUsage 모델 생성
            token_usage = TokenUsage(
                user_id=user_id,
                room_id=room_id,
                document_id=document_id,
                operation_type=operation_type,
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                input_cost=cost_info["input_cost"],
                output_cost=cost_info["output_cost"],
                total_cost=cost_info["total_cost"],
                usage_metadata=usage_metadata or {},
                status=status,
                error_message=error_message,
                request_started_at=request_started_at,
                response_received_at=response_received_at,
                processing_time_ms=processing_time_ms,
            )

            # 데이터베이스에 저장
            session.add(token_usage)
            await session.commit()
            await session.refresh(token_usage)

            # 처리 시간 로깅
            time_info = ""
            if processing_time_ms:
                time_info = f", 처리시간: {processing_time_ms}ms"

            logger.info(
                f"💰 토큰 사용량 기록 완료: {operation_type} - "
                f"입력: {input_tokens:,}, 출력: {output_tokens:,}, "
                f"총합: {total_tokens:,}, 비용: ${token_usage.total_cost:.6f}{time_info}"
            )

            return token_usage

        except Exception as e:
            logger.error(f"❌ 토큰 사용량 기록 실패: {str(e)}")
            await session.rollback()
            raise

    @classmethod
    async def record_bedrock_usage(
        cls,
        session: AsyncSession,
        user_id: int,
        operation_type: str,
        model_name: str,
        usage: Dict,
        room_id: Optional[int] = None,
        document_id: Optional[int] = None,
        usage_metadata: Optional[Dict] = None,
        status: str = "completed",
        error_message: Optional[str] = None,
        request_started_at: Optional[datetime] = None,
        response_received_at: Optional[datetime] = None,
        processing_time_ms: Optional[int] = None,
    ) -> TokenUsage:
        """Bedrock API 응답의 usage 정보를 사용하여 토큰 사용량 기록"""

        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        return await cls.record_token_usage(
            session=session,
            user_id=user_id,
            operation_type=operation_type,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            room_id=room_id,
            document_id=document_id,
            usage_metadata=usage_metadata,
            status=status,
            error_message=error_message,
            request_started_at=request_started_at,
            response_received_at=response_received_at,
            processing_time_ms=processing_time_ms,
        )

    @classmethod
    def start_timing(cls) -> float:
        """LLM 호출 시작 시간 기록"""
        return time.time()

    @classmethod
    def end_timing(cls, start_time: float) -> Dict[str, float]:
        """LLM 호출 종료 시간 기록 및 처리 시간 계산"""
        end_time = time.time()
        processing_time_seconds = end_time - start_time
        processing_time_ms = int(processing_time_seconds * 1000)

        return {
            "start_time": start_time,
            "end_time": end_time,
            "processing_time_seconds": processing_time_seconds,
            "processing_time_ms": processing_time_ms,
        }
