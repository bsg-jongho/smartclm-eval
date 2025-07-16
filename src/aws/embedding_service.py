import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_aws import BedrockEmbeddings

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingConfig:
    """임베딩 설정 클래스"""

    model_id: str = "amazon.titan-embed-text-v2:0"
    dimensions: int = 1024  # 256, 512, 1024 중 선택
    normalize: bool = True
    region_name: str = "ap-northeast-2"


class TitanEmbeddingService:
    """Amazon Titan Text Embeddings V2 + LangChain 서비스"""

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        """
        Titan 임베딩 서비스 초기화

        Args:
            config: 임베딩 설정 (None이면 기본값 사용)
        """
        self.config = config or EmbeddingConfig()

        # LangChain BedrockEmbeddings 초기화
        self.embeddings = BedrockEmbeddings(
            model_id=self.config.model_id,
            region_name=self.config.region_name,
            model_kwargs={
                "dimensions": self.config.dimensions,
                "normalize": self.config.normalize,
            },
        )

        logger.info("Titan 임베딩 서비스 초기화 완료")
        logger.info(f"  - 모델: {self.config.model_id}")
        logger.info(f"  - 차원: {self.config.dimensions}")
        logger.info(f"  - 정규화: {self.config.normalize}")

    async def create_single_embedding(self, text: str) -> List[float]:
        """
        단일 텍스트 임베딩 생성

        Args:
            text: 임베딩할 텍스트

        Returns:
            List[float]: 임베딩 벡터
        """
        try:
            logger.debug(f"단일 임베딩 생성: {text[:100]}...")
            embedding = await self.embeddings.aembed_query(text)
            logger.debug(f"임베딩 생성 완료: {len(embedding)}차원")
            return embedding
        except Exception as e:
            logger.error(f"단일 임베딩 생성 실패: {str(e)}")
            raise

    async def create_batch_embeddings(
        self, texts: List[str], show_progress: bool = True
    ) -> List[List[float]]:
        """
        배치 임베딩 생성 (LangChain 자동 최적화)

        Args:
            texts: 임베딩할 텍스트 리스트
            show_progress: 진행상황 표시 여부

        Returns:
            List[List[float]]: 임베딩 벡터 리스트
        """
        if not texts:
            return []

        try:
            if show_progress:
                logger.info(f"배치 임베딩 시작: {len(texts)}개 텍스트")

            # LangChain이 자동으로 배치 처리, 에러 핸들링, 재시도 수행
            embeddings = await self.embeddings.aembed_documents(texts)

            if show_progress:
                logger.info(f"배치 임베딩 완료: {len(embeddings)}개 벡터 생성")

            return embeddings

        except Exception as e:
            logger.error(f"배치 임베딩 생성 실패: {str(e)}")
            raise

    async def embed_chunked_documents(
        self, chunked_documents: List[Dict[str, Any]], content_key: str = "content"
    ) -> List[Dict[str, Any]]:
        """
        청킹된 문서들을 임베딩하여 벡터 DB 저장용 형태로 변환
        Parent chunk (맥락용)는 임베딩 없이, Child chunk (검색용)만 임베딩 처리

        Args:
            chunked_documents: HierarchicalChunker의 create_vector_ready_chunks 결과
            content_key: 텍스트 내용이 들어있는 키 이름

        Returns:
            임베딩이 추가된 문서 리스트 (Parent는 임베딩 없음, Child는 임베딩 포함)
        """
        if not chunked_documents:
            return []

        logger.info(f"문서 청크 임베딩 시작: {len(chunked_documents)}개 청크")

        try:
            # 임베딩 대상 분리
            embedding_targets = []
            non_embedding_chunks = []

            for i, doc in enumerate(chunked_documents):
                if doc.get(
                    "is_for_embedding", True
                ):  # Child chunk (기본값 True로 하위 호환성 유지)
                    embedding_targets.append((i, doc))
                else:  # Parent chunk (임베딩 없이 저장)
                    enhanced_doc = doc.copy()
                    enhanced_doc["embedding"] = None
                    enhanced_doc["embedding_success"] = False
                    enhanced_doc["embedding_metadata"] = {
                        "model_id": self.config.model_id,
                        "reason": "Parent chunk - 임베딩 불필요",
                        "chunk_type": doc.get("chunk_type", "unknown"),
                    }
                    non_embedding_chunks.append((i, enhanced_doc))

            logger.info(
                f"  📄 임베딩 대상: {len(embedding_targets)}개 (Child chunks + 단독 Parent chunks)"
            )
            logger.info(
                f"  📂 맥락 보존: {len(non_embedding_chunks)}개 (대형 섹션 Parent chunks)"
            )

            if not embedding_targets:
                logger.warning(
                    "임베딩 대상이 없습니다 (모두 Parent chunk인 것 같습니다)"
                )
                return [doc for _, doc in non_embedding_chunks]

            # 임베딩 대상 텍스트 추출
            texts = [doc.get(content_key, "") for _, doc in embedding_targets]

            # 빈 텍스트 필터링
            valid_texts = [(i, text) for i, text in enumerate(texts) if text.strip()]

            if not valid_texts:
                logger.warning("유효한 텍스트가 없습니다")
                return chunked_documents

            # 배치 임베딩 생성 (Child chunk만)
            valid_indices, valid_text_list = zip(*valid_texts)
            embeddings = await self.create_batch_embeddings(list(valid_text_list))

            # 결과 병합
            enhanced_documents = [None] * len(chunked_documents)
            embedding_index = 0

            # 임베딩된 Child chunks 처리
            for target_idx, (original_idx, doc) in enumerate(embedding_targets):
                enhanced_doc = doc.copy()

                if target_idx in valid_indices and embedding_index < len(embeddings):
                    enhanced_doc["embedding"] = embeddings[embedding_index]
                    enhanced_doc["embedding_success"] = True
                    enhanced_doc["embedding_metadata"] = {
                        "model_id": self.config.model_id,
                        "dimensions": len(embeddings[embedding_index]),
                        "normalized": self.config.normalize,
                        "chunk_type": doc.get("chunk_type", "child"),
                    }
                    embedding_index += 1
                else:
                    enhanced_doc["embedding"] = None
                    enhanced_doc["embedding_success"] = False
                    enhanced_doc["embedding_error"] = "빈 텍스트 또는 처리 실패"

                enhanced_documents[original_idx] = enhanced_doc

            # 임베딩 없는 Parent chunks 처리
            for original_idx, enhanced_doc in non_embedding_chunks:
                enhanced_documents[original_idx] = enhanced_doc

            successful_count = sum(
                1
                for doc in enhanced_documents
                if doc and doc.get("embedding_success", False)
            )
            parent_count = sum(
                1
                for doc in enhanced_documents
                if doc and doc.get("chunk_type") == "parent"
            )

            logger.info("문서 청크 임베딩 완료:")
            logger.info(
                f"  ✅ 임베딩 성공: {successful_count}개 (Child + 단독 Parent chunks)"
            )
            logger.info(f"  📂 맥락 보존: {parent_count}개 (Parent chunks)")
            logger.info(f"  📊 전체: {len([d for d in enhanced_documents if d])}개")

            return [doc for doc in enhanced_documents if doc is not None]

        except Exception as e:
            logger.error(f"문서 청크 임베딩 실패: {str(e)}")
            # 실패 시 원본 데이터에 실패 정보 추가
            return [
                {
                    **doc,
                    "embedding": None,
                    "embedding_success": False,
                    "embedding_error": str(e),
                }
                for doc in chunked_documents
            ]

    async def test_connection(self) -> Dict[str, Any]:
        """임베딩 서비스 연결 테스트"""
        try:
            logger.info("임베딩 서비스 연결 테스트 시작")

            # 테스트 임베딩 생성
            test_text = "안녕하세요. Amazon Titan 임베딩 연결 테스트입니다."
            embedding = await self.create_single_embedding(test_text)

            return {
                "success": True,
                "embedding_length": len(embedding),
                "test_text": test_text,
                "model_info": self.get_model_info(),
            }

        except Exception as e:
            logger.error(f"연결 테스트 실패: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "model_info": self.get_model_info(),
            }

    def get_model_info(self) -> Dict[str, Any]:
        """현재 모델 정보 반환"""
        return {
            "model_id": self.config.model_id,
            "dimensions": self.config.dimensions,
            "normalize": self.config.normalize,
            "region": self.config.region_name,
            "max_input_length": 8192,  # Titan V2 최대 입력 길이
            "supported_languages": [
                "ko",
                "en",
                "ja",
                "zh",
                "de",
                "fr",
                "es",
                "it",
                "pt",
                "ar",
            ],
            "framework": "langchain-aws",
        }

    def update_config(self, **kwargs) -> None:
        """설정 업데이트 (새 인스턴스 생성 필요)"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.info(f"설정 업데이트: {key} = {value}")
            else:
                logger.warning(f"알 수 없는 설정: {key}")

        logger.warning("설정 변경 후에는 서비스를 재초기화해야 합니다.")


# 싱글톤 인스턴스
titan_embedding_service = TitanEmbeddingService()
