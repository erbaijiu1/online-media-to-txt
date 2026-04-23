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

    # 转写并发（强烈建议 CPU 下保持 1，避免 OOM/崩溃）
    MAX_WORKERS: int = 1

    # ===== 超长音频分段转写配置（根治 OOM） =====
    # 是否启用分段转写
    TRANSCRIBE_SEGMENT_ENABLE: bool = True
    # 分段策略：目前实现 duration（固定时长窗口）
    SEGMENT_STRATEGY: str = "duration"
    # 目标分段时长（秒）
    SEGMENT_TARGET_SECONDS: int = 3000
    # 分段重叠（秒），用于缓解跨段断句；后处理可去重
    SEGMENT_OVERLAP_SECONDS: int = 5
    # 小于该时长的段不再切（避免碎片）
    SEGMENT_MIN_SECONDS: int = 30
    # 单段转写最大重试次数
    SEGMENT_MAX_RETRIES: int = 3
    # 重试退避（秒）
    SEGMENT_RETRY_BACKOFF_SEC: float = 2.0

    # Whisper 转写参数
    WHISPER_BEAM_SIZE: int = 1
    WHISPER_VAD_FILTER: bool = True

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
