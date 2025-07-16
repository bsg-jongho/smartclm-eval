"""
🔄 Doc Converter 라우터

문서 변환 서비스(doc-converter)를 호출하는 라우터
"""

import logging
import os
import shutil
import urllib.parse

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse, Response

from .client import doc_converter_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/doc-converter", tags=["🔄 문서 변환"])


@router.post("/convert")
async def convert_to_pdf(file: UploadFile = File(...)):
    """
    문서 파일을 PDF로 변환합니다.

    지원 형식: DOCX, PPTX, XLSX, TXT 등
    """
    # 파일 크기 제한 (50MB)
    MAX_FILE_SIZE = 50 * 1024 * 1024

    if file.size and file.size > MAX_FILE_SIZE:
        return JSONResponse(
            status_code=413,
            content={
                "error": f"파일 크기가 제한을 초과했습니다. 최대 {MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
            },
        )

    input_dir = "/tmp"
    os.makedirs(input_dir, exist_ok=True)
    filename = file.filename or "uploaded_file"
    input_path = os.path.join(input_dir, filename)

    try:
        logger.info(f"🔄 문서 변환 시작: {filename}")

        # 파일 저장
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # PDF 변환 시도 (doc-converter 서비스 호출)
        pdf_content = await doc_converter_client.convert_to_pdf(file)

        # 한글 파일명을 안전하게 처리하기 위해 URL 인코딩 사용
        safe_filename = urllib.parse.quote(
            f"{os.path.splitext(filename)[0]}.pdf", safe=""
        )

        logger.info(f"✅ 문서 변환 완료: {filename}")

        # 변환된 PDF를 바로 다운로드로 응답
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}"
            },
        )

    except Exception as e:
        logger.error(f"❌ 문서 변환 중 오류 발생: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

    finally:
        # 업로드된 임시 파일 삭제
        if os.path.exists(input_path):
            os.remove(input_path)


@router.get("/health")
async def health_check():
    """Doc Converter 서비스 헬스체크"""
    try:
        result = await doc_converter_client.health_check()
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"❌ Doc Converter 헬스체크 실패: {e}")
        return JSONResponse(
            status_code=500, content={"status": "error", "error": str(e)}
        )
