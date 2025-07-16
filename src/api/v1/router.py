from fastapi import APIRouter

from src.auth.router import router as auth_router
from src.chat.router import router as chat_router
from src.documents.admin_router import router as admin_documents_router
from src.documents.download_router import router as download_router
from src.documents.router import router as documents_router
from src.external_services.doc_converter.router import router as doc_converter_router
from src.external_services.doc_parser.router import router as doc_parser_router
from src.monitoring.router import router as monitoring_router
from src.rooms.router import router as rooms_router
from src.search.router import router as search_router
from src.users.router import router as users_router

api_v1_router = APIRouter(prefix="/api/v1")


api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(rooms_router)
api_v1_router.include_router(documents_router)
api_v1_router.include_router(admin_documents_router)
api_v1_router.include_router(search_router)
api_v1_router.include_router(chat_router)
api_v1_router.include_router(monitoring_router)

# 다운로드 라우터 추가
api_v1_router.include_router(download_router)

# 외부 서비스 라우터
api_v1_router.include_router(doc_parser_router)
api_v1_router.include_router(doc_converter_router)
