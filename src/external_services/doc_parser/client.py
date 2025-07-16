import logging
import os
from typing import Any, Dict

import httpx
from fastapi import UploadFile

logger = logging.getLogger(__name__)


class DocParserClient:
    def __init__(self):
        self.base_url = os.getenv("DOC_PARSER_URL", "http://localhost:8002")
        self.timeout = 600.0  # PDF 처리는 시간이 오래 걸릴 수 있음

    async def analyze_pdf(
        self, file: UploadFile, smart_pipeline: bool = True
    ) -> Dict[str, Any]:
        """
        PDF 처리 요청

        Args:
            file: 업로드된 PDF 파일
            smart_pipeline: 스마트 파이프라인 사용 여부

        Returns:
            처리 결과 딕셔너리
        """
        try:
            logger.info(f"📄 Doc Parser 서비스 호출: {file.filename}")

            # 파일을 다시 읽을 수 있도록 seek(0)
            await file.seek(0)

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                files = {"file": (file.filename, file.file, file.content_type)}
                data = {"smart_pipeline": smart_pipeline}

                response = await client.post(
                    f"{self.base_url}/analyze", files=files, data=data
                )

                if response.status_code == 200:
                    result = response.json()
                    logger.info(
                        f"✅ PDF 처리 완료: {result.get('page_count', '?')}페이지"
                    )
                    return result
                else:
                    error_msg = f"Doc Parser 서비스 오류 (HTTP {response.status_code})"
                    logger.error(error_msg)
                    raise Exception(f"{error_msg}: {response.text}")

        except httpx.TimeoutException:
            error_msg = f"Doc Parser 서비스 타임아웃 ({self.timeout}초)"
            logger.error(error_msg)
            raise Exception(error_msg)

        except Exception as e:
            logger.error(f"❌ Doc Parser 클라이언트 오류: {str(e)}")
            raise

    async def health_check(self) -> Dict[str, Any]:
        """서비스 헬스체크"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.json()
        except Exception as e:
            logger.error(f"Doc Parser 헬스체크 실패: {str(e)}")
            return {"status": "error", "error": str(e)}


# 싱글톤 인스턴스
doc_parser_client = DocParserClient()
