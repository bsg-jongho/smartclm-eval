#!/usr/bin/env python3
"""
Smart CLM RAG 파이프라인
근거자료 저장 및 검색 성능 테스트를 위한 통합 스크립트

실행 방법:
python rag_pipeline.py --step=1  # 근거자료 저장
python rag_pipeline.py --step=2  # 검색 테스트
python rag_pipeline.py --step=3  # 계약서 검토 테스트
python rag_pipeline.py --step=4  # 평가
python rag_pipeline.py --step=5  # Streamlit 결과 시각화
"""

import asyncio
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 환경변수 로딩
from dotenv import load_dotenv
load_dotenv()
from typing import Dict, List, Any, Optional
import httpx
from dataclasses import dataclass
import pandas as pd

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("rag_pipeline.log")
    ]
)
logger = logging.getLogger(__name__)

# 프로젝트 루트 디렉토리 설정
PROJECT_ROOT = Path(__file__).parent
DOCS_ROOT = PROJECT_ROOT / "docs"
RESULTS_DIR = PROJECT_ROOT / "results"
PROCESSED_DIR = PROJECT_ROOT / "processed"

# 결과 저장 디렉토리 생성
RESULTS_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)

# 문서 타입 매핑 (폴더 경로 -> 문서 타입)
DOCUMENT_TYPE_MAPPING = {
    "근거 자료/법령": "law",  # 법령 파일들
    "근거자료/법령": "law",  # 법령 파일들 (공백 없는 버전)
    "근거 자료/체결계약": "executed_contract",  # 체결된 계약서들
    "근거자료/체결계약": "executed_contract",  # 체결된 계약서들 (공백 없는 버전)
    "근거 자료/표준계약서": "standard_contract",  # 표준 계약서 템플릿들
    "근거자료/표준계약서": "standard_contract",  # 표준 계약서 템플릿들 (공백 없는 버전)
    "1. NDA": "standard_contract",  # NDA 표준계약서 (기존 폴더)
    "2. 제품(서비스) 판매": "standard_contract",  # 판매계약서 표준 (기존 폴더)
}


@dataclass
class ProcessingResult:
    """문서 처리 결과를 담는 데이터 클래스"""
    filename: str
    doc_type: str
    folder_path: str
    success: bool
    processing_time: float
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None
    error_message: Optional[str] = None
    doc_parser_result: Optional[Dict] = None


