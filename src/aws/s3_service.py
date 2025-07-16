import logging
import urllib.parse
import uuid
from datetime import datetime
from typing import Optional

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile, status

from ..core.config import settings

logger = logging.getLogger(__name__)


class S3Service:
    """S3 파일 관리 서비스"""

    def __init__(
        self,
        region_name: str,
        default_bucket: str,
    ):
        self.session = aioboto3.Session()
        self.region_name = region_name
        self.default_bucket = default_bucket

    def generate_s3_key(
        self, doc_type_obj, filename: str, prefix: str = "legal-docs"
    ) -> str:
        """S3 키 생성 (DocType 객체 기반)"""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]

        # DocType 객체에서 직접 값 가져오기 (매핑 제거)
        doc_type = doc_type_obj.type.value  # contract, law, legal_case 등
        category = doc_type_obj.name  # nda, civil-law, supreme-court 등

        # 파일명 안전하게 처리
        safe_filename = self._sanitize_filename(filename)

        return f"{prefix}/{doc_type}/{category}/{timestamp}_{unique_id}_{safe_filename}"

    def generate_contract_s3_key(
        self, contract_id: int, version: str, filename: str
    ) -> str:
        """계약서 전용 S3 키 생성 (계약 ID 기반 폴더 구조)"""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = self._sanitize_filename(filename)

        return f"contracts/{contract_id}/{version}_{timestamp}_{safe_filename}"

    def _sanitize_filename(self, filename: str) -> str:
        """파일명을 S3 키에 안전하게 사용할 수 있도록 처리"""
        # 파일 확장자 분리
        name_parts = filename.rsplit(".", 1)
        base_name = name_parts[0] if len(name_parts) > 1 else filename
        extension = f".{name_parts[1]}" if len(name_parts) > 1 else ""

        # 한국어 및 특수문자를 URL 인코딩
        encoded_base = urllib.parse.quote(base_name, safe="")

        # 너무 긴 경우 잘라내기 (S3 키 제한: 1024자)
        if len(encoded_base) > 100:
            encoded_base = encoded_base[:100]

        return f"{encoded_base}{extension}"

    async def upload_file(
        self,
        file: UploadFile,
        s3_key: str,
        bucket: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> dict:
        """파일을 S3에 업로드"""
        bucket = bucket or self.default_bucket
        content_type = content_type or file.content_type or "application/pdf"

        try:
            async with self.session.client(  # type: ignore
                "s3",
                region_name=self.region_name,
                config=Config(signature_version="s3v4"),
            ) as s3_client:
                # 파일 내용 읽기
                file_content = await file.read()

                # 파일 크기 로깅
                logger.info(
                    f"S3 업로드: {file.filename} -> {s3_key}, 크기: {len(file_content)} bytes"
                )

                # 파일 내용이 비어있는지 확인
                if len(file_content) == 0:
                    logger.error(f"파일 내용이 비어있음: {file.filename}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"파일 내용이 비어있습니다: {file.filename}",
                    )

                # S3 메타데이터용 ASCII 파일명 생성
                ascii_filename = urllib.parse.quote(
                    file.filename or "unknown.pdf", safe=""
                )

                # S3에 업로드
                await s3_client.put_object(
                    Bucket=bucket,
                    Key=s3_key,
                    Body=file_content,
                    ContentType=content_type,
                    Metadata={
                        "original_filename_encoded": ascii_filename,
                        "upload_timestamp": datetime.now().isoformat(),
                    },
                )

                # 파일 포인터 리셋 (다른 곳에서 재사용 가능)
                await file.seek(0)

                logger.info(f"S3 업로드 성공: {s3_key} ({len(file_content)} bytes)")

                return {
                    "success": True,
                    "bucket": bucket,
                    "key": s3_key,
                    "file_size": len(file_content),
                    "content_type": content_type,
                }

        except ClientError as e:
            logger.error(f"S3 업로드 실패: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"파일 업로드에 실패했습니다: {str(e)}",
            )

    async def generate_download_url(
        self,
        s3_key: str,
        bucket: Optional[str] = None,
        expires_in: int = 3600,  # 1시간
        filename: Optional[str] = None,
        file_type: Optional[str] = None,  # 추가: 'inline' 지원
    ) -> str:
        """다운로드용 Presigned URL 생성"""
        bucket = bucket or self.default_bucket

        try:
            async with self.session.client(  # type: ignore
                "s3",
                region_name=self.region_name,
                config=Config(signature_version="s3v4"),
            ) as s3_client:
                # Presigned URL 생성
                content_disposition = None
                if file_type == "inline":
                    content_disposition = "inline"
                # else: None (지정하지 않음)
                params = {
                    "Bucket": bucket,
                    "Key": s3_key,
                }
                if content_disposition:
                    params["ResponseContentDisposition"] = content_disposition

                url = await s3_client.generate_presigned_url(
                    "get_object", Params=params, ExpiresIn=expires_in
                )

                return url

        except ClientError as e:
            logger.error(f"Presigned URL 생성 실패: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"다운로드 URL 생성에 실패했습니다: {str(e)}",
            )

    async def delete_file(self, s3_key: str, bucket: Optional[str] = None) -> bool:
        """S3에서 파일 삭제"""
        bucket = bucket or self.default_bucket

        try:
            async with self.session.client(  # type: ignore
                "s3",
                region_name=self.region_name,
                config=Config(signature_version="s3v4"),
            ) as s3_client:
                await s3_client.delete_object(Bucket=bucket, Key=s3_key)
                return True

        except ClientError as e:
            logger.error(f"S3 파일 삭제 실패: {str(e)}")
            return False

    async def file_exists(self, s3_key: str, bucket: Optional[str] = None) -> bool:
        """S3에 파일이 존재하는지 확인"""
        bucket = bucket or self.default_bucket

        try:
            async with self.session.client(  # type: ignore
                "s3",
                region_name=self.region_name,
                config=Config(signature_version="s3v4"),
            ) as s3_client:
                await s3_client.head_object(Bucket=bucket, Key=s3_key)
                return True

        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            logger.error(f"S3 파일 존재 확인 실패: {str(e)}")
            return False


# 싱글톤 인스턴스
s3_service = S3Service(
    region_name=settings.AWS_REGION, default_bucket=settings.S3_BUCKET_NAME
)
