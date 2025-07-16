from contextlib import asynccontextmanager

import fastapi
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1.router import api_v1_router as v1_router
from src.core.config import settings
from src.core.database import init_db


def start():
    print("service is started.")


def shutdown():
    print("service is stopped.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    start()

    await init_db()

    yield

    shutdown()


def create_app() -> fastapi.FastAPI:
    app_instance = FastAPI(
        lifespan=lifespan,
        title=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        debug=True,
        redirect_slashes=False,
    )

    app_instance.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # health check
    @app_instance.get("/health")
    async def health_check():
        return {"status": "ok"}

    app_instance.include_router(v1_router)

    return app_instance


app = create_app()


if __name__ == "__main__":
    uvicorn.run("main:app", port=8000, host="0.0.0.0", reload=True)
