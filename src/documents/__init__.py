"""
📄 통합 문서 관리 서비스

기존 legal과 contracts 서비스를 새로운 Document, Chunk 모델로 통합
- Document: 모든 문서 (계약서, 법령, 참고자료 등)
- Chunk: 문서 청크 (RAG/AI 검색용)
"""

from .repository import DocumentRepository
from .service import DocumentService

__all__ = ["DocumentService", "DocumentRepository"]
