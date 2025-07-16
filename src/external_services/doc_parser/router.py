"""
📄 Doc Parser 라우터

PDF 분석 서비스(doc-parser)를 호출하는 라우터
"""

import logging

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import JSONResponse

from .client import doc_parser_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/doc-parser", tags=["📄 PDF 분석"])


@router.post("/analyze")
async def analyze_pdf(
    file: UploadFile = File(...),
    smart_pipeline: bool = Query(
        True,
        description="스마트 파이프라인 사용 여부 (True: 적응적 처리, False: 전체 기능 사용)",
    ),
):
    """
    Docling을 사용하여 PDF 파일을 분석합니다.

    ## 🚀 스마트 파이프라인 (smart_pipeline=true, 기본값)
    - 문서 특성을 먼저 분석하여 최적의 처리 방식 선택
    - 처리 속도 2-3배 향상, 메모리 사용량 절약
    - 디지털 문서: OCR 생략, 테이블 없으면 구조 인식 생략
    - 스캔 문서: OCR 활성화, 이미지 처리 강화

    ## ⚙️ 레거시 파이프라인 (smart_pipeline=false)
    - 모든 기능을 항상 활성화 (기존 방식)
    - OCR, 테이블 구조 인식, 이미지 처리 모두 수행
    - 안정성 우선, 처리 시간은 더 오래 걸림

    ✅ 자동으로 처리되는 항목:
    - 텍스트 추출 (디지털/스캔 문서 자동 인식)
    - 테이블 구조 정확 인식 및 추출
    - 이미지 메타데이터 및 실제 이미지 추출
    - 한국어/영어 OCR 지원
    - 구조화된 문서는 자동으로 아웃라인 생성
    """
    try:
        logger.info(f"📄 PDF 분석 시작: {file.filename}")

        # 🚀 Document Processor 마이크로서비스 호출
        result = await doc_parser_client.analyze_pdf(
            file, smart_pipeline=smart_pipeline
        )

        logger.info(f"✅ PDF 분석 완료: {file.filename}")
        return JSONResponse(content=result)

    except ValueError as e:
        logger.error(f"❌ 파일 검증 오류: {str(e)}")
        return JSONResponse(status_code=400, content={"error": str(e)})

    except Exception as e:
        logger.error(f"❌ PDF 분석 중 오류 발생: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"PDF 분석 중 오류가 발생했습니다: {str(e)}"},
        )


@router.get("/health")
async def health_check():
    """Doc Parser 서비스 헬스체크"""
    try:
        result = await doc_parser_client.health_check()
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"❌ Doc Parser 헬스체크 실패: {e}")
        return JSONResponse(
            status_code=500, content={"status": "error", "error": str(e)}
        )
