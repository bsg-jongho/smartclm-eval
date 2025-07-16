"""
📄 공통 문서 업로드 서비스

어드민과 사용자 문서 업로드의 공통 로직을 담당합니다.
"""

import os
import time
import traceback
import uuid
from datetime import datetime
from typing import Dict, Optional

from fastapi import HTTPException, UploadFile
from sqlmodel.ext.asyncio.session import AsyncSession

from src.aws.bedrock_service import BedrockService
from src.aws.dependency import get_s3_service
from src.aws.embedding_service import TitanEmbeddingService
from src.documents.chunking import HierarchicalChunker
from src.documents.repository import DocumentRepository
from src.external_services.doc_converter.client import doc_converter_client
from src.external_services.doc_parser.client import doc_parser_client
from src.models import Chunk, Document


class BaseDocumentService:
    """공통 문서 업로드 서비스"""

    def __init__(self):
        self.embedding_service = TitanEmbeddingService()
        self.chunker = HierarchicalChunker()
        self.bedrock_service = BedrockService()
        self.s3_service = get_s3_service()
        self.repository = DocumentRepository()

    async def _analyze_document_comprehensive(
        self,
        file: UploadFile,
        analysis_result: Dict,
        doc_type: str,
        session: AsyncSession = None,
        user_id: Optional[int] = None,
        is_admin: bool = False,
    ) -> Dict:
        """통합 문서 분석 (문서 유형 분류 + 상세 분석 + 계약서 검토)"""
        filename = file.filename or ""

        # doc_parser 분석 결과에서 텍스트 내용 추출
        markdown_content = analysis_result.get("markdown_content", "")
        file_size = file.size or 0
        page_count = analysis_result.get("page_count", 0)

        # 사용자 업로드 시에만 크기 제한 체크
        if not is_admin:
            if page_count > 80:
                raise HTTPException(
                    status_code=400,
                    detail=f"문서가 너무 큽니다. 현재 {page_count}페이지, 최대 80페이지까지 지원합니다. (Claude 200K 토큰 제한 기준)",
                )
            if file_size > 50 * 1024 * 1024:  # 50MB
                raise HTTPException(
                    status_code=400,
                    detail=f"파일이 너무 큽니다. 현재 {file_size / (1024 * 1024):.1f}MB, 최대 50MB까지 지원합니다.",
                )

        print(
            f"📄 문서 크기: {file_size / (1024 * 1024):.2f}MB, 페이지: {page_count}장"
        )

        # 전체 문서 내용 사용 (제한 없음)
        content_for_analysis = markdown_content if markdown_content else ""
        print(f"✅ 전체 문서 사용: {len(content_for_analysis)}자")

        # 통합 분석 프롬프트 파일 읽기
        prompt_path = "src/documents/prompts/comprehensive_analysis_prompt.txt"
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()

        # RAG 컨텍스트 설정
        rag_context = (
            "관련 참고자료 없음" if is_admin else "관련 참고자료 없음"
        )  # TODO: 실제 RAG 구현 시 수정

        # 프롬프트 템플릿에 값 치환
        prompt = prompt_template.format(
            filename=filename,
            content_for_analysis=content_for_analysis,
            rag_context=rag_context,
        )

        # Bedrock LLM 호출
        print(f"🤖 통합 문서 분석 중: {filename} ({doc_type})")
        llm_response = self.bedrock_service.invoke_model(
            prompt=prompt, max_tokens=4000, temperature=0.1
        )

        # 실제 토큰 사용량 및 시간 정보 추출
        response_text = llm_response["text"]
        token_usage = llm_response["usage"]
        timing_info = llm_response.get("timing", {})

        print(
            f"📊 실제 토큰 사용량 - 입력: {token_usage['input_tokens']:,}, 출력: {token_usage['output_tokens']:,}, 총합: {token_usage['total_tokens']:,}"
        )
        if timing_info.get("processing_time_ms"):
            print(f"⏱️ 처리 시간: {timing_info['processing_time_ms']}ms")

        # 토큰 사용량 추적 (세션과 user_id가 있는 경우에만)
        if session and user_id:
            try:
                from src.monitoring import TokenTracker

                # 메타데이터 구성
                usage_metadata = {
                    "filename": file.filename,
                    "doc_type": doc_type,
                    "content_length": len(content_for_analysis),
                    "response_length": len(response_text),
                    "is_admin": is_admin,
                }

                operation_type = (
                    "admin_document_analysis" if is_admin else "user_document_analysis"
                )

                await TokenTracker.record_bedrock_usage(
                    session=session,
                    user_id=user_id,
                    operation_type=operation_type,
                    model_name="claude-3-sonnet-20240229-v1:0",
                    usage=token_usage,
                    usage_metadata=usage_metadata,
                    request_started_at=timing_info.get("request_started_at"),
                    response_received_at=timing_info.get("response_received_at"),
                    processing_time_ms=timing_info.get("processing_time_ms"),
                )
            except Exception as e:
                print(f"⚠️ 토큰 사용량 추적 실패: {str(e)}")
                # 토큰 추적 실패는 전체 프로세스를 중단하지 않음

        # JSON 응답 파싱
        import json
        import re

        try:
            # 응답에서 JSON 부분만 추출
            response_text = response_text.strip()

            # ```json ... ``` 블록 찾기
            json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
            if json_match:
                json_content = json_match.group(1).strip()
            else:
                # ```json 블록이 없으면 전체 텍스트에서 JSON 객체 찾기
                json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
                if json_match:
                    json_content = json_match.group(0)
                else:
                    # 마지막 시도: 첫 번째 {부터 마지막 }까지
                    start = response_text.find("{")
                    end = response_text.rfind("}") + 1
                    if start != -1 and end != 0:
                        json_content = response_text[start:end]
                    else:
                        raise json.JSONDecodeError(
                            "JSON 객체를 찾을 수 없습니다", response_text, 0
                        )

            comprehensive_result = json.loads(json_content)

            # 어드민이 지정한 문서 유형과 LLM 분류 결과 비교
            llm_doc_type = comprehensive_result.get("doc_type", "contract")
            if doc_type != llm_doc_type:
                print(f"⚠️ 경고: 지정({doc_type})과 LLM 분류({llm_doc_type})가 다릅니다")
                # 지정 유형을 우선 사용
                comprehensive_result["doc_type"] = doc_type

            # 토큰 사용량 추가
            comprehensive_result["token_usage"] = token_usage

            print(
                f"✅ 통합 분석 완료: {comprehensive_result.get('title', '제목 없음')}"
            )
            return comprehensive_result

        except json.JSONDecodeError as e:
            print(f"❌ 문서 분석 JSON 파싱 실패: {str(e)}")
            print(f"LLM 응답: {llm_response}")
            raise HTTPException(
                status_code=500, detail="문서 상세 분석에 실패했습니다: JSON 파싱 오류"
            )
        except Exception as e:
            print(f"❌ 문서 분석 실패: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"문서 상세 분석에 실패했습니다: {str(e)}"
            )

    async def _process_document_chunks(
        self, document: Document, analysis_result: Dict, session: AsyncSession
    ):
        """문서 청킹 및 임베딩 처리"""
        try:
            print(f"✂️ 문서 청킹 중: {document.filename}")

            # 1. 마크다운 청킹
            markdown_content = analysis_result.get("markdown_content", "")
            chunking_result = self.chunker.chunk_markdown(
                markdown_content=markdown_content,
                filename=document.filename,
            )

            # 2. 벡터용 청크 생성
            vector_ready_chunks = self.chunker.create_vector_ready_chunks(
                chunking_result
            )

            # 3. 임베딩 생성
            embedded_chunks = await self.embedding_service.embed_chunked_documents(
                vector_ready_chunks
            )

            # 4. 청크 저장
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

            await self.repository.create_chunks(chunk_objects, session)
            print(f"✅ 청크 저장 완료: {len(chunk_objects)}개")

        except Exception as e:
            print(f"❌ 청킹 처리 실패: {str(e)}")
            # 청킹 실패해도 문서는 저장됨

    async def _upload_document_common(
        self,
        file: UploadFile,
        doc_type: str,
        room_id: Optional[int],
        user_id: int,
        session: AsyncSession,
        is_admin: bool = False,
    ) -> Dict:
        """공통 문서 업로드 로직"""
        start_time = time.time()

        try:
            # 1. 파일 형식 확인 및 PDF 변환
            print(f"📄 파일 형식 확인 중: {file.filename}")
            print(f"📄 원본 파일 크기: {file.size} bytes")
            file_extension = (
                file.filename.lower().split(".")[-1] if file.filename else ""
            )

            # PDF가 아닌 경우 변환
            if file_extension != "pdf":
                print(f"🔄 PDF 변환 중: {file.filename}")
                pdf_filename = file.filename.replace(f".{file_extension}", ".pdf")
                pdf_tmp_path = None
                pdf_bytes = None

                try:
                    # doc_converter_client를 사용하여 PDF 변환
                    pdf_bytes = await doc_converter_client.convert_to_pdf(file)

                    # 변환된 PDF 바이트 데이터 검증
                    if not pdf_bytes or len(pdf_bytes) == 0:
                        raise Exception("변환된 PDF가 비어있습니다")

                    print(f"✅ PDF 변환 완료: {pdf_filename} ({len(pdf_bytes)} bytes)")

                    # 임시 파일로 PDF 저장
                    import tempfile

                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=".pdf"
                    ) as pdf_tmp:
                        pdf_tmp.write(pdf_bytes)
                        pdf_tmp_path = pdf_tmp.name

                    # 변환된 PDF를 UploadFile로 생성 (BytesIO 사용)
                    from io import BytesIO

                    from fastapi import UploadFile as FastAPIUploadFile

                    pdf_file_io = BytesIO(pdf_bytes)
                    pdf_file_io.seek(0)  # [추가] S3 업로드 전 포인터 초기화
                    converted_pdf_file = FastAPIUploadFile(
                        filename=pdf_filename,
                        file=pdf_file_io,
                    )
                    converted_pdf_file.size = len(pdf_bytes)

                except Exception as e:
                    print(f"❌ PDF 변환 실패: {str(e)}")
                    raise HTTPException(
                        status_code=400, detail=f"PDF 변환에 실패했습니다: {str(e)}"
                    )
            else:
                converted_pdf_file = file
                pdf_filename = file.filename
                pdf_tmp_path = None
                pdf_bytes = None

            # 2. PDF 분석 (doc_parser_client 사용)
            print(f"📄 PDF 분석 중: {pdf_filename}")
            print(f"📄 변환된 PDF 파일 크기: {converted_pdf_file.size} bytes")
            analysis_result = await doc_parser_client.analyze_pdf(converted_pdf_file)

            if not analysis_result["success"]:
                raise HTTPException(status_code=400, detail="PDF 분석에 실패했습니다")

            # 3. LLM 상세 분석
            print(f"🤖 LLM 분석 시작: {file.filename}")
            doc_analysis = await self._analyze_document_comprehensive(
                file, analysis_result, doc_type, session, user_id, is_admin
            )

            title = doc_analysis.get("title", file.filename or "제목 없음")
            category = doc_analysis.get("category")
            description = doc_analysis.get("description")
            confidence = doc_analysis.get("confidence", 0.0)
            review_analysis = doc_analysis.get("review_analysis")

            # 4. 버전 관리 (계약서인 경우에만)
            new_version = ""
            if doc_type == "contract" and not is_admin and room_id is not None:
                # 해당 방에서 가장 최신 계약서 조회
                existing_doc = await self.repository.get_latest_contract_in_room(
                    room_id=room_id,
                    session=session,
                )

                if existing_doc:
                    new_version = self._increment_version(existing_doc.version or "v1")
                    print(
                        f"📝 기존 계약서 발견: {existing_doc.filename} (버전 {existing_doc.version} → {new_version})"
                    )
                else:
                    new_version = "v1"
                    print(f"📄 새로운 계약서: {title} (버전 {new_version})")
            else:
                print(f"📚 참고 문서 업로드: {file.filename} (버전 관리 없음)")

            # 5. S3 경로 설정
            s3_prefix = "system" if is_admin else "contract"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            safe_filename = file.filename or "unknown.pdf"

            # 6. S3에 원본 파일 업로드
            print(f"📤 S3 원본 파일 업로드 중: {file.filename}")
            original_s3_key = f"{s3_prefix}/original/{doc_type}/{timestamp}_{unique_id}_{safe_filename}"

            # 원본 파일 포인터 리셋
            await file.seek(0)
            original_s3_result = await self.s3_service.upload_file(
                file=file, s3_key=original_s3_key
            )
            print(
                f"✅ 원본 파일 S3 업로드 완료: {original_s3_result['file_size']} bytes"
            )

            # 7. S3에 변환된 PDF 업로드
            print(f"📤 S3 PDF 파일 업로드 중: {pdf_filename}")
            pdf_s3_key = (
                f"{s3_prefix}/pdf/{doc_type}/{timestamp}_{unique_id}_{pdf_filename}"
            )

            # 변환된 PDF 파일의 경우 바이트 데이터를 직접 전달
            if pdf_bytes is not None:
                # 변환된 PDF 바이트 데이터 사용
                from io import BytesIO

                from fastapi import UploadFile as FastAPIUploadFile

                pdf_file_obj = FastAPIUploadFile(
                    filename=pdf_filename,
                    file=BytesIO(pdf_bytes),
                )
                pdf_file_obj.size = len(pdf_bytes)
                pdf_file_obj.file.seek(0)  # [추가] S3 업로드 전 포인터 초기화

                print(
                    f"📤 변환된 PDF S3 업로드: {pdf_filename} ({len(pdf_bytes)} bytes)"
                )
                pdf_s3_result = await self.s3_service.upload_file(
                    file=pdf_file_obj, s3_key=pdf_s3_key, content_type="application/pdf"
                )
                print(
                    f"✅ 변환된 PDF S3 업로드 완료: {pdf_s3_result['file_size']} bytes"
                )
            else:
                # 이미 PDF인 경우
                await converted_pdf_file.seek(0)
                print(f"📤 원본 PDF S3 업로드: {pdf_filename}")
                pdf_s3_result = await self.s3_service.upload_file(
                    file=converted_pdf_file,
                    s3_key=pdf_s3_key,
                    content_type="application/pdf",
                )
                print(f"✅ 원본 PDF S3 업로드 완료: {pdf_s3_result['file_size']} bytes")

            # 8. 문서 메타데이터 구성
            metadata = {
                "description": description,
                "analysis_info": {
                    "processing_time": time.time() - start_time,
                    "analysis_method": "comprehensive",
                    "confidence": confidence,
                },
                "token_usage": doc_analysis.get("token_usage", {}),
            }

            # 어드민 업로드 표시
            if is_admin:
                metadata["uploaded_by_admin"] = True

            # 계약서인 경우 검토 분석 결과 추가
            if doc_type == "contract" and review_analysis:
                metadata["review_analysis"] = review_analysis

            # 9. auto_tags 추출
            auto_tags = doc_analysis.get("auto_tags", [])
            if not auto_tags:
                # auto_tags가 없으면 기본 태그 생성
                auto_tags = [doc_type, category] if category else [doc_type]
                auto_tags = [tag for tag in auto_tags if tag]  # 빈 값 제거

            # 10. Document 모델 생성
            document = Document(
                room_id=room_id,  # None = 전역 문서, 숫자 = 방별 문서
                doc_type=doc_type,
                category=category,
                processing_status="completed",
                filename=file.filename or "unknown.pdf",
                version=new_version,
                s3_bucket=original_s3_result["bucket"],
                s3_key=original_s3_result["key"],
                pdf_s3_bucket=pdf_s3_result["bucket"],
                pdf_s3_key=pdf_s3_result["key"],
                file_size=file.size,
                pdf_file_size=converted_pdf_file.size,
                page_count=analysis_result.get("page_count"),
                document_metadata=metadata,
                auto_tags=auto_tags,
                html_content=analysis_result.get("html_content"),
                markdown_content=analysis_result.get("markdown_content"),
            )

            # 11. 문서 저장
            created_document = await self.repository.create_document(document, session)

            # 12. 청킹 및 임베딩
            await self._process_document_chunks(
                created_document, analysis_result, session
            )

            # 13. 방 정보 업데이트 (계약서 v1인 경우에만)
            if doc_type == "contract" and room_id is not None and new_version == "v1":
                await self._update_room_info(room_id, title, description, session)

            # 14. 임시 파일 정리
            if pdf_tmp_path and os.path.exists(pdf_tmp_path):
                try:
                    os.remove(pdf_tmp_path)
                    print(f"🧹 임시 파일 정리 완료: {pdf_tmp_path}")
                except Exception as e:
                    print(f"⚠️ 임시 파일 정리 실패: {str(e)}")

            return {
                "document": created_document,
                "title": title,
                "version": new_version,
                "review_analysis": review_analysis,
            }

        except Exception as e:
            print(f"❌ 문서 업로드 실패: {str(e)}")
            traceback.print_exc()
            raise HTTPException(
                status_code=500, detail=f"문서 업로드 중 오류가 발생했습니다: {str(e)}"
            )

    def _increment_version(self, current_version: str) -> str:
        """버전 번호 증가 (v1 → v2 → v3...)"""
        if not current_version or not current_version.startswith("v"):
            return "v1"

        try:
            version_num = int(current_version[1:])
            return f"v{version_num + 1}"
        except ValueError:
            return "v1"

    async def _update_room_info(
        self,
        room_id: int,
        title: str,
        description: Optional[str],
        session: AsyncSession,
    ):
        """방 정보 업데이트 (제목과 설명)"""
        try:
            from src.rooms.repository import room_repository

            # 방 조회
            room = await room_repository.get_room_by_id(room_id, session)
            if not room:
                print(f"⚠️ 방을 찾을 수 없습니다: room_id={room_id}")
                return

            # 방 제목이 "Untitled"인 경우에만 업데이트
            if room.name == "Untitled" and title:
                room.name = title
                print(f"🏠 방 제목 업데이트: {title}")

            # 방 설명이 없는 경우에만 업데이트
            if not room.description and description:
                room.description = description
                print(f"🏠 방 설명 업데이트: {description}")

            # 변경사항이 있는 경우에만 저장
            if room.name != "Untitled" or room.description:
                await room_repository.update_room(room, session)
                print(f"✅ 방 정보 업데이트 완료: room_id={room_id}")

        except Exception as e:
            print(f"⚠️ 방 정보 업데이트 실패: {str(e)}")
            # 방 업데이트 실패는 전체 프로세스를 중단하지 않음
