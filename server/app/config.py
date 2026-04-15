import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置，从环境变量或 .env 文件加载"""

    # LLM 配置 (通义千问)
    DASHSCOPE_API_KEY: str = ""

    # Joplin 配置
    JOPLIN_TOKEN: str = ""
    JOPLIN_HOST: str = "http://host.docker.internal:41184"  # Docker 内访问宿主机 Joplin

    # Whisper 配置
    WHISPER_MODEL_SIZE: str = "small"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"

    # 下载临时目录
    TEMP_AUDIO_DIR: str = "/tmp/temp_audio"

    # 服务配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
