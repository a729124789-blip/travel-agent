"""
FastAPI 应用入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动/关闭时执行"""
    logger.info(f"🚀 {settings.app_name} v{settings.app_version} 启动中...")
    logger.info(f"📖 API 文档: http://localhost:{settings.port}/docs")
    yield
    logger.info("👋 应用关闭")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="基于 LangGraph + RAG 的智能旅行规划助手 API",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy", "service": settings.app_name}


# 路由注册
from app.api.routes import chat, chat_api
app.include_router(chat.router, prefix="/api")
app.include_router(chat_api.router, prefix="/api")
