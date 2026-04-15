from pydantic import BaseModel
from enum import Enum
from typing import Optional
from datetime import datetime


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    LLM_PROCESSING = "llm_processing"
    SYNCING_JOPLIN = "syncing_joplin"
    COMPLETED = "completed"
    FAILED = "failed"


class ConvertRequest(BaseModel):
    """转换请求"""
    url: str                    # MP3 在线地址
    alias: str                  # 笔记标题 / 文件别名
    joplin_path: str            # Joplin 笔记本路径，例如 "Project/stock/不惑少年/直播"


class ConvertResponse(BaseModel):
    """转换响应 - 提交后立即返回"""
    task_id: str
    message: str = "任务已提交"


class TaskStatusResponse(BaseModel):
    """任务状态查询响应"""
    task_id: str
    status: TaskStatus
    progress: str = ""          # 当前进度描述
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = "ok"
    whisper_model_loaded: bool = False


class JoplinWriteRequest(BaseModel):
    """直接写入 Joplin 的请求"""
    title: str                  # 笔记标题
    body: str                   # 笔记内容
    joplin_path: str            # Joplin 笔记本路径
    tags: Optional[list] = []   # 标签列表 (可选)
