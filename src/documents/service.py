"""
📄 통합 문서 관리 서비스

기존 legal과 contracts 서비스를 새로운 Document 모델에 맞게 통합
"""

from datetime import datetime

from fastapi import UploadFile
from sqlmodel.ext.asyncio.session import AsyncSession

from src.documents.base_service import BaseDocumentService
from src.documents.repository import DocumentRepository
from src.documents.schema import (
    DocumentComparisonResponse,
    DocumentHtmlContent,
    DocumentInfo,
    DocumentUploadRequest,
    DocumentUploadResponse,
    DocumentWithOutlineResponse,
    OutlineSection,
)


class DocumentService(BaseDocumentService):
    """사용자 문서 업로드 서비스 (BaseDocumentService 상속)"""

    async def upload_document(
        self,
        file: UploadFile,
        request: DocumentUploadRequest,
        user_id: int,
        session: AsyncSession,
    ) -> DocumentUploadResponse:
        """문서 업로드 및 처리 (사용자용)"""

        # 공통 업로드 로직 사용
        result = await self._upload_document_common(
            file=file,
            doc_type=request.doc_type,
            room_id=request.room_id,
            user_id=user_id,
            session=session,
            is_admin=False,  # 사용자 업로드
        )

        created_document = result["document"]
        title = result["title"]
        version = result["version"]
        review_analysis = result["review_analysis"]

        # 응답 데이터 구성
        response_data = {
            "document_id": created_document.id or 0,
            "title": title or "제목 없음",
            "filename": created_document.filename or "unknown.pdf",
            "doc_type": request.doc_type,
            "room_id": request.room_id,
            "version": version,
            "processing_status": "completed",
            "created_at": created_document.created_at
            if created_document.created_at
            else datetime.now(),
        }

        # 계약서인 경우 검토 분석 결과 추가
        if request.doc_type == "contract" and review_analysis:
            from src.documents.schema import ContractReviewAnalysis, ToxicClauseInfo

            try:
                # toxic_clauses 배열을 ToxicClauseInfo 객체들로 변환
                if (
                    "toxic_clauses" in review_analysis
                    and review_analysis["toxic_clauses"]
                ):
                    toxic_clauses = []
                    for clause in review_analysis["toxic_clauses"]:
                        toxic_clauses.append(ToxicClauseInfo(**clause))
                    review_analysis["toxic_clauses"] = toxic_clauses

                # 딕셔너리를 ContractReviewAnalysis 객체로 변환
                response_data["review_analysis"] = ContractReviewAnalysis(
                    **review_analysis
                )
            except Exception as e:
                print(f"⚠️ review_analysis 스키마 변환 실패: {str(e)}")
                # 변환 실패 시 None으로 설정
                response_data["review_analysis"] = None

        return DocumentUploadResponse(**response_data)

    async def get_document_with_outline(
        self, document_id: int, session: AsyncSession
    ) -> DocumentWithOutlineResponse:
        """문서 상세 + outline(조항/청크 메타데이터) 반환"""
        repo = DocumentRepository()
        document = await repo.get_document_by_id(document_id, session)
        if not document:
            raise ValueError("문서를 찾을 수 없습니다.")
        # 문서 정보
        doc_info = DocumentInfo.from_orm(document)
        # outline: parent 청크만 추출
        chunks = await repo.get_chunks_by_document(document_id, session)
        outline_sections = []
        for chunk in chunks:
            if getattr(chunk, "chunk_type", None) == "parent":
                outline_sections.append(
                    OutlineSection(
                        section_id=chunk.parent_id or str(chunk.id),
                        title=chunk.header_1 or "",
                        chunk_index=chunk.chunk_index,
                        preview=chunk.content[:200],
                        page_index=None,  # 필요시 메타데이터에서 추출
                        bbox=None,  # 필요시 메타데이터에서 추출
                        dest=chunk.parent_id,
                        type=None,  # 필요시 메타데이터에서 추출
                        items=[],  # 확장 가능
                    )
                )
        return DocumentWithOutlineResponse(document=doc_info, outline=outline_sections)

    async def get_section_with_neighbors_context(
        self,
        document_id: int,
        section_id: str,
        session: AsyncSession,
        neighbor_count: int = 1,
    ) -> dict:
        """
        선택한 조항(Parent 청크) + 앞뒤 조항(Neighbor) context 반환
        - neighbor_count: 앞뒤로 몇 개의 조항을 포함할지 (기본 1)
        """
        repo = DocumentRepository()
        chunks = await repo.get_chunks_by_document(document_id, session)
        # Parent 청크만 추출
        parent_chunks = [
            c for c in chunks if getattr(c, "chunk_type", None) == "parent"
        ]
        # 인덱스 매핑
        section_idx = None
        for idx, chunk in enumerate(parent_chunks):
            if (chunk.parent_id and chunk.parent_id == section_id) or str(
                chunk.id
            ) == section_id:
                section_idx = idx
                break
        if section_idx is None:
            raise ValueError("해당 section_id의 조항을 찾을 수 없습니다.")
        # 앞뒤 neighbor 조항 포함
        start = max(0, section_idx - neighbor_count)
        end = min(len(parent_chunks), section_idx + neighbor_count + 1)
        context_chunks = parent_chunks[start:end]
        context_text = "\n\n".join(
            f"[{c.header_1}]\n{c.content}" for c in context_chunks
        )
        return {
            "context_text": context_text,
            "sections": [
                {
                    "section_id": c.parent_id or str(c.id),
                    "title": c.header_1 or "",
                    "content": c.content,
                }
                for c in context_chunks
            ],
            "main_section_id": section_id,
            "main_section_title": parent_chunks[section_idx].header_1 or "",
        }

    async def get_documents_for_comparison(
        self, document_id_1: int, document_id_2: int, session: AsyncSession
    ) -> DocumentComparisonResponse:
        """두 문서의 HTML 콘텐츠를 가져와서 비교용으로 반환"""
        repo = DocumentRepository()

        # 첫 번째 문서 조회
        doc1 = await repo.get_document_by_id(document_id_1, session)
        doc1_content = DocumentHtmlContent(
            document_id=document_id_1,
            title=doc1.filename if doc1 else "문서를 찾을 수 없습니다",
            filename=doc1.filename if doc1 else "",
            html_content=doc1.html_content if doc1 else None,
            error="문서를 찾을 수 없습니다" if not doc1 else None,
        )

        # 두 번째 문서 조회
        doc2 = await repo.get_document_by_id(document_id_2, session)
        doc2_content = DocumentHtmlContent(
            document_id=document_id_2,
            title=doc2.filename if doc2 else "문서를 찾을 수 없습니다",
            filename=doc2.filename if doc2 else "",
            html_content=doc2.html_content if doc2 else None,
            error="문서를 찾을 수 없습니다" if not doc2 else None,
        )

        return DocumentComparisonResponse(
            document_1=doc1_content,
            document_2=doc2_content,
        )


# 서비스 인스턴스
document_service = DocumentService()
