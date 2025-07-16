"""
🤖 채팅 서비스

AI 챗봇 및 대화 기능을 제공하는 서비스입니다.
"""

import os
from typing import List, Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from src.aws.bedrock_service import BedrockService
from src.aws.embedding_service import TitanEmbeddingService
from src.documents.repository import DocumentRepository
from src.documents.service import document_service

from .schema import (
    StreamingChatRequest,
    StreamingChatResponse,
    StreamingContractDraftImprovementRequest,
    StreamingContractLegalAnalysisRequest,
    StreamingContractResponse,
)


class ChatService:
    """채팅 서비스"""

    def __init__(self):
        self.embedding_service = TitanEmbeddingService()
        self.bedrock_service = BedrockService()
        self.repository = DocumentRepository()

    async def streaming_chat(
        self, request: StreamingChatRequest, user_id: int, session: AsyncSession
    ):
        """스트리밍 채팅 (문서 전체 기반)"""
        try:
            if request.document_id is None:
                raise ValueError("document_id는 필수입니다.")
            # 1. 프롬프트 txt 파일 불러오기
            prompt_path = os.path.join(
                os.path.dirname(__file__), "prompts", "chat_stream_prompt.txt"
            )
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()

            # 2. 문서 전체(Parent 청크) context 생성
            chunks = await document_service.repository.get_chunks_by_document(
                request.document_id, session
            )
            parent_chunks = [
                c for c in chunks if getattr(c, "chunk_type", None) == "parent"
            ]
            if not parent_chunks:
                raise ValueError("해당 문서에 조항(Parent 청크)이 없습니다.")
            context_text = "\n\n".join(
                f"[{c.header_1}]\n{c.content}" for c in parent_chunks
            )

            # 3. 프롬프트와 컨텍스트 합치기
            full_prompt = prompt_template.replace("{context}", context_text)

            # 4. 스트리밍 응답 생성
            is_first_chunk = True
            async for chunk in self.bedrock_service.stream_model(
                prompt=full_prompt,
                max_tokens=request.max_tokens or 2000,
                temperature=0.0,
            ):
                yield StreamingChatResponse(
                    chunk=chunk["text"],
                    is_complete=chunk.get("is_complete", False),
                    token_usage=chunk.get("usage"),
                    sources=None,
                )
                is_first_chunk = False

        except Exception as e:
            print(f"❌ 스트리밍 채팅 실패: {str(e)}")
            yield StreamingChatResponse(
                chunk="오류가 발생했습니다.",
                is_complete=True,
                token_usage=None,
                sources=None,
            )

    async def streaming_contract_draft_improvement(
        self,
        request: StreamingContractDraftImprovementRequest,
        user_id: int,
        session: AsyncSession,
    ):
        """계약서 초안 작성 및 조항 개선 스트리밍"""
        try:
            if request.document_id is None:
                raise ValueError("document_id는 필수입니다.")
            if request.section_id is None:
                raise ValueError("section_id는 필수입니다.")
            # 1. 프롬프트 txt 파일 불러오기
            prompt_path = os.path.join(
                os.path.dirname(__file__),
                "prompts",
                "contract_draft_improvement_prompt.txt",
            )
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()

            # 2. 조항+앞뒤 맥락 context 생성
            section_context = await document_service.get_section_with_neighbors_context(
                document_id=request.document_id,
                section_id=request.section_id,
                session=session,
                neighbor_count=1,  # 앞뒤 1개씩 포함(조정 가능)
            )
            context_text = section_context["context_text"]

            # 3. 프롬프트와 컨텍스트 합치기
            full_prompt = prompt_template.replace("{context}", context_text)

            # 4. LLM 스트리밍 호출
            is_first_chunk = True
            async for chunk in self.bedrock_service.stream_model(
                prompt=full_prompt,
                max_tokens=request.max_tokens or 2000,
                temperature=0.0,
            ):
                yield StreamingContractResponse(
                    chunk=chunk["text"],
                    is_complete=chunk.get("is_complete", False),
                    token_usage=chunk.get("usage"),
                    sources=None,
                )
                is_first_chunk = False
        except Exception as e:
            print(f"❌ 계약서 초안 작성/개선 스트리밍 실패: {str(e)}")
            yield StreamingContractResponse(
                chunk="오류가 발생했습니다.",
                is_complete=True,
                token_usage=None,
                sources=None,
            )

    async def streaming_contract_legal_analysis(
        self,
        request: StreamingContractLegalAnalysisRequest,
        user_id: int,
        session: AsyncSession,
    ):
        """계약서 조항 분석 및 법적 위험 분석 스트리밍"""
        try:
            if request.document_id is None:
                raise ValueError("document_id는 필수입니다.")
            if request.section_id is None:
                raise ValueError("section_id는 필수입니다.")
            # 1. 프롬프트 txt 파일 불러오기
            prompt_path = os.path.join(
                os.path.dirname(__file__),
                "prompts",
                "contract_legal_analysis_prompt.txt",
            )
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()

            # 2. 조항+앞뒤 맥락 context 생성
            section_context = await document_service.get_section_with_neighbors_context(
                document_id=request.document_id,
                section_id=request.section_id,
                session=session,
                neighbor_count=1,  # 앞뒤 1개씩 포함(조정 가능)
            )
            context_text = section_context["context_text"]

            # 3. 프롬프트와 컨텍스트 합치기
            full_prompt = prompt_template.replace("{context}", context_text)

            # 4. LLM 스트리밍 호출
            is_first_chunk = True
            async for chunk in self.bedrock_service.stream_model(
                prompt=full_prompt,
                max_tokens=request.max_tokens or 2000,
                temperature=0.0,
            ):
                yield StreamingContractResponse(
                    chunk=chunk["text"],
                    is_complete=chunk.get("is_complete", False),
                    token_usage=chunk.get("usage"),
                    sources=None,
                )
                is_first_chunk = False
        except Exception as e:
            print(f"❌ 계약서 조항 분석/법적 위험 분석 스트리밍 실패: {str(e)}")
            yield StreamingContractResponse(
                chunk="오류가 발생했습니다.",
                is_complete=True,
                token_usage=None,
                sources=None,
            )

    async def _search_relevant_documents(
        self,
        query: str,
        room_id: Optional[int],
        doc_types: Optional[List[str]],
        db_session: AsyncSession,
    ) -> List[dict]:
        """관련 문서 검색 (일반 채팅용)"""
        try:
            # 쿼리 임베딩 생성
            query_embedding = await self.embedding_service.create_single_embedding(
                query
            )

            # 하이브리드 검색 (방별 문서 + 시스템 문서)
            search_results = await self.repository.search_documents_hybrid(
                query_embedding=query_embedding,
                session=db_session,
                room_id=room_id,
                doc_types=doc_types,
                top_k=8,
                system_weight=0.6,
                room_weight=0.4,
            )

            # 결과 변환
            relevant_docs = []
            for result in search_results:
                relevant_docs.append(
                    {
                        "document_id": result["document_id"],
                        "title": result["filename"],
                        "content": result["content"],
                        "similarity_score": result["similarity_score"],
                        "doc_type": result["doc_type"],
                        "source_type": result.get("source_type", "system"),
                    }
                )

            return relevant_docs

        except Exception as e:
            print(f"⚠️ 문서 검색 실패: {str(e)}")
            return []

    async def _search_relevant_documents_for_draft_improvement(
        self,
        query: str,
        document_id: Optional[int],
        room_id: Optional[int],
        db_session: AsyncSession,
    ) -> List[dict]:
        """계약서 초안 작성 및 조항 개선용 관련 문서 검색"""
        try:
            # 쿼리 임베딩 생성
            query_embedding = await self.embedding_service.create_single_embedding(
                query
            )

            # 초안 작성 관련 문서 유형
            draft_doc_types = ["standard_contract", "guideline", "law"]

            # 하이브리드 검색 (방별 문서 + 시스템 문서)
            search_results = await self.repository.search_documents_hybrid(
                query_embedding=query_embedding,
                session=db_session,
                room_id=room_id,
                doc_types=draft_doc_types,
                top_k=10,
                system_weight=0.7,
                room_weight=0.3,
            )

            # 결과 변환
            relevant_docs = []
            for result in search_results:
                relevant_docs.append(
                    {
                        "document_id": result["document_id"],
                        "title": result["filename"],
                        "content": result["content"],
                        "similarity_score": result["similarity_score"],
                        "doc_type": result["doc_type"],
                        "source_type": result.get("source_type", "system"),
                    }
                )

            return relevant_docs

        except Exception as e:
            print(f"⚠️ 초안 작성 문서 검색 실패: {str(e)}")
            return []

    async def _search_relevant_documents_for_legal_analysis(
        self,
        query: str,
        document_id: Optional[int],
        room_id: Optional[int],
        db_session: AsyncSession,
    ) -> List[dict]:
        """계약서 법적 분석용 관련 문서 검색"""
        try:
            # 쿼리 임베딩 생성
            query_embedding = await self.embedding_service.create_single_embedding(
                query
            )

            # 법적 분석 관련 문서 유형
            legal_doc_types = ["law", "precedent", "guideline"]

            # 하이브리드 검색 (방별 문서 + 시스템 문서)
            search_results = await self.repository.search_documents_hybrid(
                query_embedding=query_embedding,
                session=db_session,
                room_id=room_id,
                doc_types=legal_doc_types,
                top_k=10,
                system_weight=0.8,
                room_weight=0.2,
            )

            # 결과 변환
            relevant_docs = []
            for result in search_results:
                relevant_docs.append(
                    {
                        "document_id": result["document_id"],
                        "title": result["filename"],
                        "content": result["content"],
                        "similarity_score": result["similarity_score"],
                        "doc_type": result["doc_type"],
                        "source_type": result.get("source_type", "system"),
                    }
                )

            return relevant_docs

        except Exception as e:
            print(f"⚠️ 법적 분석 문서 검색 실패: {str(e)}")
            return []

    def _build_chat_context(
        self,
        question: str,
        relevant_docs: List[dict],
    ) -> str:
        """채팅 컨텍스트 구성 (일반)"""
        context_parts = []

        # 관련 문서 컨텍스트
        if relevant_docs:
            docs_context = "참고 문서:\n"
            for i, doc in enumerate(relevant_docs, 1):
                source_type = doc.get("source_type", "system")
                source_label = "방 문서" if source_type == "room" else "시스템 문서"
                docs_context += f"{i}. {doc['title']} ({doc['doc_type']}, {source_label}): {doc['content'][:500]}...\n"
            context_parts.append(docs_context)

        # 현재 질문
        context_parts.append(f"사용자 질문: {question}")

        return "\n\n".join(context_parts)

    def _build_draft_improvement_context(
        self,
        question: str,
        context_text: Optional[str],
        document_id: Optional[int],
        room_id: Optional[int],
        relevant_docs: List[dict],
    ) -> str:
        """계약서 초안 작성 및 조항 개선 컨텍스트 구성"""
        context_parts = []

        # 작성/개선하려는 조항
        if context_text:
            context_parts.append(f"[작성/개선하려는 조항]\n{context_text}")

        # 문서 및 방 정보
        if document_id:
            context_parts.append(f"[표준계약서 원본 문서 ID: {document_id}]")
        if room_id:
            context_parts.append(f"[방 ID: {room_id}]")

        # 참고 문서 컨텍스트
        if relevant_docs:
            docs_context = "참고 문서 (표준계약서, 가이드라인, 법령):\n"
            for i, doc in enumerate(relevant_docs, 1):
                source_type = doc.get("source_type", "system")
                source_label = "방 문서" if source_type == "room" else "시스템 문서"
                docs_context += f"{i}. {doc['title']} ({doc['doc_type']}, {source_label}): {doc['content'][:500]}...\n"
            context_parts.append(docs_context)

        # 질문/요청
        context_parts.append(f"[질문/요청]\n{question}")

        return "\n\n".join(context_parts)

    def _build_legal_analysis_context(
        self,
        question: str,
        context_text: Optional[str],
        document_id: Optional[int],
        room_id: Optional[int],
        relevant_docs: List[dict],
    ) -> str:
        """계약서 법적 분석 컨텍스트 구성"""
        context_parts = []

        # 분석할 조항/부분
        if context_text:
            context_parts.append(f"[분석할 조항/부분]\n{context_text}")

        # 분석할 계약서 정보
        if document_id:
            context_parts.append(f"[분석할 계약서 문서 ID: {document_id}]")
        if room_id:
            context_parts.append(f"[방 ID: {room_id}]")

        # 참고 문서 컨텍스트
        if relevant_docs:
            docs_context = "참고 문서 (법령, 판례, 가이드라인):\n"
            for i, doc in enumerate(relevant_docs, 1):
                source_type = doc.get("source_type", "system")
                source_label = "방 문서" if source_type == "room" else "시스템 문서"
                docs_context += f"{i}. {doc['title']} ({doc['doc_type']}, {source_label}): {doc['content'][:500]}...\n"
            context_parts.append(docs_context)

        # 질문/요청
        context_parts.append(f"[질문/요청]\n{question}")

        return "\n\n".join(context_parts)


# 서비스 인스턴스
chat_service = ChatService()
