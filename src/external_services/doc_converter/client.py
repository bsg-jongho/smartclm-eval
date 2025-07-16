import logging
import os
from typing import Any, Dict

import httpx
from fastapi import UploadFile

logger = logging.getLogger(__name__)


class DocConverterClient:
    def __init__(self):
        self.base_url = os.getenv("DOC_CONVERTER_URL", "http://localhost:8001")

    async def convert_to_pdf(self, file: UploadFile) -> bytes:
        """
        doc-converter 서비스에 파일을 전송하여 PDF로 변환합니다.

        Args:
            file: 변환할 파일 (UploadFile)

        Returns:
            bytes: 변환된 PDF 파일의 바이트 데이터

        Raises:
            Exception: 변환 실패 시
        """
        async with httpx.AsyncClient() as client:
            # 파일을 다시 읽기 위해 seek(0)
            await file.seek(0)

            files = {"file": (file.filename, file.file, file.content_type)}

            response = await client.post(
                f"{self.base_url}/convert",
                files=files,
                timeout=600.0,  # 10분 타임아웃
            )

            if response.status_code == 200:
                return response.content
            else:
                error_msg = response.text
                raise Exception(
                    f"PDF 변환 실패 (status: {response.status_code}): {error_msg}"
                )

    async def health_check(self) -> Dict[str, Any]:
        """서비스 헬스체크"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.json()
        except Exception as e:
            logger.error(f"Doc Converter 헬스체크 실패: {str(e)}")
            return {"status": "error", "error": str(e)}


# 싱글톤 인스턴스
doc_converter_client = DocConverterClient()
