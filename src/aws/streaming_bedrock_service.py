import json
import logging
from typing import Any, AsyncGenerator, Dict

import boto3

logger = logging.getLogger(__name__)


class StreamingBedrockService:
    """Amazon Bedrock 스트리밍 API 서비스 (boto3 직접 사용)"""

    def __init__(
        self,
        region_name: str = "ap-northeast-2",
        default_model_id: str = "apac.anthropic.claude-3-7-sonnet-20250219-v1:0",
    ):
        """
        스트리밍 Bedrock 서비스 초기화

        Args:
            region_name: AWS 리전 (서울 리전 고정)
            default_model_id: 기본 모델 ID
        """
        self.bedrock = boto3.client("bedrock-runtime", region_name=region_name)
        self.region_name = region_name
        self.default_model_id = default_model_id

        logger.info(f"StreamingBedrockService 초기화 완료 (모델: {default_model_id})")

    async def stream_chat_response(
        self,
        prompt: str,
        max_tokens: int = 4000,
        temperature: float = 0.1,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        스트리밍으로 채팅 응답 생성 (boto3 직접 사용)

        Args:
            prompt: 입력 프롬프트
            max_tokens: 최대 토큰 수
            temperature: 온도 설정
            **kwargs: 추가 매개변수

        Yields:
            str: 실시간 토큰 스트림
        """
        try:
            logger.info("boto3 스트리밍 채팅 응답 생성 시작")

            # 요청 본문 구성 (기존 bedrock_service와 동일)
            body = json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                    **kwargs,
                }
            )

            # 스트리밍 호출
            response = self.bedrock.invoke_model_with_response_stream(
                modelId=self.default_model_id, body=body
            )

            # 스트림 처리
            stream = response.get("body")
            if stream:
                for event in stream:
                    chunk = event.get("chunk")
                    if chunk:
                        chunk_obj = json.loads(chunk.get("bytes").decode())

                        # Claude 응답에서 텍스트 추출
                        if chunk_obj.get("type") == "content_block_delta":
                            delta = chunk_obj.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    yield text

                        # 스트림 완료 확인
                        elif chunk_obj.get("type") == "message_stop":
                            logger.info("스트리밍 완료")
                            break

            logger.info("boto3 스트리밍 채팅 응답 생성 완료")

        except Exception as e:
            logger.error(f"boto3 스트리밍 채팅 중 오류: {str(e)}")
            yield f"❌ 오류가 발생했습니다: {str(e)}"

    async def test_streaming_connection(self) -> bool:
        """스트리밍 연결 테스트"""
        try:
            logger.info("boto3 스트리밍 연결 테스트 시작")

            response_tokens = []
            async for token in self.stream_chat_response(
                "안녕하세요! 연결 테스트입니다."
            ):
                response_tokens.append(token)
                if len(response_tokens) > 5:  # 몇 개 토큰만 받아보고 중단
                    break

            success = len(response_tokens) > 0
            logger.info(f"boto3 스트리밍 연결 테스트 {'성공' if success else '실패'}")
            return success

        except Exception as e:
            logger.error(f"boto3 스트리밍 연결 테스트 실패: {str(e)}")
            return False

    def get_model_info(self) -> Dict[str, Any]:
        """현재 모델 정보 반환"""
        return {
            "model_id": self.default_model_id,
            "region": self.region_name,
            "streaming": True,
            "framework": "boto3-direct",
            "max_tokens": 4000,
            "temperature": 0.1,
        }


# 싱글톤 인스턴스
streaming_bedrock_service = StreamingBedrockService()
