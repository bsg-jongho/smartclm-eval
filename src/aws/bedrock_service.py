import json
import logging
import time
from datetime import datetime
from typing import Any, Optional

import boto3

logger = logging.getLogger(__name__)


class BedrockService:
    """Amazon Bedrock API 호출을 담당하는 서비스"""

    def __init__(
        self,
        region_name: str = "ap-northeast-2",
        default_model_id: str = "apac.anthropic.claude-3-7-sonnet-20250219-v1:0",
    ):
        """
        Bedrock 서비스 초기화

        Args:
            region_name: AWS 리전
            default_model_id: 기본 모델 ID
        """
        self.bedrock = boto3.client("bedrock-runtime", region_name=region_name)
        self.default_model_id = default_model_id

    def invoke_model(
        self,
        prompt: str,
        model_id: Optional[str] = None,
        max_tokens: int = 4000,
        temperature: float = 0.1,
        **kwargs: Any,
    ) -> dict:
        """
        Bedrock 모델 호출

        Args:
            prompt: 입력 프롬프트
            model_id: 사용할 모델 ID (None이면 기본 모델 사용)
            max_tokens: 최대 토큰 수
            temperature: 온도 설정
            **kwargs: 추가 매개변수 (body에 포함됨)

        Returns:
            dict: {"text": str, "usage": dict, "timing": dict} - 응답 텍스트, 토큰 사용량, 시간 정보
        """
        # 요청 시작 시간 기록
        request_started_at = datetime.now()
        start_time = time.time()

        try:
            # 모델 ID 결정 (지정하지 않으면 기본 모델 사용)
            selected_model_id = model_id or self.default_model_id

            # model_id는 kwargs에서 제거 (body에 포함되면 안 됨)
            filtered_kwargs = {k: v for k, v in kwargs.items() if k != "model_id"}

            body = json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                    **filtered_kwargs,
                }
            )

            logger.info(f"Bedrock API 호출 시작 (모델: {selected_model_id})")
            response = self.bedrock.invoke_model(modelId=selected_model_id, body=body)
            logger.info("Bedrock API 응답 수신")

            # 응답 수신 시간 기록
            response_received_at = datetime.now()
            end_time = time.time()
            processing_time_seconds = end_time - start_time
            processing_time_ms = int(processing_time_seconds * 1000)

            result = json.loads(response["body"].read())
            response_text = result["content"][0]["text"]

            # 실제 토큰 사용량 추출
            usage = result.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)

            logger.info(f"API 응답 텍스트 길이: {len(response_text)}")
            logger.info(
                f"토큰 사용량 - 입력: {input_tokens}, 출력: {output_tokens}, 총합: {total_tokens}"
            )
            logger.info(f"처리 시간: {processing_time_ms}ms")

            return {
                "text": response_text,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                },
                "timing": {
                    "request_started_at": request_started_at,
                    "response_received_at": response_received_at,
                    "processing_time_ms": processing_time_ms,
                    "processing_time_seconds": processing_time_seconds,
                },
            }

        except Exception as e:
            # 오류 발생 시에도 시간 정보 포함
            response_received_at = datetime.now()
            end_time = time.time()
            processing_time_seconds = end_time - start_time
            processing_time_ms = int(processing_time_seconds * 1000)

            logger.error(f"Bedrock API 호출 중 오류: {str(e)}")
            logger.error(f"오류 발생까지 소요 시간: {processing_time_ms}ms")

            # 오류 시에도 timing 정보를 포함하여 반환
            raise Exception(
                f"Bedrock API 호출 실패 (소요시간: {processing_time_ms}ms): {str(e)}"
            )

    def test_connection(self, model_id: Optional[str] = None) -> bool:
        """
        Bedrock 연결 테스트

        Args:
            model_id: 테스트할 모델 ID (None이면 기본 모델 사용)
        """
        try:
            response = self.invoke_model("Hello, world!", model_id=model_id)
            return len(response["text"]) > 0
        except Exception as e:
            logger.error(f"연결 테스트 실패: {str(e)}")
            return False

    def set_default_model(self, model_id: str) -> None:
        """
        기본 모델 변경

        Args:
            model_id: 새로운 기본 모델 ID
        """
        self.default_model_id = model_id
        logger.info(f"기본 모델이 {model_id}로 변경되었습니다")

    async def stream_model(
        self,
        prompt: str,
        model_id: Optional[str] = None,
        max_tokens: int = 4000,
        temperature: float = 0.1,
        **kwargs: Any,
    ):
        """
        Bedrock 모델 스트리밍 호출

        Args:
            prompt: 입력 프롬프트
            model_id: 사용할 모델 ID (None이면 기본 모델 사용)
            max_tokens: 최대 토큰 수
            temperature: 온도 설정
            **kwargs: 추가 매개변수

        Yields:
            dict: {"text": str, "is_complete": bool, "usage": dict} - 스트리밍 응답
        """
        try:
            # 모델 ID 결정
            selected_model_id = model_id or self.default_model_id

            # model_id는 kwargs에서 제거
            filtered_kwargs = {k: v for k, v in kwargs.items() if k != "model_id"}

            body = json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                    **filtered_kwargs,
                }
            )

            logger.info(f"Bedrock 스트리밍 API 호출 시작 (모델: {selected_model_id})")

            # 스트리밍 호출
            response = self.bedrock.invoke_model_with_response_stream(
                modelId=selected_model_id, body=body
            )

            full_text = ""
            total_input_tokens = 0
            total_output_tokens = 0

            for event in response["body"]:
                chunk = json.loads(event["chunk"]["bytes"])

                if chunk["type"] == "content_block_delta":
                    text_chunk = chunk["delta"]["text"]
                    full_text += text_chunk

                    yield {
                        "text": text_chunk,
                        "is_complete": False,
                        "usage": None,
                    }

                elif chunk["type"] == "message_delta":
                    # 메시지 완료
                    if "usage" in chunk:
                        total_input_tokens = chunk["usage"]["input_tokens"]
                        total_output_tokens = chunk["usage"]["output_tokens"]

                    yield {
                        "text": "",
                        "is_complete": True,
                        "usage": {
                            "input_tokens": total_input_tokens,
                            "output_tokens": total_output_tokens,
                            "total_tokens": total_input_tokens + total_output_tokens,
                        },
                    }

        except Exception as e:
            logger.error(f"Bedrock 스트리밍 API 호출 중 오류: {str(e)}")
            yield {
                "text": f"오류가 발생했습니다: {str(e)}",
                "is_complete": True,
                "usage": None,
            }
