import asyncio
import logging
from typing import AsyncGenerator, List, Type

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, text
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.config import settings

# 로깅 설정
logger = logging.getLogger(__name__)

async_engine = create_async_engine(settings.DATABASE_URL, echo=False)


def auto_discover_models() -> List[Type[SQLModel]]:
    """
    🔍 새로운 통합 모델 사용
    """
    models = []

    try:
        # 🎯 새로운 통합 모델만 import
        from src.models import Chunk, Document, Room, TokenUsage, User

        # 📋 모델 클래스 목록
        model_classes = [
            User,
            Room,
            Document,
            Chunk,
            TokenUsage,
        ]

        # ✅ 유효한 모델만 등록
        for model_class in model_classes:
            if hasattr(model_class, "__tablename__"):
                models.append(model_class)
                print(f"✅ 모델 등록: {model_class.__name__}")

        print(f"🎯 총 {len(models)}개 모델 등록 완료!")

    except ImportError as e:
        print(f"❌ 모델 import 실패: {e}")

    return models


async def init_db():
    """
    🛠️ 데이터베이스 초기화

    테이블 생성, 인덱스 생성, 트리거 설정, 초기 데이터 삽입을 한 번에 처리합니다.
    """
    # 🔄 DB 연결 재시도 로직
    max_retries = 2
    retry_interval = 2

    for attempt in range(max_retries):
        try:
            logger.info(f"🔗 데이터베이스 연결 시도 {attempt + 1}/{max_retries}")

            # 🔍 모델 자동 발견 및 등록
            discovered_models = auto_discover_models()
            print(f"📊 발견된 모델 수: {len(discovered_models)}")

            # 🏗️ 데이터베이스 테이블 생성
            async with async_engine.begin() as conn:
                # 🚀 pgvector 확장 활성화
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                print("🔌 pgvector 확장 활성화 완료")

                # 📋 모든 테이블 생성
                await conn.run_sync(SQLModel.metadata.create_all)
                print("🏗️ 데이터베이스 테이블 생성 완료")

                # 🚀 HNSW 벡터 인덱스 생성 (성능 최적화)
                await conn.execute(
                    text("""
                    CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx 
                    ON chunks 
                    USING hnsw (embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64);
                """)
                )

                print("⚡ HNSW 벡터 인덱스 생성 완료 (검색 성능 최적화)")

                # ⏰ updated_at 자동 업데이트 트리거 함수 생성
                await conn.execute(
                    text("""
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = now();
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                """)
                )

                # 📝 updated_at 컬럼이 있는 테이블들 찾기
                table_names = []

                def collect_table_names(metadata):
                    for table in metadata.tables.values():
                        if "updated_at" in table.columns:
                            table_names.append(table.name)

                await conn.run_sync(
                    lambda sync_conn: collect_table_names(SQLModel.metadata)
                )

                # 🔄 각 테이블에 대해 트리거 생성
                for table_name in table_names:
                    # 🗑️ 기존 트리거 삭제
                    await conn.execute(
                        text(
                            f"DROP TRIGGER IF EXISTS update_updated_at_trigger ON {table_name};"
                        )
                    )

                    # ➕ 새 트리거 생성
                    await conn.execute(
                        text(f"""
                    CREATE TRIGGER update_updated_at_trigger
                    BEFORE UPDATE ON {table_name}
                    FOR EACH ROW
                    EXECUTE FUNCTION update_updated_at_column();
                    """)
                    )

                print(f"⏰ {len(table_names)}개 테이블에 updated_at 트리거 생성 완료")

            # 🎯 초기 데이터 삽입
            await insert_initial_data()

            print("🎉 데이터베이스 초기화 완료!")
            logger.info("✅ 데이터베이스 연결 및 초기화 성공!")
            break

        except Exception as e:
            logger.warning(
                f"❌ 데이터베이스 연결 실패 (시도 {attempt + 1}/{max_retries}): {e}"
            )
            if attempt == max_retries - 1:
                logger.error("🚨 최대 재시도 횟수 초과. 데이터베이스 연결 실패!")
                raise
            await asyncio.sleep(retry_interval)


async def insert_initial_data():
    """
    📋 초기 데이터 삽입

    문서 유형, 관리자 계정 등을 DB에 삽입합니다.
    """
    from src.core.initial_data import insert_all_initial_data

    async_session = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        await insert_all_initial_data(session)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    🔗 데이터베이스 세션 생성

    비동기 세션을 생성하여 데이터베이스 작업을 수행합니다.
    """
    async_session = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session() as session:
        yield session
