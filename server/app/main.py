import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.services.converter import init_whisper_model

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时预加载 Whisper 模型"""
    logger.info("🚀 服务启动中，预加载 Whisper 模型...")
    init_whisper_model()
    logger.info("✅ 服务就绪")
    yield
    logger.info("👋 服务停止")


app = FastAPI(
    title="Online Media to TXT",
    description="在线音频转文字服务 - 下载 MP3 → Whisper 转录 → LLM 整理 → Joplin 同步",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置 - 允许 Chrome 插件访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Chrome 插件使用 chrome-extension:// 协议
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
