from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    ConvertRequest,
    ConvertResponse,
    TaskStatusResponse,
    HealthResponse,
)
from app.services.converter import submit_task, get_task_status, is_whisper_loaded

router = APIRouter(prefix="/api", tags=["convert"])


@router.post("/convert", response_model=ConvertResponse)
async def convert_audio(req: ConvertRequest):
    """
    提交一个 MP3 转文字任务。
    立即返回 task_id，后台异步处理。
    """
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="URL 不能为空")
    if not req.alias.strip():
        raise HTTPException(status_code=400, detail="标题不能为空")
    if not req.joplin_path.strip():
        raise HTTPException(status_code=400, detail="Joplin 路径不能为空")

    task_id = submit_task(
        url=req.url.strip(),
        alias=req.alias.strip(),
        joplin_path=req.joplin_path.strip()
    )

    return ConvertResponse(task_id=task_id, message="任务已提交，正在后台处理")


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def query_task(task_id: str):
    """查询任务状态"""
    task = get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskStatusResponse(**task)


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    return HealthResponse(
        status="ok",
        whisper_model_loaded=is_whisper_loaded()
    )
