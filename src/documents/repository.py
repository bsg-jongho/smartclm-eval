"""
📄 통합 문서 관리 리포지토리

기존 legal과 contracts 리포지토리를 새로운 Document, Chunk 모델로 통합
"""

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.query_utils import (
    create_soft_delete_query,
    create_soft_delete_query_with_conditions,
)
from src.models import Chunk, Document


class DocumentRepository:
    """
    통합 문서 관리 리포지토리
    """

    # ═══════════════════════════════════════════════════════════════════════════════
    # 📚 Document CRUD
    # ═══════════════════════════════════════════════════════════════════════════════

    async def create_document(
        self, document: Document, session: AsyncSession
    ) -> Document:
        """문서 생성"""
        session.add(document)
        await session.commit()
        await session.refresh(document)
        return document

    async def get_document_by_id(
        self, document_id: int, session: AsyncSession, include_deleted: bool = False
    ) -> Optional[Document]:
        """ID로 문서 조회"""
        query = create_soft_delete_query_with_conditions(
            Document, include_deleted_records=include_deleted, id=document_id
        )
        result = await session.exec(query)
        return result.first()

    async def get_documents_by_room(
        self, room_id: int, session: AsyncSession, include_deleted: bool = False
    ) -> List[Document]:
        """방별 문서 목록 조회"""
        query = create_soft_delete_query_with_conditions(
            Document, include_deleted_records=include_deleted, room_id=room_id
        ).order_by(desc(Document.created_at))
        result = await session.exec(query)
        return list(result.all())

    async def get_document_by_filename_and_room(
        self,
        filename: str,
        room_id: int,
        session: AsyncSession,
        include_deleted: bool = False,
    ) -> Optional[Document]:
        """같은 방에서 같은 파일명의 최신 문서 조회"""
        base_query = create_soft_delete_query(
            Document, include_deleted_records=include_deleted
        )
        query = base_query.where(
            Document.filename == filename, Document.room_id == room_id
        ).order_by(desc(Document.created_at))
        result = await session.exec(query)
        return result.first()

    async def get_latest_contract_in_room(
        self, room_id: int, session: AsyncSession, include_deleted: bool = False
    ) -> Optional[Document]:
        """해당 방에서 가장 최신 계약서 조회 (버전 관리용)"""
        base_query = create_soft_delete_query(
            Document, include_deleted_records=include_deleted
        )
        query = base_query.where(
            Document.room_id == room_id, Document.doc_type == "contract"
        ).order_by(desc(Document.created_at))
        result = await session.exec(query)
        return result.first()

    async def get_global_documents(
        self,
        doc_type: Optional[str] = None,
        category: Optional[str] = None,
        processing_status: Optional[str] = None,
        session: AsyncSession = None,
        include_deleted: bool = False,
    ) -> List[Document]:
        """전역 문서 목록 조회 (room_id = NULL)"""
        base_query = create_soft_delete_query(
            Document, include_deleted_records=include_deleted
        )
        query = base_query.where(Document.room_id == None)

        if doc_type:
            query = query.where(Document.doc_type == doc_type)
        if category:
            query = query.where(Document.category == category)
        if processing_status:
            query = query.where(Document.processing_status == processing_status)

        query = query.order_by(desc(Document.created_at))
        result = await session.exec(query)
        documents = list(result.all())
        return documents

    async def get_documents_by_type(
        self, doc_type: str, session: AsyncSession, include_deleted: bool = False
    ) -> List[Document]:
        """문서 유형별 조회"""
        base_query = create_soft_delete_query(
            Document, include_deleted_records=include_deleted
        )
        query = base_query.where(
            text("document_metadata->>'type' = :doc_type")
        ).order_by(desc(Document.created_at))
        result = await session.exec(query, {"doc_type": doc_type})
        return list(result.all())

    async def update_document(
        self, document: Document, session: AsyncSession
    ) -> Document:
        """문서 업데이트"""
        session.add(document)
        await session.commit()
        await session.refresh(document)
        return document

    async def soft_delete_document(
        self, document_id: int, session: AsyncSession
    ) -> bool:
        """문서 Soft Delete"""
        document = await self.get_document_by_id(document_id, session)
        if document:
            document.soft_delete()
            await session.commit()
            return True
        return False

    async def restore_document(self, document_id: int, session: AsyncSession) -> bool:
        """삭제된 문서 복구"""
        document = await self.get_document_by_id(
            document_id, session, include_deleted=True
        )
        if document and document.is_deleted:
            document.restore()
            await session.commit()
            return True
        return False

    async def hard_delete_document(
        self, document_id: int, session: AsyncSession
    ) -> bool:
        """문서 Hard Delete (영구 삭제)"""
        document = await self.get_document_by_id(
            document_id, session, include_deleted=True
        )
        if document:
            await session.delete(document)
            await session.commit()
            return True
        return False

    async def get_deleted_documents(
        self, room_id: Optional[int] = None, session: AsyncSession = None
    ) -> List[Document]:
        """삭제된 문서 목록 조회"""
        base_query = create_soft_delete_query(Document, include_deleted_records=True)
        query = base_query.where(Document.deleted_at != None)

        if room_id is not None:
            query = query.where(Document.room_id == room_id)

        query = query.order_by(desc(Document.deleted_at))
        result = await session.exec(query)
        return list(result.all())

    # ═══════════════════════════════════════════════════════════════════════════════
    # 🔍 Chunk CRUD
    # ═══════════════════════════════════════════════════════════════════════════════

    async def create_chunks(
        self, chunks: List[Chunk], session: AsyncSession
    ) -> List[Chunk]:
        """청크 일괄 생성"""
        session.add_all(chunks)
        await session.commit()
        for chunk in chunks:
            await session.refresh(chunk)
        return chunks

    async def get_chunks_by_document(
        self, document_id: int, session: AsyncSession
    ) -> List[Chunk]:
        """문서별 청크 조회"""
        query = (
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index)
        )
        result = await session.exec(query)
        return list(result.all())

    # ═══════════════════════════════════════════════════════════════════════════════
    # 🔍 벡터 검색
    # ═══════════════════════════════════════════════════════════════════════════════

    async def search_documents_by_vector(
        self,
        query_embedding: List[float],
        session: AsyncSession,
        doc_types: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """벡터 기반 문서 검색 (시스템 RAG용)"""

        # 기본 쿼리 구성 - 전역 문서만 검색
        base_query = """
        SELECT 
            c.id as chunk_id,
            c.content,
            c.chunk_type,
            c.parent_id,
            c.child_id,
            c.header_1,
            c.header_2,
            c.header_3,
            c.header_4,
            d.id as document_id,
            d.filename,
            d.doc_type,
            d.category,
            d.auto_tags,
            (1 - (c.embedding <=> :query_embedding)) as similarity_score
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.embedding IS NOT NULL
        AND d.room_id IS NULL 
        """

        # 벡터를 pgvector 형식 문자열로 변환
        vector_str = "[" + ",".join(map(str, query_embedding)) + "]"
        params: Dict[str, Any] = {"query_embedding": vector_str}

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

        # 쿼리 실행
        connection = await session.connection()
        result = await connection.execute(text(base_query), params)
        rows = result.fetchall()

        # 결과 변환
        search_results = []
        for row in rows:
            search_results.append(
                {
                    "chunk_id": row.chunk_id,
                    "content": row.content,
                    "similarity_score": round(row.similarity_score, 4),
                    "chunk_type": row.chunk_type,
                    "parent_id": row.parent_id,
                    "child_id": row.child_id,
                    "headers": {
                        "header_1": row.header_1,
                        "header_2": row.header_2,
                        "header_3": row.header_3,
                        "header_4": row.header_4,
                    },
                    "document_id": row.document_id,
                    "filename": row.filename,
                    "doc_type": row.doc_type,
                    "category": row.category,
                    "auto_tags": row.auto_tags or [],
                }
            )

        return search_results

    async def get_parent_chunk_content(
        self, parent_id: str, session: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """Parent 청크 내용 조회"""
        try:
            parent_query = """
            SELECT content, header_1, header_2, header_3, header_4
            FROM chunks 
            WHERE chunk_type = 'parent' 
            AND parent_id = :parent_id
            LIMIT 1
            """
            connection = await session.connection()
            result = await connection.execute(
                text(parent_query), {"parent_id": parent_id}
            )
            row = result.fetchone()

            if row:
                return {
                    "content": row.content,
                    "headers": {
                        "header_1": row.header_1,
                        "header_2": row.header_2,
                        "header_3": row.header_3,
                        "header_4": row.header_4,
                    },
                }
            return None
        except Exception:
            return None

    async def search_documents_by_vector_advanced(
        self,
        query_embedding: List[float],
        session: AsyncSession,
        doc_types: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """고급 벡터 기반 문서 검색 (추가 필터링)"""

        # 기본 쿼리 구성 - 전역 문서만 검색
        base_query = """
        SELECT 
            c.id as chunk_id,
            c.content,
            c.chunk_type,
            c.parent_id,
            c.child_id,
            c.header_1,
            c.header_2,
            c.header_3,
            c.header_4,
            d.id as document_id,
            d.filename,
            d.doc_type,
            d.category,
            d.auto_tags,
            (1 - (c.embedding <=> :query_embedding)) as similarity_score
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.embedding IS NOT NULL
        AND d.room_id IS NULL  
        """

        # 벡터를 pgvector 형식 문자열로 변환
        vector_str = "[" + ",".join(map(str, query_embedding)) + "]"
        params: Dict[str, Any] = {"query_embedding": vector_str}

        # 문서 유형 필터
        if doc_types:
            type_conditions = []
            for i, doc_type in enumerate(doc_types):
                param_name = f"doc_type_{i}"
                type_conditions.append(f"d.doc_type = :{param_name}")
                params[param_name] = doc_type
            base_query += f" AND ({' OR '.join(type_conditions)})"

        # 카테고리 필터
        if categories:
            category_conditions = []
            for i, category in enumerate(categories):
                param_name = f"category_{i}"
                category_conditions.append(f"d.category = :{param_name}")
                params[param_name] = category
            base_query += f" AND ({' OR '.join(category_conditions)})"

        # 태그 필터
        if tags:
            tag_conditions = []
            for i, tag in enumerate(tags):
                param_name = f"tag_{i}"
                tag_conditions.append(f":{param_name} = ANY(d.auto_tags)")
                params[param_name] = tag
            base_query += f" AND ({' OR '.join(tag_conditions)})"

        # 유사도 정렬 및 제한
        base_query += " ORDER BY similarity_score DESC LIMIT :top_k"
        params["top_k"] = top_k

        # 쿼리 실행
        connection = await session.connection()
        result = await connection.execute(text(base_query), params)
        rows = result.fetchall()

        # 결과 변환
        search_results = []
        for row in rows:
            search_results.append(
                {
                    "chunk_id": row.chunk_id,
                    "content": row.content,
                    "similarity_score": round(row.similarity_score, 4),
                    "chunk_type": row.chunk_type,
                    "parent_id": row.parent_id,
                    "child_id": row.child_id,
                    "headers": {
                        "header_1": row.header_1,
                        "header_2": row.header_2,
                        "header_3": row.header_3,
                        "header_4": row.header_4,
                    },
                    "document_id": row.document_id,
                    "filename": row.filename,
                    "doc_type": row.doc_type,
                    "category": row.category,
                    "auto_tags": row.auto_tags or [],
                }
            )

        return search_results

    async def search_documents_by_vector_with_room_context(
        self,
        query_embedding: List[float],
        session: AsyncSession,
        room_id: Optional[int] = None,
        doc_types: Optional[List[str]] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """방별 컨텍스트를 포함한 벡터 기반 문서 검색 (하이브리드 RAG용)"""

        # 방별 문서와 시스템 문서를 모두 검색
        base_query = """
        SELECT 
            c.id as chunk_id,
            c.content,
            c.chunk_type,
            c.parent_id,
            c.child_id,
            c.header_1,
            c.header_2,
            c.header_3,
            c.header_4,
            d.id as document_id,
            d.filename,
            d.doc_type,
            d.category,
            d.auto_tags,
            d.room_id,
            (1 - (c.embedding <=> :query_embedding)) as similarity_score
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.embedding IS NOT NULL
        """

        # 벡터를 pgvector 형식 문자열로 변환
        vector_str = "[" + ",".join(map(str, query_embedding)) + "]"
        params: Dict[str, Any] = {"query_embedding": vector_str}

        # 방별 필터링
        if room_id is not None:
            # 특정 방의 문서 + 시스템 문서
            base_query += " AND (d.room_id = :room_id OR d.room_id IS NULL)"
            params["room_id"] = room_id
        else:
            # 시스템 문서만
            base_query += " AND d.room_id IS NULL"

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

        # 쿼리 실행
        connection = await session.connection()
        result = await connection.execute(text(base_query), params)
        rows = result.fetchall()

        # 결과 변환
        search_results = []
        for row in rows:
            search_results.append(
                {
                    "chunk_id": row.chunk_id,
                    "content": row.content,
                    "similarity_score": round(row.similarity_score, 4),
                    "chunk_type": row.chunk_type,
                    "parent_id": row.parent_id,
                    "child_id": row.child_id,
                    "headers": {
                        "header_1": row.header_1,
                        "header_2": row.header_2,
                        "header_3": row.header_3,
                        "header_4": row.header_4,
                    },
                    "document_id": row.document_id,
                    "filename": row.filename,
                    "doc_type": row.doc_type,
                    "category": row.category,
                    "auto_tags": row.auto_tags or [],
                    "room_id": row.room_id,
                    "is_room_document": row.room_id is not None,
                }
            )

        return search_results

    async def search_documents_hybrid(
        self,
        query_embedding: List[float],
        session: AsyncSession,
        room_id: Optional[int] = None,
        doc_types: Optional[List[str]] = None,
        top_k: int = 15,
        system_weight: float = 0.6,
        room_weight: float = 0.4,
    ) -> List[Dict[str, Any]]:
        """하이브리드 검색 (시스템 문서 + 방별 문서 가중치 적용)"""

        try:
            # 1. 시스템 문서 검색 (전역 문서)
            system_results = await self.search_documents_by_vector(
                query_embedding=query_embedding,
                session=session,
                doc_types=doc_types,
                top_k=top_k,
            )

            # 2. 방별 문서 검색 (해당 방의 문서)
            room_results = []
            if room_id is not None:
                room_results = await self.search_documents_by_vector_with_room_context(
                    query_embedding=query_embedding,
                    session=session,
                    room_id=room_id,
                    doc_types=doc_types,
                    top_k=top_k,
                )
                # 방별 문서만 필터링
                room_results = [
                    r for r in room_results if r.get("is_room_document", False)
                ]

            # 3. 가중치 적용 및 결과 병합
            combined_results = []

            # 시스템 문서에 가중치 적용
            for result in system_results:
                result["weighted_score"] = result["similarity_score"] * system_weight
                result["source_type"] = "system"
                combined_results.append(result)

            # 방별 문서에 가중치 적용
            for result in room_results:
                result["weighted_score"] = result["similarity_score"] * room_weight
                result["source_type"] = "room"
                combined_results.append(result)

            # 4. 가중치 점수로 정렬
            combined_results.sort(key=lambda x: x["weighted_score"], reverse=True)

            # 5. 상위 결과 반환
            return combined_results[:top_k]

        except Exception as e:
            print(f"⚠️ 하이브리드 검색 실패: {str(e)}")
            # 실패시 기본 검색으로 폴백
            return await self.search_documents_by_vector(
                query_embedding=query_embedding,
                session=session,
                doc_types=doc_types,
                top_k=top_k,
            )
