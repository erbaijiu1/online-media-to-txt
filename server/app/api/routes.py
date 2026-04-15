from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    ConvertRequest,
    ConvertResponse,
    TaskStatusResponse,
    HealthResponse,
    JoplinWriteRequest,
)
from app.services.converter import submit_task, get_task_status, is_whisper_loaded
from app.tools.joplinUtil import JoplinToolbox

from app.config import get_settings

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


@router.post("/joplin/write")
async def write_to_joplin(req: JoplinWriteRequest):
    """
    直接写入内容到 Joplin。
    支持传入路径、标题、内容和标签。
    """
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="标题不能为空")
    if not req.body.strip():
        raise HTTPException(status_code=400, detail="内容不能为空")
    if not req.joplin_path.strip():
        raise HTTPException(status_code=400, detail="Joplin 路径不能为空")

    try:
        # 初始化 Joplin 工具
        settings = get_settings()

        joplin_tool = JoplinToolbox(settings.JOPLIN_TOKEN, url=settings.JOPLIN_HOST)

        # 创建笔记
        note_id, error_msg = joplin_tool.create_note(
            title=req.title.strip(),
            body=req.body.strip(),
            notebook_path=req.joplin_path.strip(),
            tags=req.tags or []
        )
        
        if note_id:
            return {
                "success": True,
                "note_id": note_id,
                "message": f"成功同步到 Joplin: {req.title}"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=error_msg or "写入 Joplin 失败，请检查路径是否正确或 Joplin 服务是否运行"
            )
            
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入失败: {str(e)}")
