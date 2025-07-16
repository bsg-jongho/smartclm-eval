"""
📥 공통 문서 다운로드 라우터

모든 문서 다운로드 요청을 처리하는 공통 라우터입니다.
권한 체크를 통해 안전한 다운로드를 제공합니다.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from src.auth.dependency import get_current_user
from src.aws.dependency import get_s3_service
from src.core.database import get_session
from src.core.schema import SchemaBase, create_success_response
from src.documents.repository import DocumentRepository
from src.rooms.repository import room_repository

router = APIRouter(prefix="/download", tags=["📥 문서 다운로드"])


class DownloadDocumentInfo(SchemaBase):
    id: int
    title: str
    doc_type: str
    room_id: int | None
    is_system_document: bool


class DownloadUrlResponse(SchemaBase):
    download_url: str
    filename: str
    file_type: str
    expires_in: int
    document_info: DownloadDocumentInfo


@router.get("/documents/{document_id}")
async def download_document(
    document_id: int,
    file_type: str = "pdf",  # "original" 또는 "pdf" (기본값: pdf)
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    📥 문서 다운로드

    문서 ID로 원본 파일 또는 PDF 파일을 다운로드합니다.

    **파라미터:**
    - document_id: 문서 ID
    - file_type: 파일 유형 ("original" 또는 "pdf") - 기본값: pdf

    **권한 체크:**
    - 시스템 RAG용 문서 (room_id = NULL): 모든 사용자 다운로드 가능
    - 사용자 테스트 문서 (room_id != NULL):
      - 방 소유자만 다운로드 가능
      - 관리자는 모든 문서 다운로드 가능

    **응답:**
    - 다운로드 URL (1시간 유효)
    """
    try:
        # 문서 조회
        repository = DocumentRepository()
        document = await repository.get_document_by_id(
            document_id=document_id,
            session=session,
        )

        if not document:
            raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")

        # 권한 체크
        if document.room_id is not None:
            # 사용자 테스트 문서인 경우 (room_id != NULL)

            # 1. 관리자는 모든 문서 다운로드 가능
            if user["role"] == "admin":
                print(f"✅ 관리자 권한으로 다운로드 허용: 문서 ID {document_id}")
            else:
                # 2. 일반 사용자는 방 소유자만 다운로드 가능
                room = await room_repository.get_room_by_id(
                    room_id=document.room_id, session=session
                )

                if not room:
                    raise HTTPException(
                        status_code=404, detail="문서가 속한 방을 찾을 수 없습니다"
                    )

                if room.owner_id != user["user_id"]:
                    raise HTTPException(
                        status_code=403,
                        detail="이 문서는 방 소유자만 다운로드할 수 있습니다",
                    )

                print(
                    f"✅ 방 소유자 권한으로 다운로드 허용: 문서 ID {document_id}, 방 ID {document.room_id}"
                )
        else:
            # 시스템 RAG용 문서인 경우 (room_id = NULL) - 모든 사용자 다운로드 가능
            print(f"✅ 시스템 RAG 문서 다운로드 허용: 문서 ID {document_id}")

        # 파일 유형에 따른 S3 정보 선택
        if file_type == "pdf":
            if not document.pdf_s3_key:
                raise HTTPException(
                    status_code=404, detail="PDF 파일이 존재하지 않습니다"
                )

            s3_key = document.pdf_s3_key
            s3_bucket = document.pdf_s3_bucket
            filename = (
                document.filename.replace(document.filename.split(".")[-1], "pdf")
                if "." in document.filename
                else f"{document.filename}.pdf"
            )
        else:  # original
            s3_key = document.s3_key
            s3_bucket = document.s3_bucket
            filename = document.filename

        # 다운로드 URL 생성
        s3_service = get_s3_service()
        download_url = await s3_service.generate_download_url(
            s3_key=s3_key,
            bucket=s3_bucket,
            filename=filename,
            expires_in=900,  # 15분 (계약서 보안 강화)
        )

        return create_success_response(
            data=DownloadUrlResponse(
                download_url=download_url,
                filename=filename,
                file_type=file_type,
                expires_in=900,
                document_info=DownloadDocumentInfo(
                    id=document.id,
                    title=document.filename,
                    doc_type=document.doc_type,
                    room_id=document.room_id,
                    is_system_document=document.room_id is None,
                ),
            ),
            message="다운로드 URL이 생성되었습니다 (유효시간: 15분)",
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 문서 다운로드 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