class ExternalServiceClient:
    """외부 서비스 클라이언트 통합 클래스"""
    
    def __init__(self):
        self.doc_converter_url = os.getenv("DOC_CONVERTER_URL", "http://localhost:8001")
        self.doc_parser_url = os.getenv("DOC_PARSER_URL", "http://localhost:8002")
        self.api_url = os.getenv("API_URL", "http://localhost:8000")
        self.timeout = 600.0
    
    async def health_check_all(self) -> Dict[str, bool]:
        """모든 서비스의 헬스체크"""
        services = {
            "doc-converter": f"{self.doc_converter_url}/health",
            "doc-parser": f"{self.doc_parser_url}/health",
            "api": f"{self.api_url}/health"
        }
        
        results = {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            for service, url in services.items():
                try:
                    response = await client.get(url)
                    results[service] = response.status_code == 200
                    logger.info(f"✅ {service} 서비스 정상")
                except Exception as e:
                    results[service] = False
                    logger.error(f"❌ {service} 서비스 오류: {e}")
        
        return results
    
    def determine_doc_type(self, file_path: Path) -> str:
        """파일 경로를 기반으로 문서 타입 결정"""
        # 상대 경로 계산 (docs 폴더 기준)
        relative_path = file_path.relative_to(DOCS_ROOT)
        folder_path = str(relative_path.parent)
        
        # 폴더 경로 매핑에서 문서 타입 찾기
        for pattern, doc_type in DOCUMENT_TYPE_MAPPING.items():
            if folder_path.startswith(pattern) or folder_path == pattern:
                return doc_type
        
        # 기본값: law (근거자료)
        return "law"
    
    async def search_documents_direct(self, query: str, top_k: int = 5, doc_types: List[str] = None) -> Dict:
        """데이터베이스 직접 접근으로 문서 검색"""
        try:
            # 직접 임베딩 서비스 및 검색 로직 구현
            from sqlmodel.ext.asyncio.session import AsyncSession
            from sqlalchemy.ext.asyncio import create_async_engine
            from src.aws.embedding_service import TitanEmbeddingService
            from sqlalchemy import text
            
            # 데이터베이스 연결
            database_url = os.getenv("DATABASE_URL") or f"postgresql+asyncpg://{os.getenv('DATABASE_USER', 'postgres')}:{os.getenv('DATABASE_PASSWORD', 'postgres')}@{os.getenv('DATABASE_HOST', 'localhost')}:{os.getenv('DATABASE_PORT', '5434')}/{os.getenv('DATABASE_NAME', 'smartclm-poc')}"
            async_engine = create_async_engine(database_url, echo=False)
            
            # 임베딩 서비스 초기화
            embedding_service = TitanEmbeddingService()
            
            async with AsyncSession(async_engine) as session:
                # 1. 쿼리 임베딩 생성
                query_embedding = await embedding_service.create_single_embedding(query)
                
                # 2. 벡터 검색 쿼리 구성
                base_query = """
                SELECT 
                    c.id as chunk_id,
                    c.content,
                    c.chunk_type,
                    c.parent_id,
                    d.id as document_id,
                    d.filename,
                    d.doc_type,
                    d.category,
                    (1 - (c.embedding <=> :query_embedding)) as similarity_score
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.embedding IS NOT NULL
                AND d.room_id IS NULL 
                """
                
                # 벡터를 pgvector 형식 문자열로 변환
                vector_str = "[" + ",".join(map(str, query_embedding)) + "]"
                params = {"query_embedding": vector_str}
                
                # 문서 유형 필터
                if doc_types:
                    type_conditions = []
                    for i, doc_type in enumerate(doc_types):
                        param_name = f"doc_type_{i}"
                        type_conditions.append(f"d.doc_type = :{param_name}")
                        params[param_name] = doc_type
                    base_query += f" AND ({' OR '.join(type_conditions)})"
                
                # 유사도 정렬 및 제한
                base_query += " ORDER BY similarity_score DESC LIMIT :top_k"
                params["top_k"] = top_k
                
                # 3. 쿼리 실행
                connection = await session.connection()
                result = await connection.execute(text(base_query), params)
                rows = result.fetchall()
                
                # 4. 결과 변환
                search_results = []
                for row in rows:
                    search_results.append({
                        "chunk_id": row.chunk_id,
                        "content": row.content,
                        "similarity_score": round(row.similarity_score, 4),
                        "chunk_type": row.chunk_type,
                        "parent_id": row.parent_id,
                        "document_id": row.document_id,
                        "filename": row.filename,
                        "doc_type": row.doc_type,
                        "category": row.category,
                    })
                
                return {
                    "results": search_results,
                    "total_found": len(search_results),
                    "query": query
                }
                
        except Exception as e:
            logger.error(f"❌ 직접 검색 실패: {str(e)}")
            return {"results": [], "total_found": 0, "error": str(e)}
    
    async def convert_to_pdf_if_needed(self, file_path: Path) -> Path:
        """필요시 PDF로 변환 (DOCX 등)"""
        if file_path.suffix.lower() == '.pdf':
            return file_path
        
        logger.info(f"🔄 PDF 변환 중: {file_path.name}")
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                with open(file_path, "rb") as f:
                    files = {
                        "file": (file_path.name, f, "application/octet-stream")
                    }
                    
                    response = await client.post(
                        f"{self.doc_converter_url}/convert",
                        files=files
                    )
                
                if response.status_code == 200:
                    # PDF 파일을 임시 저장
                    pdf_path = PROCESSED_DIR / f"{file_path.stem}_converted.pdf"
                    with open(pdf_path, "wb") as f:
                        f.write(response.content)
                    
                    logger.info(f"✅ PDF 변환 완료: {pdf_path.name}")
                    return pdf_path
                else:
                    raise Exception(f"변환 실패: HTTP {response.status_code}")
                    
        except Exception as e:
            logger.error(f"❌ PDF 변환 실패: {str(e)}")
            raise
    
    async def analyze_document_file(self, file_path: Path) -> ProcessingResult:
        """문서 파일을 분석"""
        start_time = time.time()
        doc_type = self.determine_doc_type(file_path)
        relative_path = file_path.relative_to(DOCS_ROOT)
        folder_path = str(relative_path.parent)
        
        try:
            logger.info(f"📄 문서 분석 시작: {file_path.name} (타입: {doc_type})")
            
            # PDF로 변환 (필요시)
            pdf_file_path = await self.convert_to_pdf_if_needed(file_path)
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                with open(pdf_file_path, "rb") as f:
                    files = {
                        "file": (pdf_file_path.name, f, "application/pdf")
                    }
                    data = {"smart_pipeline": True}
                    
                    response = await client.post(
                        f"{self.doc_parser_url}/analyze",
                        files=files,
                        data=data
                    )
                
                if response.status_code == 200:
                    result = response.json()
                    processing_time = time.time() - start_time
                    
                    return ProcessingResult(
                        filename=file_path.name,
                        doc_type=doc_type,
                        folder_path=folder_path,
                        success=True,
                        processing_time=processing_time,
                        page_count=result.get("page_count"),
                        chunk_count=len(result.get("chunks", [])),
                        doc_parser_result=result
                    )
                else:
                    error_msg = f"Doc Parser 오류 (HTTP {response.status_code}): {response.text}"
                    logger.error(error_msg)
                    return ProcessingResult(
                        filename=file_path.name,
                        doc_type=doc_type,
                        folder_path=folder_path,
                        success=False,
                        processing_time=time.time() - start_time,
                        error_message=error_msg
                    )
            
            # 임시 PDF 파일 정리
            if pdf_file_path != file_path and pdf_file_path.exists():
                pdf_file_path.unlink()
                    
        except Exception as e:
            error_msg = f"문서 분석 실패: {str(e)}"
            logger.error(error_msg)
            return ProcessingResult(
                filename=file_path.name,
                doc_type=doc_type,
                folder_path=folder_path,
                success=False,
                processing_time=time.time() - start_time,
                error_message=error_msg
            )
    
    async def save_to_database(self, parsed_result: Dict, source_file: Path, doc_type: str) -> bool:
        """파싱된 결과를 직접 데이터베이스에 저장 (S3 업로드 없음)"""
        try:
            logger.info(f"💾 데이터베이스 저장 시작: {source_file.name} (타입: {doc_type})")
            
            # 로컬에서 직접 데이터베이스에 저장
            from datetime import datetime
            from sqlmodel.ext.asyncio.session import AsyncSession
            from sqlalchemy.ext.asyncio import create_async_engine
            from src.models import Document, Chunk
            from src.aws.embedding_service import TitanEmbeddingService
            from src.documents.chunking import HierarchicalChunker
            import uuid
            
            # 직접 환경변수에서 데이터베이스 URL 가져오기
            database_url = os.getenv("DATABASE_URL") or f"postgresql+asyncpg://{os.getenv('DATABASE_USER', 'postgres')}:{os.getenv('DATABASE_PASSWORD', 'postgres')}@{os.getenv('DATABASE_HOST', '127.0.0.1')}:{os.getenv('DATABASE_PORT', '5434')}/{os.getenv('DATABASE_NAME', 'smartclm-poc')}"
            async_engine = create_async_engine(database_url, echo=False)
            
            async with AsyncSession(async_engine) as session:
                try:
                    # 1. Document 메타데이터 구성
                    filename = source_file.name
                    title = parsed_result.get("title", filename)
                    page_count = parsed_result.get("page_count", 0)
                    markdown_content = parsed_result.get("markdown_content", "")
                    html_content = parsed_result.get("html_content", "")
                    
                    # 파일 크기 계산
                    file_size = source_file.stat().st_size if source_file.exists() else 0
                    
                    # docs/ 기준 상대 경로 계산
                    relative_path = source_file.relative_to(DOCS_ROOT)
                    
                    # 2. Document 생성 (실제 파일 경로 정보 사용)
                    document = Document(
                        room_id=None,  # 전역 문서
                        doc_type=doc_type,
                        category=None,
                        processing_status="processing",
                        filename=filename,
                        version=None,
                        s3_bucket="local",  # 로컬 저장 표시
                        s3_key=str(relative_path),  # docs/ 기준 상대 경로
                        pdf_s3_bucket="local",
                        pdf_s3_key=f"processed/{doc_type}/{filename}",  # 처리된 결과 경로
                        file_size=file_size,
                        pdf_file_size=file_size,  # PDF와 원본이 같다고 가정
                        page_count=page_count,
                        document_metadata={
                            "source": "rag_pipeline",
                            "local_processing": True,
                            "original_path": str(source_file),
                            "processing_time": parsed_result.get("processing_time", 0),
                            "chunks_count": len(parsed_result.get("chunks", [])),
                        },
                        auto_tags=[doc_type],
                        html_content=html_content,
                        markdown_content=markdown_content,
                    )
                    
                    # 3. Document 저장
                    session.add(document)
                    await session.commit()
                    await session.refresh(document)
                    document_id = document.id  # ID를 미리 저장
                    logger.info(f"📄 Document 저장 완료: ID {document_id}")
                    
                    # 4. 청킹 및 임베딩 처리
                    if markdown_content:
                        logger.info(f"✂️ 청킹 및 임베딩 시작: {filename}")
                        
                        chunker = HierarchicalChunker()
                        embedding_service = TitanEmbeddingService()
                        
                        # 마크다운 청킹
                        chunking_result = chunker.chunk_markdown(
                            markdown_content=markdown_content,
                            filename=filename,
                        )
                        
                        # 벡터용 청크 생성
                        vector_ready_chunks = chunker.create_vector_ready_chunks(chunking_result)
                        
                        # 임베딩 생성
                        embedded_chunks = await embedding_service.embed_chunked_documents(vector_ready_chunks)
                        
                        # 청크 저장
                        chunk_objects = []
                        for i, chunk_data in enumerate(embedded_chunks):
                            if chunk_data.get("content", "").strip():
                                chunk = Chunk(
                                    document_id=document.id or 0,
                                    content=chunk_data.get("content", ""),
                                    chunk_index=i,
                                    header_1=chunk_data.get("headers", {}).get("header_1"),
                                    header_2=chunk_data.get("headers", {}).get("header_2"),
                                    header_3=chunk_data.get("headers", {}).get("header_3"),
                                    header_4=chunk_data.get("headers", {}).get("header_4"),
                                    parent_id=chunk_data.get("parent_id"),
                                    child_id=chunk_data.get("child_id"),
                                    chunk_type=chunk_data.get("chunk_type", "child"),
                                    embedding=chunk_data.get("embedding"),
                                    word_count=len(chunk_data.get("content", "").split()),
                                    char_count=len(chunk_data.get("content", "")),
                                    chunk_metadata=chunk_data.get("metadata", {}),
                                    auto_tags=chunk_data.get("auto_tags", []),
                                )
                                chunk_objects.append(chunk)
                        
                        # 배치로 청크 저장
                        for chunk in chunk_objects:
                            session.add(chunk)
                        
                        await session.commit()
                        logger.info(f"✅ 청크 저장 완료: {len(chunk_objects)}개")
                    
                    # 5. 처리 완료 상태로 변경
                    document.processing_status = "completed"
                    session.add(document)
                    await session.commit()
                    
                    logger.info(f"✅ 데이터베이스 저장 완료: {filename} (Document ID: {document_id})")
                    return True
                    
                except Exception as e:
                    await session.rollback()
                    raise e
                    
        except Exception as e:
            logger.error(f"❌ 데이터베이스 저장 오류: {str(e)}")
            import traceback
            logger.error(f"상세 오류: {traceback.format_exc()}")
            return False


class RAGPipeline:
    """RAG 파이프라인 메인 클래스"""
    
    def __init__(self):
        self.client = ExternalServiceClient()
        self.results: List[ProcessingResult] = []
    
    def find_all_documents(self) -> List[Path]:
        """근거 자료 폴더에서만 문서 파일 찾기"""
        supported_extensions = {'.pdf', '.docx', '.doc', '.hwp', '.xlsx', '.xls', '.pptx', '.ppt'}
        document_files = []
        
        # 근거 자료 폴더만 검색
        base_folder = DOCS_ROOT / "근거 자료"
        if base_folder.exists():
            for ext in supported_extensions:
                # 모든 하위 폴더 검색 (법령, 체결계약, 표준계약서)
                document_files.extend(base_folder.glob(f"**/*{ext}"))
        
        return sorted(set(document_files))  # 중복 제거 및 정렬
    
    async def step1_store_reference_materials(self, force: bool = False):
        """Step 1: 근거자료 저장"""
        logger.info("🚀 Step 1: 근거자료 저장 시작")
        
        # 서비스 헬스체크
        health_status = await self.client.health_check_all()
        if not all(health_status.values()):
            unhealthy_services = [k for k, v in health_status.items() if not v]
            logger.error(f"❌ 다음 서비스들이 비정상입니다: {unhealthy_services}")
            return False
        
        # 문서 파일 목록 가져오기
        document_files = self.find_all_documents()
        if not document_files:
            logger.warning("⚠️ docs 폴더에 지원되는 문서 파일이 없습니다.")
            return False
        
        logger.info(f"📁 발견된 문서 파일: {len(document_files)}개")
        
        # 문서 타입별 분류 출력
        type_counts = {}
        for file_path in document_files:
            doc_type = self.client.determine_doc_type(file_path)
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
        
        logger.info("📊 문서 타입별 분류:")
        for doc_type, count in type_counts.items():
            logger.info(f"  - {doc_type}: {count}개")
        
        # 각 문서 파일 처리
        for i, file_path in enumerate(document_files, 1):
            doc_type = self.client.determine_doc_type(file_path)
            logger.info(f"📄 처리 중 ({i}/{len(document_files)}): {file_path.name} ({doc_type})")
            
            # 1. JSON 파일이 있는지 확인 (문서 분석 건너뛰기용)
            doc_type_folder = PROCESSED_DIR / doc_type
            result_file = doc_type_folder / f"{file_path.stem}_parsed.json"
            old_format_file = PROCESSED_DIR / f"{file_path.stem}_{doc_type}_parsed.json"
            
            if not force and (result_file.exists() or old_format_file.exists()):
                # 기존 JSON 파일 로드
                json_file = result_file if result_file.exists() else old_format_file
                logger.info(f"📄 기존 분석 결과 사용: {json_file.name}")
                
                with open(json_file, 'r', encoding='utf-8') as f:
                    doc_parser_result = json.load(f)
                
                result = ProcessingResult(
                    filename=file_path.name,
                    doc_type=doc_type,
                    folder_path=str(file_path.parent),
                    success=True,
                    processing_time=0,
                    page_count=doc_parser_result.get("page_count"),
                    chunk_count=len(doc_parser_result.get("chunks", [])),
                    doc_parser_result=doc_parser_result
                )
            else:
                # 새로 문서 분석
                logger.info(f"🔍 문서 분석 시작: {file_path.name}")
                result = await self.client.analyze_document_file(file_path)
            
            self.results.append(result)
            
            if result.success:
                # 2. 타입별 폴더 생성
                import shutil
                doc_type_folder = PROCESSED_DIR / doc_type
                doc_type_folder.mkdir(exist_ok=True)
                
                # 3. 분석 결과 저장 (타입별 폴더에 JSON 저장)
                result_file = doc_type_folder / f"{file_path.stem}_parsed.json"
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(result.doc_parser_result, f, ensure_ascii=False, indent=2)
                logger.info(f"📄 JSON 저장 완료: {result_file}")
                
                # 4. 원본 파일을 타입별 폴더로 복사
                copied_file = doc_type_folder / file_path.name
                shutil.copy2(file_path, copied_file)
                logger.info(f"📁 파일 복사 완료: {copied_file}")
                
                # 5. 데이터베이스 저장 (중복 체크)
                # DB에 이미 있는지 확인
                db_already_exists = False
                if not force:
                    try:
                        from sqlmodel.ext.asyncio.session import AsyncSession
                        from sqlalchemy.ext.asyncio import create_async_engine
                        from src.models import Document
                        from sqlmodel import select
                        
                        # 직접 환경변수에서 데이터베이스 URL 가져오기
                        database_url = os.getenv("DATABASE_URL") or f"postgresql+asyncpg://{os.getenv('DATABASE_USER', 'postgres')}:{os.getenv('DATABASE_PASSWORD', 'postgres')}@{os.getenv('DATABASE_HOST', 'localhost')}:{os.getenv('DATABASE_PORT', '5434')}/{os.getenv('DATABASE_NAME', 'smartclm-poc')}"
                        async_engine = create_async_engine(database_url, echo=False)
                        
                        async with AsyncSession(async_engine) as session:
                            # 완료된 문서만 스킵, processing 상태는 재처리
                            query = select(Document).where(
                                Document.filename == file_path.name,
                                Document.doc_type == doc_type,
                                Document.processing_status == "completed"
                            )
                            result_doc = await session.exec(query)
                            existing_doc = result_doc.first()
                            
                            if existing_doc:
                                logger.info(f"💾 DB 저장 건너뛰기: {file_path.name} (이미 저장됨: ID {existing_doc.id})")
                                db_already_exists = True
                    except Exception as e:
                        logger.warning(f"⚠️ DB 중복 확인 실패: {file_path.name} - {str(e)}")
                        logger.info(f"💾 중복 확인 실패로 인해 저장을 시도합니다: {file_path.name}")
                
                if not db_already_exists:
                    db_success = await self.client.save_to_database(
                        result.doc_parser_result, 
                        file_path,  # 전체 파일 경로 전달
                        doc_type
                    )
                    
                    if db_success:
                        logger.info(f"✅ 완료: {file_path.name} ({result.processing_time:.2f}초)")
                    else:
                        logger.error(f"❌ DB 저장 실패: {file_path.name}")
                else:
                    logger.info(f"✅ 완료: {file_path.name} ({result.processing_time:.2f}초) - DB는 기존 사용")
            else:
                logger.error(f"❌ 처리 실패: {file_path.name} - {result.error_message}")
            
            # 처리 간 잠시 대기 (시스템 부하 방지)
            await asyncio.sleep(1)
        
        # 결과 요약 저장
        await self._save_processing_summary()
        
        return True
    
    async def _ensure_contract_in_db(self, document_path: Path) -> Optional[int]:
        """계약서가 DB에 없으면 저장하고, 있으면 기존 ID 반환"""
        try:
            from sqlmodel.ext.asyncio.session import AsyncSession
            from sqlalchemy.ext.asyncio import create_async_engine
            from src.models import Document
            from sqlmodel import select
            
            # 데이터베이스 연결
            database_url = os.getenv("DATABASE_URL") or f"postgresql+asyncpg://{os.getenv('DATABASE_USER', 'postgres')}:{os.getenv('DATABASE_PASSWORD', 'postgres')}@{os.getenv('DATABASE_HOST', 'localhost')}:{os.getenv('DATABASE_PORT', '5434')}/{os.getenv('DATABASE_NAME', 'smartclm-poc')}"
            async_engine = create_async_engine(database_url, echo=False)
            
            async with AsyncSession(async_engine) as session:
                # 1. 기존 문서 확인
                query = select(Document).where(
                    Document.filename == document_path.name,
                    Document.doc_type == "contract",
                    Document.processing_status == "completed"
                )
                result = await session.exec(query)
                existing_doc = result.first()
                
                if existing_doc:
                    logger.info(f"🗑️ 기존 계약서 삭제 후 재생성: {document_path.name} (ID: {existing_doc.id})")
                    # 기존 청크들 삭제
                    from sqlmodel import delete
                    from src.models import Chunk
                    chunk_delete_stmt = delete(Chunk).where(Chunk.document_id == existing_doc.id)
                    await session.exec(chunk_delete_stmt)
                    
                    # 기존 문서 삭제
                    doc_delete_stmt = delete(Document).where(Document.id == existing_doc.id)
                    await session.exec(doc_delete_stmt)
                    await session.commit()
                    logger.info(f"✅ 기존 데이터 삭제 완료")
                
                # 2. 새로 분석 및 저장
                logger.info(f"🔍 계약서 분석 및 DB 저장: {document_path.name}")
                doc_data = await self.client.analyze_document_file(document_path)
                
                if not doc_data.success:
                    logger.error(f"❌ 문서 분석 실패: {doc_data.error_message}")
                    return None
                
                logger.info(f"✅ 문서 분석 완료 ({doc_data.processing_time:.2f}초)")
                
                # 3. DB 저장
                db_success = await self.client.save_to_database(
                    doc_data.doc_parser_result,
                    document_path,
                    "contract"  # contract 타입으로 저장
                )
                
                if not db_success:
                    logger.error(f"❌ DB 저장 실패: {document_path.name}")
                    return None
                
                # 4. 저장된 문서 ID 조회
                result2 = await session.exec(query)
                new_doc = result2.first()
                
                if new_doc:
                    logger.info(f"✅ 새 계약서 저장 완료: ID {new_doc.id}")
                    return new_doc.id
                
                return None
                
        except Exception as e:
            logger.error(f"❌ 계약서 DB 처리 실패: {str(e)}")
            return None
    
    async def _get_document_from_db(self, document_id: int) -> Optional[Dict]:
        """DB에서 문서 정보 조회"""
        try:
            from sqlmodel.ext.asyncio.session import AsyncSession
            from sqlalchemy.ext.asyncio import create_async_engine
            from src.models import Document
            from sqlmodel import select
            
            database_url = os.getenv("DATABASE_URL") or f"postgresql+asyncpg://{os.getenv('DATABASE_USER', 'postgres')}:{os.getenv('DATABASE_PASSWORD', 'postgres')}@{os.getenv('DATABASE_HOST', 'localhost')}:{os.getenv('DATABASE_PORT', '5434')}/{os.getenv('DATABASE_NAME', 'smartclm-poc')}"
            async_engine = create_async_engine(database_url, echo=False)
            
            async with AsyncSession(async_engine) as session:
                query = select(Document).where(Document.id == document_id)
                result = await session.exec(query)
                document = result.first()
                
                if document:
                    return {
                        "id": document.id,
                        "filename": document.filename,
                        "doc_type": document.doc_type,
                        "markdown_content": document.markdown_content,
                        "page_count": document.page_count
                    }
                return None
                
        except Exception as e:
            logger.error(f"❌ 문서 조회 실패: {str(e)}")
            return None
    
    async def _get_document_chunks_from_db(self, document_id: int) -> List[Dict]:
        """DB에서 문서의 청크들 조회"""
        try:
            from sqlmodel.ext.asyncio.session import AsyncSession
            from sqlalchemy.ext.asyncio import create_async_engine
            from src.models import Chunk
            from sqlmodel import select
            
            database_url = os.getenv("DATABASE_URL") or f"postgresql+asyncpg://{os.getenv('DATABASE_USER', 'postgres')}:{os.getenv('DATABASE_PASSWORD', 'postgres')}@{os.getenv('DATABASE_HOST', 'localhost')}:{os.getenv('DATABASE_PORT', '5434')}/{os.getenv('DATABASE_NAME', 'smartclm-poc')}"
            async_engine = create_async_engine(database_url, echo=False)
            
            async with AsyncSession(async_engine) as session:
                query = select(Chunk).where(
                    Chunk.document_id == document_id,
                    Chunk.chunk_type == "parent"
                ).order_by(Chunk.chunk_index)
                
                result = await session.exec(query)
                chunks = result.all()
                
                # Chunk 모델을 딕셔너리로 변환
                chunk_list = []
                for chunk in chunks:
                    chunk_dict = {
                        "chunk_index": chunk.chunk_index,
                        "chunk_type": chunk.chunk_type,
                        "content": chunk.content,
                        "header_1": chunk.header_1,
                        "header_2": chunk.header_2,
                        "header_3": chunk.header_3,
                        "chunk_metadata": chunk.chunk_metadata or {}
                    }
                    chunk_list.append(chunk_dict)
                
                logger.info(f"📊 DB에서 {len(chunk_list)}개 parent 청크 조회")
                return chunk_list
                
        except Exception as e:
            logger.error(f"❌ 청크 조회 실패: {str(e)}")
            return []
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # 🔗 체인 분석 메소드들 (Chain 1, 2, 3)
    # ═══════════════════════════════════════════════════════════════════════════════
    
    async def _chain1_identify_violations(self, document_name: str, all_chunks: List[Dict], document_id: int) -> List[Dict]:
        """Chain 1: 전체 계약서를 스캔하여 위법 조항들을 식별"""
        try:
            # 전체 계약서 구조 생성 (원본 조항 번호 보존)
            contract_structure = []
            for i, chunk in enumerate(all_chunks, 1):
                title = chunk.get("header_1", f"조항 {i}")
                content = chunk.get("content", "")[:200] + "..." if len(chunk.get("content", "")) > 200 else chunk.get("content", "")
                

                # title이 이미 "제X조" 형태인지 확인
                if title.startswith("제") and "조" in title:
                    # 이미 조항 번호가 있으면 그대로 사용
                    contract_structure.append(f"{title}: {content}")
                else:
                    # 조항 번호가 없으면 순서대로 추가
                    contract_structure.append(f"제{i}조 {title}: {content}")
            
            full_contract = "\n\n".join(contract_structure)
            
            # Chain 1 프롬프트
            chain1_prompt = f"""# 📋 (주)비에스지파트너스 관점 계약서 위험 조항 식별

**계약서명:** {document_name}
**총 조항수:** {len(all_chunks)}개
**검토 관점:** **(주)비에스지파트너스 입장에서 불리한 조항 중심 분석**

**전체 계약서 구조:**
```
{full_contract}
```

## 🎯 분석 요구사항

이 계약서를 **(주)비에스지파트너스 입장**에서 검토하여 **비에스지파트너스에게 불리하거나 위험한 조항들**을 모두 찾아주세요.

### 비에스지파트너스 관점 상세 검토 기준:

**🔍 비밀정보 관련 위험:**
1. **정보 보호 범위의 과도한 축소**: "비밀" 표시 누락 시 핵심정보도 보호받지 못하는 조항
2. **일방적 비밀유지 의무**: 비에스지파트너스에게만 과도한 비밀유지 의무 부과
3. **비밀정보 정의의 불균형**: 상대방 정보는 넓게, 비에스지파트너스 정보는 좁게 정의

**⚖️ 책임 및 배상 관련 위험:**
4. **과도한 손해배상**: 비에스지파트너스에게만 과중한 배상책임 부과
5. **배상 한도의 불균형**: 상대방은 무제한, 비에스지파트너스는 제한된 배상
6. **입증책임의 전가**: 비에스지파트너스가 무과실을 입증해야 하는 조항

**🚪 계약 해지 및 권리 관련 위험:**
7. **일방적 해지권**: 상대방에게만 해지권을 부여하는 불평등 조항
8. **권리 행사 제한**: 비에스지파트너스의 정당한 권리(가처분, 손해배상청구 등) 제한
9. **통지 의무의 불균형**: 비에스지파트너스에게만 까다로운 통지 의무 부과

**📋 절차 및 기타 위험:**
10. **관할 법원의 불리함**: 비에스지파트너스에게 불리한 원거리 관할 지정
11. **계약 기간의 불균형**: 의무는 길게, 권리는 짧게 설정
12. **법적 위험**: 강행법규 위반으로 비에스지파트너스가 불이익을 받을 수 있는 조항

**⚠️ 특히 주의깊게 검토할 조항:**
- 비밀정보 정의에서 "표시" 요구사항 (실무상 누락 위험 높음)
- 손해배상 조항의 금액 제한 및 면책 조항
- 계약 위반 시 구제수단 제한 조항
- 준거법 및 관할 조항

## 📝 출력 형식 (JSON)

위법 조항이 있다면 다음 형식으로 출력해주세요:

```json
{{
  "violations_found": true,
  "total_violations": 3,
  "violations": [
    {{
      "clause_number": "제3조",
      "clause_title": "비밀정보의 정의",
      "risk_type": "정보_보호_범위의_과도한_축소",
      "risk_level": "높음",
      "brief_reason": "비밀 표시 누락 시 핵심정보도 보호받지 못해 비에스지파트너스에게 매우 위험"
    }},
    {{
      "clause_number": "제9조", 
      "clause_title": "손해배상",
      "risk_type": "과도한_손해배상_및_권리제한",
      "risk_level": "높음",
      "brief_reason": "비에스지파트너스만 배상 한도 제한되고 가처분 청구권도 박탈당함"
    }},
    {{
      "clause_number": "제8조",
      "clause_title": "계약기간",
      "risk_type": "계약_기간의_불균형",
      "risk_level": "중간", 
      "brief_reason": "비에스지파트너스의 의무는 3년+1년, 상대방 의무는 계약 종료와 함께 소멸"
    }}
  ]
}}
```

위법 조항이 없다면:
```json
{{
  "violations_found": false,
  "total_violations": 0,
  "violations": []
}}
```

**중요**: 반드시 JSON 형식으로만 출력하고, 추가 설명은 하지 마세요."""

            # AI 호출
            from src.aws.bedrock_service import BedrockService
            bedrock_service = BedrockService()
            
            response = bedrock_service.invoke_model(
                prompt=chain1_prompt,
                max_tokens=2000,
                temperature=0.0
            )
            
            # JSON 파싱
            response_text = response.get("text", "") if isinstance(response, dict) else str(response)
            
            import json
            import re
            
            # JSON 추출 (```json 태그 제거)
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # JSON 태그 없이 직접 JSON인 경우
                json_str = response_text.strip()
            
            try:
                result = json.loads(json_str)
                violations = result.get("violations", [])
                
                # chunk_index 추가 (조항 번호에서 추출)
                for violation in violations:
                    clause_num = violation.get("clause_number", "")
                    # "제3조" -> 3 추출
                    import re
                    match = re.search(r'제(\d+)조', clause_num)
                    if match:
                        violation["chunk_index"] = int(match.group(1)) - 1  # 0-based
                    else:
                        violation["chunk_index"] = 0
                
                logger.info(f"🔍 Chain 1 결과: {len(violations)}개 위법 조항 후보 식별")
                return violations
                
            except json.JSONDecodeError as e:
                logger.error(f"❌ Chain 1 JSON 파싱 실패: {e}")
                logger.error(f"응답 텍스트: {response_text[:500]}...")
                return []
                
        except Exception as e:
            logger.error(f"❌ Chain 1 실패: {str(e)}")
            return []
    
    async def _chain2_search_related_laws(self, violation_candidates: List[Dict]) -> List[Dict]:
        """Chain 2: 각 위법 조항별로 관련 법령을 병렬 검색"""
        violations_with_laws = []
        
        # 병렬 처리를 위한 태스크 생성
        search_tasks = []
        for violation in violation_candidates:
            search_query = f"{violation.get('clause_title', '')} {violation.get('brief_reason', '')}"
            task = self._search_laws_for_violation(violation, search_query)
            search_tasks.append(task)
        
        # 병렬 실행
        if search_tasks:
            results = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"❌ 법령 검색 실패: {result}")
                else:
                    violations_with_laws.append(result)
        
        logger.info(f"🔍 Chain 2 결과: {len(violations_with_laws)}개 조항의 법령 검색 완료")
        return violations_with_laws
    
    async def _search_laws_for_violation(self, violation: Dict, search_query: str) -> Dict:
        """개별 위법 조항에 대한 법령 검색"""
        try:
            # 관련 법령 검색
            legal_docs = await self.client.search_documents_direct(
                query=search_query,
                top_k=3,
                doc_types=["law"]
            )
            
            violation_with_laws = violation.copy()
            violation_with_laws["related_laws"] = legal_docs.get("results", [])
            violation_with_laws["laws_found"] = len(legal_docs.get("results", []))
            
            logger.info(f"  📖 {violation.get('clause_title', '')}: {len(legal_docs.get('results', []))}개 관련 법령 발견")
            return violation_with_laws
            
        except Exception as e:
            logger.error(f"❌ 법령 검색 실패 ({violation.get('clause_title', '')}): {e}")
            violation_with_laws = violation.copy()
            violation_with_laws["related_laws"] = []
            violation_with_laws["laws_found"] = 0
            return violation_with_laws
    
    async def _chain3_detailed_analysis(self, violations_with_laws: List[Dict], document_name: str) -> Dict:
        """Chain 3: 위법 조항과 법령 근거를 바탕으로 최종 상세 분석"""
        try:
            if not violations_with_laws:
                return {"violations": []}
            
            final_violations = []
            
            for violation_data in violations_with_laws:
                try:
                    # 상세 분석을 위한 프롬프트 구성
                    clause_title = violation_data.get("clause_title", "")
                    clause_number = violation_data.get("clause_number", "")
                    risk_type = violation_data.get("risk_type", "")
                    brief_reason = violation_data.get("brief_reason", "")
                    related_laws = violation_data.get("related_laws", [])
                    
                    # 관련 법령 텍스트 구성
                    laws_text = ""
                    if related_laws:
                        law_descriptions = []
                        for i, law in enumerate(related_laws, 1):
                            filename = law.get('filename', '').replace('.pdf', '')
                            content = law.get('content', '')[:300] + "..." if len(law.get('content', '')) > 300 else law.get('content', '')
                            similarity = f"(유사도: {law.get('similarity_score', 0):.3f})"
                            law_descriptions.append(f"{i}. {filename} {similarity}\n{content}")
                        laws_text = "\n\n".join(law_descriptions)
                    else:
                        laws_text = "관련 법령을 찾을 수 없습니다."
                    
                    chain3_prompt = f"""# 🏛️ (주)비에스지파트너스 관점 계약서 조항 상세 분석

**분석 대상 조항:** {clause_number} {clause_title}
**검토 관점:** (주)비에스지파트너스 입장에서의 위험성 평가
**예비 위험 유형:** {risk_type}
**예비 판단:** {brief_reason}

## 📚 관련 법령 근거

{laws_text}

## 🎯 상세 분석 요구사항

위 조항과 관련 법령을 바탕으로 **(주)비에스지파트너스 입장에서** 다음 형식으로 상세 분석해주세요:

### 출력 형식 (JSON):
```json
{{
  "조항_위치": "{clause_number} ({clause_title})",
  "리스크_유형": "비에스지파트너스 관점의 구체적인 위험 유형 (예: 정보 보호 범위의 과도한 축소, 과도한_배상책임, 불리한_해지조건)",
  "판단_근거": "비에스지파트너스에게 어떤 불이익이 있는지 관련 법령과 함께 구체적 제시 (예: 비에스지파트너스에게만 민법 제398조 위반 수준의 과도한 배상책임 부과)",
  "의견": "비에스지파트너스 입장에서의 구체적인 개선 방안 (예: 상호 배상책임으로 변경하거나 비에스지파트너스 배상 한도 설정 필요)",
  "관련_법령": ["구체적인 법령 조항명"]
}}
```

**중요**: 
1. 반드시 JSON 형식으로만 출력
2. **(주)비에스지파트너스 입장**에서 불리한 점을 중심으로 분석
3. 관련 법령이 있다면 구체적인 조항명 명시  
4. 비에스지파트너스에게 실무적으로 도움이 되는 개선방안 제시
5. 추가 설명 없이 JSON만 출력"""

                    # AI 호출
                    from src.aws.bedrock_service import BedrockService
                    bedrock_service = BedrockService()
                    
                    response = bedrock_service.invoke_model(
                        prompt=chain3_prompt,
                        max_tokens=1500,
                        temperature=0.0
                    )
                    
                    # JSON 파싱
                    response_text = response.get("text", "") if isinstance(response, dict) else str(response)
                    
                    import json
                    import re
                    
                    # JSON 추출
                    json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
                    else:
                        json_str = response_text.strip()
                    
                    try:
                        detailed_analysis = json.loads(json_str)
                        final_violations.append(detailed_analysis)
                        logger.info(f"  ✅ {clause_title} 상세 분석 완료")
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ Chain 3 JSON 파싱 실패 ({clause_title}): {e}")
                        # 실패 시 기본 형식으로 대체
                        final_violations.append({
                            "조항_위치": f"{clause_number} ({clause_title})",
                            "리스크_유형": risk_type,
                            "판단_근거": brief_reason,
                            "의견": "상세 분석 실패로 인해 기본 정보만 제공",
                            "관련_법령": [law.get('filename', '').replace('.pdf', '') for law in related_laws[:2]]
                        })
                
                except Exception as e:
                    logger.error(f"❌ 개별 조항 분석 실패 ({violation_data.get('clause_title', '')}): {e}")
                    continue
            
            return {
                "contract_analysis": {
                    "document_name": document_name,
                    "total_violations": len(final_violations),
                    "analysis_method": "3_chain_analysis",
                    "analysis_date": datetime.now().isoformat()
                },
                "violations": final_violations
            }
            
        except Exception as e:
            logger.error(f"❌ Chain 3 실패: {str(e)}")
            return {"violations": []}
    
    async def _save_chain_analysis_results(self, document_name: str, analysis_result: Dict, performance_stats: Dict):
        """체인 분석 결과 저장"""
        try:
            # 타임스탬프 생성
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 결과 파일명
            result_filename = f"chain_analysis_{document_name.replace('.docx', '')}_{timestamp}.json"
            result_file = RESULTS_DIR / result_filename
            
            # 최종 결과 구성
            final_result = {
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "document_name": document_name,
                    "analysis_method": "3_chain_analysis",
                    "performance": performance_stats
                },
                "summary": {
                    "violations_found": len(analysis_result.get("violations", [])),
                    "total_analysis_time": performance_stats.get("total_time", 0),
                    "efficiency_gain": f"기존 조항별 분석 대비 {performance_stats.get('total_clauses', 0) * 30 - performance_stats.get('total_time', 0):.1f}초 단축"
                },
                "analysis_result": analysis_result
            }
            
            # JSON 파일 저장
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(final_result, f, ensure_ascii=False, indent=2)
            
            # 로그 출력
            logger.info("=" * 50)
            logger.info("📝 체인 분석 결과 요약")
            logger.info("=" * 50)
            logger.info(f"📄 문서명: {document_name}")
            logger.info(f"🔍 위법 조항 발견: {len(analysis_result.get('violations', []))}개")
            logger.info(f"⏱️ 전체 분석 시간: {performance_stats.get('total_time', 0):.2f}초")
            logger.info(f"   - Chain 1 (위법 조항 식별): {performance_stats.get('chain1_time', 0):.2f}초")
            logger.info(f"   - Chain 2 (법령 검색): {performance_stats.get('chain2_time', 0):.2f}초")  
            logger.info(f"   - Chain 3 (상세 분석): {performance_stats.get('chain3_time', 0):.2f}초")
            
            # 개별 위법 조항 요약
            if analysis_result.get("violations"):
                logger.info(f"📊 발견된 위법 조항:")
                for i, violation in enumerate(analysis_result["violations"], 1):
                    logger.info(f"   {i}. {violation.get('조항_위치', '')} - {violation.get('리스크_유형', '')}")
            
            logger.info(f"💾 결과 저장: {result_file}")
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error(f"❌ 체인 분석 결과 저장 실패: {str(e)}")
     
    async def _save_processing_summary(self):
        """처리 결과 요약 저장"""
        # 타입별 통계
        type_stats = {}
        for result in self.results:
            doc_type = result.doc_type
            if doc_type not in type_stats:
                type_stats[doc_type] = {"total": 0, "success": 0, "failed": 0}
            
            type_stats[doc_type]["total"] += 1
            if result.success:
                type_stats[doc_type]["success"] += 1
            else:
                type_stats[doc_type]["failed"] += 1
        
        summary = {
            "total_files": len(self.results),
            "successful": len([r for r in self.results if r.success]),
            "failed": len([r for r in self.results if not r.success]),
            "total_processing_time": sum(r.processing_time for r in self.results),
            "type_statistics": type_stats,
            "details": [
                {
                    "filename": r.filename,
                    "doc_type": r.doc_type,
                    "folder_path": r.folder_path,
                    "success": r.success,
                    "processing_time": r.processing_time,
                    "page_count": r.page_count,
                    "chunk_count": r.chunk_count,
                    "error": r.error_message
                }
                for r in self.results
            ]
        }
        
        summary_file = RESULTS_DIR / "processing_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        logger.info(f"📊 처리 요약:")
        logger.info(f"  - 전체: {summary['total_files']}개")
        logger.info(f"  - 성공: {summary['successful']}개")
        logger.info(f"  - 실패: {summary['failed']}개")
        logger.info(f"  - 총 처리 시간: {summary['total_processing_time']:.2f}초")
        
        logger.info(f"📋 타입별 통계:")
        for doc_type, stats in type_stats.items():
            logger.info(f"  - {doc_type}: {stats['success']}/{stats['total']} 성공")
        
        logger.info(f"💾 요약 저장: {summary_file}")
    
    async def _save_search_test_results(self, search_results: List[Dict]):
        """검색 테스트 결과 저장"""
        # 결과 요약 계산
        total_queries = len(search_results)
        successful_queries = len([r for r in search_results if r.get("success", False)])
        failed_queries = total_queries - successful_queries
        
        # 검색 시간 통계
        search_times = [r.get("search_time", 0) for r in search_results if r.get("success")]
        avg_search_time = sum(search_times) / len(search_times) if search_times else 0
        
        # 결과 수 통계
        result_counts = [r.get("total_results", 0) for r in search_results if r.get("success")]
        avg_results = sum(result_counts) / len(result_counts) if result_counts else 0
        
        # 카테고리별 성공률
        category_stats = {}
        for result in search_results:
            category = result.get("category", "unknown")
            if category not in category_stats:
                category_stats[category] = {"total": 0, "success": 0}
            category_stats[category]["total"] += 1
            if result.get("success", False):
                category_stats[category]["success"] += 1
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "test_summary": {
                "total_queries": total_queries,
                "successful_queries": successful_queries,
                "failed_queries": failed_queries,
                "success_rate": successful_queries / total_queries if total_queries > 0 else 0,
                "avg_search_time_seconds": round(avg_search_time, 3),
                "avg_results_per_query": round(avg_results, 1)
            },
            "category_performance": {
                category: {
                    "success_rate": stats["success"] / stats["total"] if stats["total"] > 0 else 0,
                    "success_count": stats["success"],
                    "total_count": stats["total"]
                }
                for category, stats in category_stats.items()
            },
            "detailed_results": search_results
        }
        
        # 결과 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = RESULTS_DIR / f"search_test_results_{timestamp}.json"
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        # 로그 출력
        logger.info("=" * 50)
        logger.info("🔍 검색 테스트 결과 요약")
        logger.info("=" * 50)
        logger.info(f"📊 전체 쿼리: {total_queries}개")
        logger.info(f"✅ 성공: {successful_queries}개 ({successful_queries/total_queries*100:.1f}%)")
        logger.info(f"❌ 실패: {failed_queries}개")
        logger.info(f"⏱️ 평균 검색 시간: {avg_search_time:.3f}초")
        logger.info(f"📄 평균 결과 수: {avg_results:.1f}개")
        
        logger.info("\n📈 카테고리별 성공률:")
        for category, stats in category_stats.items():
            success_rate = stats["success"] / stats["total"] * 100
            logger.info(f"  - {category}: {stats['success']}/{stats['total']} ({success_rate:.1f}%)")
        
        logger.info(f"\n💾 상세 결과 저장: {results_file}")
    
    async def _create_manual_sections(self, doc_parser_result: Dict) -> List[Dict]:
        """한국어 조항 패턴을 인식하여 조항별로 분할 (독립 함수)"""
        try:
            import re
            
            # 마크다운 내용 가져오기
            markdown_content = doc_parser_result.get("markdown_content", "")
            if not markdown_content:
                logger.error("❌ 마크다운 내용이 없습니다.")
                return []
            
            logger.info(f"📄 조항 분할 시작 (총 {len(markdown_content)} 문자)")
            
            # 한국어 조항 패턴 인식 및 분할
            lines = markdown_content.split('\n')
            sections = []
            current_section = {"header_1": "서문", "content": ""}
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # 헤딩 또는 조항 패턴 발견 시 새로운 섹션 시작
                is_new_section = False
                header_text = ""
                
                if line.startswith('#'):
                    # 마크다운 헤딩
                    is_new_section = True
                    header_text = line.lstrip('#').strip()
                elif re.match(r'^제\s*\d+\s*조', line):
                    # "제X조" 또는 "제 X 조" 패턴 - 원본 조항 번호 보존
                    is_new_section = True
                    header_text = line  # 원본 그대로 사용
                    logger.info(f"🔍 조항 패턴 발견: {line}")
                elif line.startswith('Article') or line.startswith('ARTICLE'):
                    # 영문 조항
                    is_new_section = True
                    header_text = line
                elif any(line.startswith(pattern) for pattern in ['1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.']):
                    # 번호 매긴 조항 (1., 2., 3. 등)
                    if len(line) > 10 and not current_section["content"]:
                        is_new_section = True
                        header_text = line
                
                if is_new_section:
                    # 이전 섹션 저장
                    if current_section["content"].strip():
                        current_section["chunk_type"] = "parent"
                        sections.append(current_section)
                    
                    # 새 섹션 시작 - 원본 조항 번호 보존
                    current_section = {
                        "header_1": header_text,  # 원본 조항 번호 그대로 사용
                        "content": "",
                        "chunk_type": "parent"
                    }
                else:
                    # 내용 추가
                    if current_section["content"]:
                        current_section["content"] += "\n"
                    current_section["content"] += line
            
            # 마지막 섹션 저장
            if current_section["content"].strip():
                current_section["chunk_type"] = "parent"
                sections.append(current_section)
            
            # 헤딩이 없으면 문단 기준으로 분할
            if not sections:
                logger.info("📄 헤딩이 없어 문단 기준으로 분할합니다.")
                paragraphs = [p.strip() for p in markdown_content.split('\n\n') if p.strip()]
                
                for i, paragraph in enumerate(paragraphs[:10], 1):  # 최대 10개 문단
                    if len(paragraph) > 50:  # 너무 짧은 문단 제외
                        sections.append({
                            "header_1": f"조항 {i}",
                            "content": paragraph,
                            "chunk_type": "parent"
                        })
            
            logger.info(f"✅ {len(sections)}개 조항으로 분할 완료")
            
            # 각 섹션 미리보기
            for i, section in enumerate(sections[:3], 1):
                preview = section["content"][:100] + "..." if len(section["content"]) > 100 else section["content"]
                logger.info(f"  {i}. {section['header_1']}: {preview}")
                
            return sections
            
        except Exception as e:
            logger.error(f"❌ 조항 분할 실패: {str(e)}")
            return []
    
    async def _perform_contract_review(self, section_title: str, section_content: str, document_name: str, all_sections: List[Dict] = None, current_section_index: int = 1, document_id: Optional[int] = None) -> Dict:
        """계약서 조항 검토 수행"""
        try:
            # 1. 관련 법령 검색
            search_query = f"{section_title} {section_content[:200]}"  # 조항 제목과 내용 일부로 검색
            
            legal_docs = await self.client.search_documents_direct(
                query=search_query,
                top_k=3,
                doc_types=["law"]  # 법령만 검색
            )
            
            # 2. 의미적 유사도 기반 관련 조항 검색
            contract_context = ""
            if all_sections:
                # 전체 구조 개요 (제목만)
                contract_overview = []
                for idx, section in enumerate(all_sections, 1):
                    title = section.get("header_1", f"조항 {idx}")
                    marker = " ← [현재 검토 중]" if idx == current_section_index else ""
                    contract_overview.append(f"{idx}. {title}{marker}")
                
                # 현재 조항과 의미적으로 유사한 조항들 검색 (document_id 기반)
                similar_clauses = []
                if document_id:
                    try:
                        from src.aws.embedding_service import TitanEmbeddingService
                        from sqlmodel.ext.asyncio.session import AsyncSession
                        from sqlalchemy.ext.asyncio import create_async_engine
                        from sqlalchemy import text
                        
                        # 현재 조항 임베딩 생성
                        embedding_service = TitanEmbeddingService()
                        current_clause_embedding = await embedding_service.create_single_embedding(section_content)
                        
                        # 같은 문서 내에서 유사한 조항 검색 (현재 조항 제외)
                        database_url = os.getenv("DATABASE_URL") or f"postgresql+asyncpg://{os.getenv('DATABASE_USER', 'postgres')}:{os.getenv('DATABASE_PASSWORD', 'postgres')}@{os.getenv('DATABASE_HOST', '127.0.0.1')}:{os.getenv('DATABASE_PORT', '5434')}/{os.getenv('DATABASE_NAME', 'smartclm-poc')}"
                        async_engine = create_async_engine(database_url, echo=False)
                        
                        async with AsyncSession(async_engine) as session:
                            # 벡터 검색 쿼리 (document_id 기반, 현재 조항 제외)
                            vector_str = "[" + ",".join(map(str, current_clause_embedding)) + "]"
                            similarity_query = """
                            SELECT 
                                c.header_1,
                                c.content,
                                c.chunk_index,
                                (1 - (c.embedding <=> :query_embedding)) as similarity_score
                            FROM chunks c
                            WHERE c.embedding IS NOT NULL
                            AND c.chunk_type = 'parent'
                            AND c.document_id = :document_id
                            AND c.chunk_index != :current_index
                            ORDER BY similarity_score DESC
                            LIMIT 3
                            """
                            
                            connection = await session.connection()
                            result = await connection.execute(text(similarity_query), {
                                "query_embedding": vector_str,
                                "document_id": document_id,
                                "current_index": current_section_index - 1  # 0-based
                            })
                            similar_clauses = result.fetchall()
                            
                        # 관련 조항들 포맷
                        related_sections = []
                        for clause in similar_clauses:
                            similarity = clause.similarity_score
                            clause_num = clause.chunk_index + 1  # 1-based로 변환
                            title = clause.header_1 or f"조항 {clause_num}"
                            content = clause.content[:300] + "..." if len(clause.content) > 300 else clause.content
                            
                            related_sections.append(f"""**조항 {clause_num}: {title}** (유사도: {similarity:.3f})
{content}""")
                        
                        logger.info(f"🔗 관련 조항 검색 완료: {len(similar_clauses)}개 조항 발견")
                        
                    except Exception as e:
                        logger.warning(f"⚠️ 관련 조항 검색 실패: {str(e)}, 슬라이딩 윈도우로 대체")
                        # 실패 시 기존 슬라이딩 윈도우 방식으로 대체
                        similar_clauses = []
                        window_size = 2
                        start_idx = max(0, current_section_index - 1 - window_size)
                        end_idx = min(len(all_sections), current_section_index + window_size)
                        
                        related_sections = []
                        for idx in range(start_idx, end_idx):
                            if idx != current_section_index - 1:  # 현재 조항 제외
                                section = all_sections[idx]
                                section_num = idx + 1
                                title = section.get("header_1", f"조항 {section_num}")
                                content = section.get("content", "")[:300] + "..." if len(section.get("content", "")) > 300 else section.get("content", "")
                                
                                related_sections.append(f"""**조항 {section_num}: {title}** (인접 조항)
{content}""")
                
                else:
                    # document_id가 없는 경우 슬라이딩 윈도우 사용
                    logger.info("🔗 document_id 없음, 슬라이딩 윈도우 방식 사용")
                    similar_clauses = []
                    window_size = 2
                    start_idx = max(0, current_section_index - 1 - window_size)
                    end_idx = min(len(all_sections), current_section_index + window_size)
                    
                    related_sections = []
                    for idx in range(start_idx, end_idx):
                        if idx != current_section_index - 1:  # 현재 조항 제외
                            section = all_sections[idx]
                            section_num = idx + 1
                            title = section.get("header_1", f"조항 {section_num}")
                            content = section.get("content", "")[:300] + "..." if len(section.get("content", "")) > 300 else section.get("content", "")
                            
                            related_sections.append(f"""**조항 {section_num}: {title}** (인접 조항)
{content}""")
                
                contract_context = f"""
**계약서 전체 구조 ({document_name}):**
{chr(10).join(contract_overview)}

**검토 범위:**
- 총 {len(all_sections)}개 조항 중 현재 조항: {current_section_index}/{len(all_sections)}
- 계약 유형: 비밀유지계약서 (NDA)

**🔗 계약서 내 관련 조항 (의미적 유사도 기반):**

{chr(10).join(related_sections) if related_sections else "관련 조항을 찾을 수 없습니다."}
"""

            # 3. 개선된 검토 프롬프트 구성
            prompt_template = """# 🏛️ 전문 계약서 조항 법적 검토 및 위험 분석

당신은 계약법, 민법, 상법, 개인정보보호법 등에 정통한 변호사로서 계약서 조항의 법적 위험을 분석하고 실무적 개선방안을 제시하는 전문가입니다.

{contract_context}

## 📋 현재 검토 대상 조항

**조항 제목:** {section_title}
**조항 내용:**
```
{section_content}
```

{legal_references}

## 🔍 상세 법적 검토 요구사항

### 1. 법적 유효성 분석
- 해당 조항의 법적 구속력 여부
- 민법, 상법 등 기본법과의 합치성
- 강행법규 위반 가능성 검토
- 공서양속 위반 여부

### 2. 위험요소 및 분쟁 가능성
- 조항 해석상 모호한 부분
- 일방 당사자에게 과도하게 불리한 조항
- 불공정약관 해당 가능성
- 실제 분쟁 발생 시 예상 쟁점

### 3. 전체 계약서와의 일관성
- 다른 조항과의 상충 여부
- 계약서 전체 목적과의 정합성
- 조항 간 연계성 및 보완성

### 4. 업계 표준 및 모범관행 비교
- 동종 업계 표준 계약서와의 비교
- 일반적 상관례와의 부합성
- 법원 판례 동향과의 일치성

## 📝 분석 결과 작성 형식

### ⚖️ 법적 유효성
[조항의 법적 효력, 강행법규 위반 여부, 공서양속 적합성 등]

### ⚠️ 위험요소
[구체적 위험 사항을 번호를 매겨 나열]
1. 
2. 
3. 

### 📖 관련 법령 위반 검토
[해당 법령 조항과 위반 가능성, 제재 수준]

### 🔧 개선 권고사항
[구체적이고 실무적인 조항 개선 방안]
1. 
2. 
3. 

### 📊 종합 위험도 평가
**위험도:** [높음/중간/낮음/안전]

### 🎯 핵심 권고사항
[가장 우선적으로 개선해야 할 사항 3가지]

### 📋 법적 근거 요약
[인용된 법령 및 조항의 핵심 내용]

계약서 전체의 맥락을 고려하여 해당 조항이 계약 목적 달성에 적합한지, 당사자 간 권리의무가 균형있게 배분되었는지 종합적으로 검토해주세요."""

            # 4. 법령 근거 텍스트 구성
            legal_references = "## ❌ 관련 법령을 찾을 수 없습니다.\n검색된 법령이 없어 일반적인 법리에 따라 검토를 진행합니다."
            if legal_docs.get("results"):
                references = []
                for i, doc in enumerate(legal_docs["results"], 1):
                    filename = doc['filename'].replace('.pdf', '')
                    content = doc['content'][:500] + "..." if len(doc['content']) > 500 else doc['content']
                    similarity = f"(유사도: {doc.get('similarity_score', 0):.3f})"
                    references.append(f"### 📖 {i}. {filename} {similarity}\n```\n{content}\n```")
                legal_references = "## 📚 관련 법령 및 판례 근거 (데이터베이스 검색)\n\n" + "\n\n".join(references)
            else:
                legal_references = "## 📚 관련 법령 및 판례 근거 (데이터베이스 검색)\n\n❌ 관련 법령을 찾을 수 없습니다.\n검색된 법령이 없어 일반적인 법리에 따라 검토를 진행합니다."
            
            # 5. 완성된 프롬프트
            full_prompt = prompt_template.format(
                contract_context=contract_context,
                section_title=section_title,
                section_content=section_content,
                legal_references=legal_references
            )
            
            # 6. LLM 호출 (비스트리밍) - 더 상세한 분석을 위해 토큰 수 증가
            from src.aws.bedrock_service import BedrockService
            bedrock_service = BedrockService()
            
            # 프롬프트 크기 측정
            prompt_chars = len(full_prompt)
            estimated_input_tokens = prompt_chars // 4  # 대략적인 토큰 추정 (1토큰 ≈ 4글자)
            
            logger.info(f"🤖 AI 조항 검토 시작: {section_title}")
            logger.info(f"   📏 프롬프트 크기: {prompt_chars:,}자 (≈{estimated_input_tokens:,} 토큰)")
            
            response = bedrock_service.invoke_model(
                prompt=full_prompt,
                max_tokens=4000,  # 더 상세한 분석을 위해 증가
                temperature=0.0
            )
            
            # 토큰 사용량 상세 로그
            token_usage = response.get("usage", {})
            processing_time = response.get("timing", {}).get("processing_time_ms", 0)
            input_tokens = token_usage.get("input_tokens", 0)
            output_tokens = token_usage.get("output_tokens", 0)
            total_tokens = token_usage.get("total_tokens", 0)
            
            logger.info(f"✅ AI 검토 완료: {section_title} ({processing_time}ms)")
            logger.info(f"   📊 토큰 사용량: 입력 {input_tokens:,} + 출력 {output_tokens:,} = 총 {total_tokens:,}")
            
            # 7. 결과 구성
            review_text = response.get("text", "") if isinstance(response, dict) else str(response)
            
            return {
                "section_title": section_title,
                "section_content": section_content[:500] + "..." if len(section_content) > 500 else section_content,
                "legal_references_count": len(legal_docs.get("results", [])),
                "legal_references": legal_docs.get("results", []),
                "review_analysis": review_text,
                "contract_context_provided": all_sections is not None,
                "total_sections_in_contract": len(all_sections) if all_sections else 0,
                "current_section_index": current_section_index,
                "token_usage": token_usage,
                "processing_time_ms": processing_time,
                "prompt_size": {
                    "characters": prompt_chars,
                    "estimated_tokens": estimated_input_tokens
                },
                "optimization_info": {
                    "related_sections_count": len(related_sections) if 'related_sections' in locals() else 0,
                    "total_sections_available": len(all_sections) if all_sections else 0,
                    "search_method": "semantic_similarity" if document_id and similar_clauses else "sliding_window_fallback",
                    "semantic_similarity_count": len(similar_clauses) if 'similar_clauses' in locals() else 0,
                    "document_id_provided": document_id is not None
                },
                "success": True
            }
            
        except Exception as e:
            logger.error(f"❌ 계약서 검토 수행 실패: {str(e)}")
            return {
                "section_title": section_title,
                "success": False,
                "error": str(e)
            }
    
    async def _save_contract_review_results(self, document_name: str, review_results: List[Dict]):
        """계약서 검토 결과 저장"""
        # 결과 요약 계산
        total_sections = len(review_results)
        successful_reviews = len([r for r in review_results if r.get("success", False)])
        failed_reviews = total_sections - successful_reviews
        
        # 검토 시간 통계
        review_times = [r.get("processing_time_ms", 0) for r in review_results if r.get("success")]
        avg_review_time = sum(review_times) / len(review_times) if review_times else 0
        
        # 법령 참조 통계
        legal_ref_counts = [r.get("legal_references_count", 0) for r in review_results if r.get("success")]
        avg_legal_refs = sum(legal_ref_counts) / len(legal_ref_counts) if legal_ref_counts else 0
        
        # 토큰 사용량 통계
        successful_results = [r for r in review_results if r.get("success", False)]
        if successful_results:
            total_input_tokens = sum(r.get("token_usage", {}).get("input_tokens", 0) for r in successful_results)
            total_output_tokens = sum(r.get("token_usage", {}).get("output_tokens", 0) for r in successful_results)
            total_tokens = sum(r.get("token_usage", {}).get("total_tokens", 0) for r in successful_results)
            avg_input_tokens = total_input_tokens / len(successful_results)
            avg_output_tokens = total_output_tokens / len(successful_results)
            avg_total_tokens = total_tokens / len(successful_results)
            
            # 프롬프트 크기 통계
            prompt_sizes = [r.get("prompt_size", {}).get("characters", 0) for r in successful_results]
            avg_prompt_size = sum(prompt_sizes) / len(prompt_sizes) if prompt_sizes else 0
            
            # 관련 조항 효율성 통계
            related_counts = [r.get("optimization_info", {}).get("related_sections_count", 0) for r in successful_results]
            avg_related_sections = sum(related_counts) / len(related_counts) if related_counts else 0
            
            # 검색 방법 통계
            search_methods = [r.get("optimization_info", {}).get("search_method", "unknown") for r in successful_results]
            semantic_count = search_methods.count("semantic_similarity")
            fallback_count = search_methods.count("sliding_window_fallback")
        else:
            total_input_tokens = total_output_tokens = total_tokens = 0
            avg_input_tokens = avg_output_tokens = avg_total_tokens = 0
            avg_prompt_size = avg_related_sections = 0
            semantic_count = fallback_count = 0
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "document_name": document_name,
            "review_summary": {
                "total_sections": total_sections,
                "successful_reviews": successful_reviews,
                "failed_reviews": failed_reviews,
                "success_rate": successful_reviews / total_sections if total_sections > 0 else 0,
                "avg_review_time_ms": round(avg_review_time, 1),
                "avg_legal_references": round(avg_legal_refs, 1),
                "token_usage": {
                    "total_input_tokens": total_input_tokens,
                    "total_output_tokens": total_output_tokens,
                    "total_tokens": total_tokens,
                    "avg_input_tokens": round(avg_input_tokens, 1),
                    "avg_output_tokens": round(avg_output_tokens, 1),
                    "avg_total_tokens": round(avg_total_tokens, 1)
                },
                "optimization": {
                    "avg_prompt_size_chars": round(avg_prompt_size, 1),
                    "avg_related_sections": round(avg_related_sections, 1),
                    "semantic_search_count": semantic_count,
                    "fallback_count": fallback_count,
                    "optimization_method": "semantic_similarity"
                }
            },
            "detailed_results": review_results
        }
        
        # 결과 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = RESULTS_DIR / f"contract_review_results_{timestamp}.json"
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        # 로그 출력
        logger.info("=" * 50)
        logger.info("📝 계약서 검토 결과 요약 (의미적 유사도 최적화)")
        logger.info("=" * 50)
        logger.info(f"📄 문서명: {document_name}")
        logger.info(f"📊 총 조항: {total_sections}개")
        logger.info(f"✅ 성공: {successful_reviews}개 ({successful_reviews/total_sections*100:.1f}%)")
        logger.info(f"❌ 실패: {failed_reviews}개")
        logger.info(f"⏱️ 평균 검토 시간: {avg_review_time:.1f}ms")
        logger.info(f"📖 평균 법령 참조: {avg_legal_refs:.1f}개")
        logger.info(f"🎯 토큰 사용량:")
        logger.info(f"   - 총 입력: {total_input_tokens:,} (평균: {avg_input_tokens:.1f})")
        logger.info(f"   - 총 출력: {total_output_tokens:,} (평균: {avg_output_tokens:.1f})")
        logger.info(f"   - 총 사용: {total_tokens:,} (평균: {avg_total_tokens:.1f})")
        logger.info(f"📏 최적화 효과:")
        logger.info(f"   - 평균 프롬프트 크기: {avg_prompt_size:,.0f}자")
        logger.info(f"   - 평균 관련 조항 수: {avg_related_sections:.1f}개")
        logger.info(f"   - 의미적 검색 성공: {semantic_count}개")
        logger.info(f"   - 슬라이딩 윈도우 대체: {fallback_count}개")
        
        # 성공한 검토 결과 미리보기
        if successful_reviews > 0:
            logger.info(f"\n📋 검토 결과 미리보기:")
            for result in review_results:
                if result.get("success"):
                    analysis = result.get("review_analysis", "")
                    # 위험도 추출 시도
                    risk_level = "분석 중"
                    if "위험도:" in analysis:
                        risk_line = [line for line in analysis.split('\n') if '위험도:' in line]
                        if risk_line:
                            risk_level = risk_line[0].split('위험도:')[-1].strip()
                    
                    logger.info(f"  - {result['section_title']}: 위험도 {risk_level}")
        
        logger.info(f"\n💾 상세 결과 저장: {results_file}")
    
    async def step2_test_search(self):
        """Step 2: 검색 테스트"""
        logger.info("🔍 Step 2: 검색 테스트 시작")
        
        # 테스트 쿼리 정의
        test_queries = [
            # 법령 관련 쿼리
            {
                "query": "개인정보보호법의 주요 내용은?",
                "category": "law",
                "expected_doc_type": "law"
            },
            {
                "query": "전자상거래 소비자보호에 관한 법률",
                "category": "law", 
                "expected_doc_type": "law"
            },
            # 계약서 관련 쿼리
            {
                "query": "계약해지 조건과 절차",
                "category": "contract",
                "expected_doc_type": ["executed_contract", "standard_contract"]
            },
            {
                "query": "손해배상 책임 범위",
                "category": "contract",
                "expected_doc_type": ["executed_contract", "standard_contract"]
            },
            {
                "query": "계약 기간 및 갱신 조건",
                "category": "contract", 
                "expected_doc_type": ["executed_contract", "standard_contract"]
            },
            # 일반적인 질문
            {
                "query": "계약서 작성 시 주의사항",
                "category": "general",
                "expected_doc_type": "any"
            }
        ]
        
        search_results = []
        
        # 각 쿼리에 대해 검색 수행
        for i, test_case in enumerate(test_queries, 1):
            logger.info(f"🔍 검색 테스트 {i}/{len(test_queries)}: {test_case['query']}")
            
            try:
                # 직접 검색 호출
                start_time = time.time()
                result = await self.client.search_documents_direct(
                    query=test_case["query"],
                    top_k=5,
                    doc_types=None  # 모든 문서 타입에서 검색
                )
                search_time = time.time() - start_time
                
                # 결과 분석
                search_result = {
                    "query": test_case["query"],
                    "category": test_case["category"],
                    "expected_doc_type": test_case["expected_doc_type"],
                    "search_time": search_time,
                    "total_results": len(result.get("results", [])),
                    "results": result.get("results", []),
                    "success": True
                }
                
                # 결과 품질 평가
                if result.get("results"):
                    # 문서 타입 분포 확인
                    doc_types = [r.get("doc_type") for r in result["results"]]
                    search_result["doc_type_distribution"] = {
                        doc_type: doc_types.count(doc_type) 
                        for doc_type in set(doc_types) if doc_type
                    }
                    
                    # 평균 점수 계산
                    scores = [r.get("similarity_score", 0) for r in result["results"]]
                    search_result["avg_similarity_score"] = sum(scores) / len(scores) if scores else 0
                    search_result["max_similarity_score"] = max(scores) if scores else 0
                    search_result["min_similarity_score"] = min(scores) if scores else 0
                
                logger.info(f"  ✅ 검색 완료: {search_result['total_results']}개 결과, {search_time:.2f}초")
                if search_result.get("doc_type_distribution"):
                    for doc_type, count in search_result["doc_type_distribution"].items():
                        logger.info(f"    - {doc_type}: {count}개")
                
            except Exception as e:
                logger.error(f"  ❌ 검색 실패: {str(e)}")
                search_result = {
                    "query": test_case["query"],
                    "category": test_case["category"],
                    "expected_doc_type": test_case["expected_doc_type"],
                    "error": str(e),
                    "success": False
                }
            
            search_results.append(search_result)
            
            # 요청 간 잠시 대기
            await asyncio.sleep(0.5)
        
        # 결과 요약 및 저장
        await self._save_search_test_results(search_results)
        
        logger.info("🎉 Step 2 검색 테스트 완료!")
        return True
    
    async def step3_contract_review_test(self):
        """Step 3: 계약서 검토 기능 테스트 (3단계 체인 방식)"""
        logger.info("📝 Step 3: 계약서 검토 기능 테스트 시작 (체인 방식)")
        
        # 1. 테스트 대상 문서 선택
        test_document_path = DOCS_ROOT / "1. NDA" / "초안_비밀유지계약서.docx"
        
        if not test_document_path.exists():
            logger.error(f"❌ 테스트 문서가 없습니다: {test_document_path}")
            return False
        
        logger.info(f"📄 테스트 문서: {test_document_path.name}")
        
        # 2. 계약서를 DB에 저장 (중복 체크 포함)
        logger.info("💾 계약서 DB 저장 확인/처리 중...")
        document_id = await self._ensure_contract_in_db(test_document_path)
        
        if not document_id:
            logger.error("❌ 계약서 DB 저장 실패")
            return False
        
        logger.info(f"✅ 계약서 DB 저장 완료 (Document ID: {document_id})")
        
        # 3. DB에서 계약서 정보 조회
        document_info = await self._get_document_from_db(document_id)
        if not document_info:
            logger.error("❌ DB에서 계약서 정보 조회 실패")
            return False
        
        # 4. 계약서 조항 조회
        chunks = await self._get_document_chunks_from_db(document_id)
        parent_chunks = [c for c in chunks if c.get("chunk_type") == "parent"]
        
        logger.info(f"🔍 DB에서 조회한 청크 수: {len(chunks)}")
        logger.info(f"🔍 Parent 청크 수: {len(parent_chunks)}")
        
        if not parent_chunks:
            logger.error("❌ 분석할 조항을 생성할 수 없습니다.")
            return False
        
        logger.info(f"📊 총 {len(parent_chunks)}개 조항 발견")
        
        try:
            # === 3단계 체인 분석 시작 ===
            
            # Chain 1: 전체 계약서 스캔 → 위법 조항 식별
            logger.info("🔍 Chain 1: 전체 계약서 위법 조항 식별 중...")
            start_time = time.time()
            
            violation_candidates = await self._chain1_identify_violations(
                document_name=test_document_path.name,
                all_chunks=parent_chunks,
                document_id=document_id
            )
            
            chain1_time = time.time() - start_time
            logger.info(f"✅ Chain 1 완료: {len(violation_candidates)}개 위법 조항 후보 발견 ({chain1_time:.2f}초)")
            
            if not violation_candidates:
                logger.info("✅ 위법 조항이 발견되지 않았습니다.")
                await self._save_chain_analysis_results(test_document_path.name, {"violations": []}, {
                    "chain1_time": chain1_time,
                    "chain2_time": 0,
                    "chain3_time": 0,
                    "total_time": chain1_time,
                    "violations_found": 0,
                    "total_clauses": len(parent_chunks)
                })
                return True
            
            # Chain 2: 각 위법 조항별 관련 법령 검색 (병렬 처리)
            logger.info("🔍 Chain 2: 위법 조항별 관련 법령 검색 중...")
            start_time = time.time()
            
            violations_with_laws = await self._chain2_search_related_laws(violation_candidates)
            
            chain2_time = time.time() - start_time
            logger.info(f"✅ Chain 2 완료: {len(violations_with_laws)}개 조항의 법령 검색 완료 ({chain2_time:.2f}초)")
            
            # Chain 3: 최종 상세 분석
            logger.info("🔍 Chain 3: 최종 상세 분석 중...")
            start_time = time.time()
            
            final_analysis = await self._chain3_detailed_analysis(
                violations_with_laws=violations_with_laws,
                document_name=test_document_path.name
            )
            
            chain3_time = time.time() - start_time
            logger.info(f"✅ Chain 3 완료: 최종 분석 완료 ({chain3_time:.2f}초)")
            
            # 결과 저장
            await self._save_chain_analysis_results(test_document_path.name, final_analysis, {
                "chain1_time": chain1_time,
                "chain2_time": chain2_time, 
                "chain3_time": chain3_time,
                "total_time": chain1_time + chain2_time + chain3_time,
                "violations_found": len(final_analysis.get("violations", [])),
                "total_clauses": len(parent_chunks)
            })
            
            logger.info("🎉 Step 3 계약서 검토 테스트 완료 (체인 방식)!")
            return True
            
        except Exception as e:
            logger.error(f"❌ 체인 분석 실패: {str(e)}")
            return False
    
    async def step4_streamlit_visualization(self):
        """Step 4: Streamlit 결과 시각화"""
        logger.info("📈 Step 4: Streamlit 결과 시각화 시작")
        # TODO: Streamlit 시각화 구현
        pass
    
    async def _split_contract_into_sections(self, markdown_content: str) -> List[Dict]:
        """계약서를 조항별로 분할"""
        try:
            logger.info(f"📄 계약서 분할 시작 (총 {len(markdown_content)} 문자)")
            
            # 마크다운 내용 미리보기
            preview_lines = markdown_content.split('\n')[:10]
            logger.info("📋 마크다운 내용 미리보기:")
            for i, line in enumerate(preview_lines, 1):
                if line.strip():
                    logger.info(f"  {i:2d}: {line[:80]}{'...' if len(line) > 80 else ''}")
            
            sections = []
            
            # 방법 1: 헤딩(#, ##) 및 조항 패턴으로 분할
            lines = markdown_content.split('\n')
            current_section = {"header_1": "서문", "content": ""}
            section_count = 0
            
            import re
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # 헤딩 또는 조항 패턴 발견 시 새로운 섹션 시작
                is_new_section = False
                header_text = ""
                
                if line.startswith('#'):
                    # 마크다운 헤딩
                    is_new_section = True
                    header_text = line.lstrip('#').strip()
                elif re.match(r'^제\s*\d+\s*조', line):
                    # "제X조" 또는 "제 X 조" 패턴 (괄호 없이도 인식)
                    is_new_section = True
                    header_text = line
                elif line.startswith('Article') or line.startswith('ARTICLE'):
                    # 영문 조항
                    is_new_section = True
                    header_text = line
                elif any(line.startswith(pattern) for pattern in ['1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.']):
                    # 번호 매긴 조항 (1., 2., 3. 등)
                    if len(line) > 10 and not current_section["content"]:  # 너무 짧지 않고 새 섹션일 때만
                        is_new_section = True
                        header_text = line
                
                if is_new_section:
                    # 이전 섹션 저장
                    if current_section["content"].strip():
                        current_section["chunk_type"] = "parent"
                        sections.append(current_section)
                        section_count += 1
                    
                    # 새 섹션 시작 - 원본 조항 번호 보존
                    current_section = {
                        "header_1": header_text,  # 원본 조항 번호 그대로 사용
                        "content": "",
                        "chunk_type": "parent"
                    }
                else:
                    # 내용 추가
                    if current_section["content"]:
                        current_section["content"] += "\n"
                    current_section["content"] += line
            
            # 마지막 섹션 저장
            if current_section["content"].strip():
                sections.append(current_section)
                section_count += 1
            
            # 헤딩이 없으면 문단 기준으로 분할
            if not sections:
                logger.info("📄 헤딩이 없어 문단 기준으로 분할합니다.")
                paragraphs = [p.strip() for p in markdown_content.split('\n\n') if p.strip()]
                
                for i, paragraph in enumerate(paragraphs[:10], 1):  # 최대 10개 문단
                    if len(paragraph) > 50:  # 너무 짧은 문단 제외
                        sections.append({
                            "header_1": f"조항 {i}",
                            "content": paragraph,
                            "chunk_type": "parent"
                        })
            
            logger.info(f"✅ {len(sections)}개 조항으로 분할 완료")
            
            # 각 섹션 미리보기
            for i, section in enumerate(sections[:3], 1):
                preview = section["content"][:100] + "..." if len(section["content"]) > 100 else section["content"]
                logger.info(f"  {i}. {section['header_1']}: {preview}")
                
            return sections
            
        except Exception as e:
            logger.error(f"❌ 계약서 분할 실패: {str(e)}")
            return []


async def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(description="Smart CLM RAG 파이프라인")
    parser.add_argument(
        "--step", 
        type=int, 
        choices=[1, 2, 3, 4], 
        default=1,
        help="실행할 단계 (1: 근거자료 저장, 2: 검색 테스트, 3: 계약서 검토 테스트, 4: Streamlit 시각화)"
    )
    parser.add_argument(
        "--force", 
        action="store_true",
        help="이미 처리된 파일도 강제로 다시 처리"
    )
    
    args = parser.parse_args()
    
    pipeline = RAGPipeline()
    
    try:
        if args.step == 1:
            success = await pipeline.step1_store_reference_materials(force=args.force)
            if success:
                logger.info("🎉 Step 1 완료!")
            else:
                logger.error("❌ Step 1 실패!")
                sys.exit(1)
        
        elif args.step == 2:
            await pipeline.step2_test_search()
        
        elif args.step == 3:
            await pipeline.step3_contract_review_test()
        
        elif args.step == 4:
            await pipeline.step4_streamlit_visualization()
    
    except KeyboardInterrupt:
        logger.info("⏹️ 사용자에 의해 중단되었습니다.")
        sys.exit(0)
    
    except Exception as e:
        logger.error(f"💥 예기치 않은 오류: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 