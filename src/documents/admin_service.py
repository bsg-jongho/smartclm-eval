"""
📚 어드민 전용 문서 관리 서비스

시스템 RAG용 문서들(법령, 가이드라인, 표준계약서, 판례)을 관리합니다.
"""

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import HTTPException, UploadFile
from sqlmodel.ext.asyncio.session import AsyncSession

from src.documents.base_service import BaseDocumentService
from src.documents.schema import AdminDocumentUploadRequest, DocumentUploadResponse


class AdminDocumentService(BaseDocumentService):
    """어드민 전용 문서 관리 서비스 (BaseDocumentService 상속)"""

    async def upload_system_document(
        self,
        file: UploadFile,
        request: AdminDocumentUploadRequest,
        user_id: int,
        session: AsyncSession,
    ) -> DocumentUploadResponse:
        """시스템 RAG용 문서 업로드 (어드민 전용)"""

        # 공통 업로드 로직 사용
        result = await self._upload_document_common(
            file=file,
            doc_type=request.doc_type,
            room_id=None,  # 전역 문서
            user_id=user_id,
            session=session,
            is_admin=True,  # 어드민 업로드
        )

        created_document = result["document"]
        title = result["title"]
        version = result["version"]

        return DocumentUploadResponse(
            document_id=created_document.id or 0,
            title=title,
            filename=created_document.filename,
            doc_type=request.doc_type,
            room_id=None,  # 전역 문서
            version=version,  # 버전 없음
            processing_status="completed",
            created_at=created_document.created_at or datetime.now(),
        )

    async def list_global_documents(
        self,
        doc_type: Optional[str] = None,
        category: Optional[str] = None,
        processing_status: Optional[str] = None,
        session: AsyncSession = None,
    ) -> List[Dict]:
        """전역 문서 목록 조회 (어드민 전용)"""
        try:
            print(
                f"🔍 전역 문서 목록 조회 시작: doc_type={doc_type}, category={category}, processing_status={processing_status}"
            )

            documents = await self.repository.get_global_documents(
                doc_type=doc_type,
                category=category,
                processing_status=processing_status,
                session=session,
            )

            print(f"📄 조회된 문서 수: {len(documents)}")

            result = []
            for doc in documents:
                metadata = doc.document_metadata or {}
                filename = doc.filename or "unknown.pdf"
                result.append(
                    {
                        "id": doc.id,
                        "title": metadata.get("title", filename),
                        "filename": filename,
                        "doc_type": doc.doc_type,
                        "category": doc.category,
                        "room_id": doc.room_id,  # None (전역 문서)
                        "file_size": doc.file_size,
                        "pdf_file_size": doc.pdf_file_size,
                        "page_count": doc.page_count,
                        "processing_status": doc.processing_status,
                        "created_at": doc.created_at,
                        "document_metadata": metadata,
                        "auto_tags": doc.auto_tags or [],
                        "version": doc.version or "",
                    }
                )

            print(f"✅ 전역 문서 목록 조회 완료: {len(result)}개")
            return result

        except Exception as e:
            print(f"❌ 전역 문서 목록 조회 실패: {str(e)}")
            import traceback

            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"전역 문서 목록 조회 중 오류가 발생했습니다: {str(e)}",
            )


# 서비스 인스턴스
admin_document_service = AdminDocumentService()
