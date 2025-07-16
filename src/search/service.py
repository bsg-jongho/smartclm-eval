"""
🔍 검색 서비스

문서 검색 및 RAG 기능을 제공하는 서비스입니다.
"""

import time

from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from src.aws.embedding_service import TitanEmbeddingService
from src.documents.repository import DocumentRepository

from .schema import (
    DocumentSearchRequest,
    DocumentSearchResponse,
    SearchResult,
)


class SearchService:
    """검색 서비스"""

    def __init__(self):
        self.embedding_service = TitanEmbeddingService()
        self.repository = DocumentRepository()

    async def search_documents(
        self, request: DocumentSearchRequest, session: AsyncSession
    ) -> DocumentSearchResponse:
        """기본 문서 검색 (시스템 RAG용)"""
        start_time = time.time()

        try:
            # 1. 검색 쿼리 임베딩 생성
            query_embedding = await self.embedding_service.create_single_embedding(
                request.query
            )

            # 2. 벡터 검색 (시스템 RAG용 문서만)
            search_results = await self.repository.search_documents_by_vector(
                query_embedding=query_embedding,
                session=session,
                doc_types=request.doc_types,
                top_k=request.top_k,
            )

            # 3. 결과 변환
            results = []
            for result in search_results:
                # Parent context 조회
                parent_context = None
                if result.get("parent_id") and result.get("chunk_type") == "child":
                    parent_data = await self.repository.get_parent_chunk_content(
                        result["parent_id"], session
                    )
                    if parent_data:
                        parent_context = parent_data["content"]

                # # 유사도 하한선 적용 (예: 0.7)
                # if result["similarity_score"] < 0.7:
                #     continue

                results.append(
                    SearchResult(
                        document_id=result["document_id"],
                        title=result["filename"],
                        doc_type=result["doc_type"],
                        category=result["category"],
                        content=result["content"],
                        similarity_score=result["similarity_score"],
                        chunk_id=result["chunk_id"],
                        parent_context=parent_context,
                    )
                )

            search_time = (time.time() - start_time) * 1000

            return DocumentSearchResponse(
                query=request.query,
                results=results,
                total_found=len(results),
                search_time_ms=round(search_time, 2),
            )

        except Exception as e:
            print(f"❌ 문서 검색 실패: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"문서 검색 중 오류가 발생했습니다: {str(e)}"
            )


# 서비스 인스턴스
search_service = SearchService()
