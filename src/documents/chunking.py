from typing import Any, Dict, List, Optional

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)


class HierarchicalChunker:
    """
    Docling에서 추출한 마크다운을 기반으로 계층적 청킹을 수행하는 클래스
    """

    def __init__(self):
        # 헤더 정의 (헤더 레벨과 메타데이터 키 이름)
        self.headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
            ("####", "Header 4"),
        ]

        # Markdown 헤더 기준 분할기
        self.markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.headers_to_split_on
        )

        # Child 문서용 텍스트 분할기 설정
        self.chunk_size = 500
        self.chunk_overlap = 50
        self._create_child_splitter()

    def _create_child_splitter(self):
        """Child splitter를 생성합니다."""
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
        )

    def update_chunk_settings(self, chunk_size: int, chunk_overlap: int):
        """청킹 설정을 업데이트합니다."""
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._create_child_splitter()
        print(f"📐 청킹 설정 업데이트: 크기={chunk_size}, 오버랩={chunk_overlap}")

    def chunk_markdown(
        self, markdown_content: str, filename: str = "document"
    ) -> Dict[str, Any]:
        """
        마크다운 콘텐츠를 계층적으로 청킹합니다.
        한국어 조항 패턴(제X조)도 인식하여 원본 번호를 보존합니다.

        Args:
            markdown_content: 마크다운 형식의 문서 내용
            filename: 파일명 (메타데이터용)

        Returns:
            청킹 결과 딕셔너리
        """
        print(f"📄 마크다운 계층적 청킹 시작: {filename}")

        try:
            import re
            
            # 1단계: 한국어 조항 패턴 전처리 - 제X조를 마크다운 헤더로 변환
            lines = markdown_content.split('\n')
            preprocessed_lines = []
            
            for line in lines:
                # 제X조 패턴을 ## 헤더로 변환하여 MarkdownHeaderTextSplitter가 인식하도록 함
                if re.match(r'^제\s*\d+\s*조', line.strip()):
                    # "제8조 (계약기간)" 또는 "제8조" → "## 제8조 (계약기간)"
                    preprocessed_lines.append(f"## {line.strip()}")
                    print(f"🔍 조항 패턴 발견: {line.strip()} → ## {line.strip()}")
                else:
                    preprocessed_lines.append(line)
            
            preprocessed_markdown = '\n'.join(preprocessed_lines)
            
            # 2단계: 전처리된 마크다운으로 헤더 기준 분할 (Parent chunks)
            parent_chunks = self.markdown_splitter.split_text(preprocessed_markdown)

            print(f"📊 헤더 분할 결과: {len(parent_chunks)}개 섹션")
            print(
                f"📏 섹션별 크기: {[len(chunk.page_content) for chunk in parent_chunks]}"
            )

            # 3단계: Parent chunks에서 원본 조항 번호 복원
            for idx, parent_chunk in enumerate(parent_chunks):
                # Header 2에서 "제X조" 패턴이 있다면 원본 형태로 복원
                header_2 = parent_chunk.metadata.get("Header 2", "")
                if header_2 and header_2.startswith("제") and "조" in header_2:
                    # "제8조 (계약기간)" 형태 그대로 유지
                    parent_chunk.metadata["Header 1"] = header_2
                    print(f"🔄 조항 번호 복원: {header_2}")
                
                preview = parent_chunk.page_content[:200].replace("\n", "\\n")

            # 4단계: 각 parent chunk를 child chunks로 세분화
            all_child_chunks = []
            parent_child_mapping = {}

            for parent_idx, parent_chunk in enumerate(parent_chunks):
                parent_id = f"{filename}_parent_{parent_idx}"

                # Parent chunk 메타데이터 보강
                parent_chunk.metadata.update(
                    {
                        "source": filename,
                        "chunk_type": "parent",
                        "parent_id": parent_id,
                        "parent_index": parent_idx,
                        "content_length": len(parent_chunk.page_content),
                    }
                )

                # Parent chunk를 child chunks로 분할
                if len(parent_chunk.page_content) > 500:  # 큰 섹션만 추가 분할
                    child_docs = self.child_splitter.split_documents([parent_chunk])

                    # Child chunks 메타데이터 설정
                    for child_idx, child_doc in enumerate(child_docs):
                        child_id = f"{parent_id}_child_{child_idx}"
                        child_doc.metadata.update(
                            {
                                "source": filename,
                                "chunk_type": "child",
                                "parent_id": parent_id,
                                "child_id": child_id,
                                "child_index": child_idx,
                                "content_length": len(child_doc.page_content),
                            }
                        )
                        all_child_chunks.append(child_doc)

                    parent_child_mapping[parent_id] = [
                        doc.metadata["child_id"] for doc in child_docs
                    ]
                    print(f"  📂 섹션 {parent_idx}: {len(child_docs)}개 하위 청크 생성")

                    # Child chunks 상세 정보 로그
                    for child_idx, child_doc in enumerate(child_docs):
                        preview = child_doc.page_content[:100].replace("\n", "\\n")
                else:
                    # 작은 섹션(500자 이하)은 Parent만 저장하고 Child는 생성하지 않음
                    # Parent chunk 메타데이터에 단독 저장 표시
                    parent_chunk.metadata.update(
                        {
                            "is_standalone": True,  # Parent만 단독 저장되는 청크임을 표시
                            "skip_child_creation": True,  # Child 생성 스킵 플래그
                        }
                    )
                    parent_child_mapping[parent_id] = []  # Child 없음

            # 결과 정리
            result = {
                "success": True,
                "filename": filename,
                "parent_chunks": parent_chunks,
                "child_chunks": all_child_chunks,
                "parent_child_mapping": parent_child_mapping,
                "summary": {
                    "total_parent_chunks": len(parent_chunks),
                    "total_child_chunks": len(all_child_chunks),
                    "average_parent_size": sum(
                        len(chunk.page_content) for chunk in parent_chunks
                    )
                    // len(parent_chunks)
                    if parent_chunks
                    else 0,
                    "average_child_size": sum(
                        len(chunk.page_content) for chunk in all_child_chunks
                    )
                    // len(all_child_chunks)
                    if all_child_chunks
                    else 0,
                },
            }

            print("\n" + "=" * 80)
            print("✅ 계층적 청킹 완료 - 최종 결과 요약")
            print("=" * 80)
            print(f"📊 Parent chunks: {result['summary']['total_parent_chunks']}개")
            print(f"📊 Child chunks: {result['summary']['total_child_chunks']}개")
            print(f"📏 평균 Parent 크기: {result['summary']['average_parent_size']}자")
            print(f"📏 평균 Child 크기: {result['summary']['average_child_size']}자")

            return result

        except Exception as e:
            print(f"❌ 청킹 처리 오류: {e}")
            return {"success": False, "error": str(e), "filename": filename}

    def create_vector_ready_chunks(
        self, chunking_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        벡터 DB 저장용 청크 데이터를 생성합니다.
        Parent chunk (전체 맥락용)와 Child chunk (검색용) 모두 포함합니다.

        Args:
            chunking_result: chunk_markdown 결과

        Returns:
            벡터 DB 저장용 청크 리스트 (Parent + Child)
        """
        if not chunking_result.get("success"):
            return []

        vector_ready_chunks = []

        # 1. Parent chunks 추가 (전체 맥락 보존용)
        print("📂 Parent chunks를 DB 저장용으로 변환 중...")
        for parent_chunk in chunking_result["parent_chunks"]:
            parent_id = parent_chunk.metadata.get("parent_id")
            is_standalone = parent_chunk.metadata.get("is_standalone", False)

            parent_data = {
                "content": parent_chunk.page_content,
                "metadata": parent_chunk.metadata,
                "chunk_id": parent_id,  # Parent 고유 ID
                "parent_id": parent_id,  # 자신의 ID (더 직관적)
                "child_id": parent_id,  # DB 저장시 child_id 필드에 자신의 ID 저장
                "chunk_type": "parent",  # DB 구분용
                "headers": {
                    "header_1": parent_chunk.metadata.get("Header 1", ""),
                    "header_2": parent_chunk.metadata.get("Header 2", ""),
                    "header_3": parent_chunk.metadata.get("Header 3", ""),
                    "header_4": parent_chunk.metadata.get("Header 4", ""),
                },
                "source_file": parent_chunk.metadata.get("source", ""),
                "content_length": len(parent_chunk.page_content),
                "is_standalone": is_standalone,  # 단독 저장 여부 표시
            }

            # 작은 섹션(단독 저장)의 경우 임베딩도 포함 (검색 가능하도록)
            if is_standalone:
                parent_data.update(
                    {
                        "embedding": None,  # 임베딩은 나중에 생성
                        "embedding_success": False,
                        "is_for_embedding": True,  # 단독 저장되는 Parent는 임베딩 대상
                    }
                )
            else:
                # 큰 섹션의 Parent는 임베딩 없음 (Child가 검색 담당)
                parent_data.update(
                    {
                        "embedding": None,
                        "embedding_success": False,
                        "is_for_embedding": False,  # 임베딩 대상 아님
                    }
                )

            # print(
            #     f"   📂 Parent 벡터 변환: parent_id={parent_id} (자신), child_id={parent_id}, standalone={is_standalone}"
            # )
            vector_ready_chunks.append(parent_data)

        print(
            f"   ✅ {len(chunking_result['parent_chunks'])}개 Parent chunks 준비 완료"
        )

        # 2. Child chunks 추가 (검색용 - 임베딩 대상)
        print("📄 Child chunks를 벡터 DB 저장용으로 변환 중...")
        for child_chunk in chunking_result["child_chunks"]:
            parent_id = child_chunk.metadata.get("parent_id")
            child_id = child_chunk.metadata.get("child_id")

            child_data = {
                "content": child_chunk.page_content,
                "metadata": child_chunk.metadata,
                "chunk_id": child_id,
                "parent_id": parent_id,
                "child_id": child_id,  # Child 자신의 ID도 저장
                "chunk_type": "child",  # DB 구분용
                "headers": {
                    "header_1": child_chunk.metadata.get("Header 1", ""),
                    "header_2": child_chunk.metadata.get("Header 2", ""),
                    "header_3": child_chunk.metadata.get("Header 3", ""),
                    "header_4": child_chunk.metadata.get("Header 4", ""),
                },
                "source_file": child_chunk.metadata.get("source", ""),
                "content_length": len(child_chunk.page_content),
                # Child는 임베딩 대상
                "is_for_embedding": True,  # 임베딩 대상임을 명시
            }

            # print(f"   🔗 벡터 변환: parent_id={parent_id}, child_id={child_id}")
            vector_ready_chunks.append(child_data)

        print(f"   ✅ {len(chunking_result['child_chunks'])}개 Child chunks 준비 완료")

        total_parent = len(chunking_result["parent_chunks"])
        total_child = len(chunking_result["child_chunks"])

        print(f"🔄 벡터 DB 저장용 청크 총 {len(vector_ready_chunks)}개 생성")
        print(f"   📂 Parent chunks: {total_parent}개 (전체 맥락 보존용)")
        print(f"   📄 Child chunks: {total_child}개 (벡터 검색용)")

        return vector_ready_chunks

    def get_parent_context(
        self, chunking_result: Dict[str, Any], child_chunk_id: str
    ) -> Optional[str]:
        """
        Child chunk ID를 기반으로 해당하는 Parent chunk의 전체 컨텍스트를 반환합니다.

        Args:
            chunking_result: chunk_markdown 결과
            child_chunk_id: Child chunk ID

        Returns:
            Parent chunk의 전체 내용
        """
        if not chunking_result.get("success"):
            return None

        # Child chunk에서 parent_id 찾기
        parent_id = None
        for child_chunk in chunking_result["child_chunks"]:
            if child_chunk.metadata.get("child_id") == child_chunk_id:
                parent_id = child_chunk.metadata.get("parent_id")
                break

        if not parent_id:
            return None

        # Parent chunk 찾기
        for parent_chunk in chunking_result["parent_chunks"]:
            if parent_chunk.metadata.get("parent_id") == parent_id:
                return parent_chunk.page_content

        return None

    def integrate_image_ocr(self, markdown_content: str, images_data: list) -> str:
        """이미지 OCR 텍스트를 마크다운에 통합"""
        enhanced_markdown = markdown_content

        for image_info in images_data:
            if image_info.get("ocr_text") and image_info.get("is_info_rich"):
                ocr_text = image_info["ocr_text"]
                enhanced_markdown = enhanced_markdown.replace(
                    "<!-- image -->",
                    f"\n### 이미지 {image_info['image_index']} 내용\n{ocr_text}\n",
                    1,  # 첫 번째 매칭만 교체
                )

        return enhanced_markdown


# 싱글톤 인스턴스
hierarchical_chunker = HierarchicalChunker()
