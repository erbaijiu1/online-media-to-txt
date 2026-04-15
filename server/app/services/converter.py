import os
import uuid
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

import requests
from faster_whisper import WhisperModel

from app.config import get_settings
from app.models.schemas import TaskStatus
from app.tools.model_deal import process_text_with_prompt
from app.tools.joplinUtil import JoplinToolbox

logger = logging.getLogger(__name__)

# 全局任务存储 (内存中，重启会丢失；生产环境可换 Redis)
tasks: Dict[str, dict] = {}

# 线程池 (Whisper 是 CPU 密集型，限制并发)
executor = ThreadPoolExecutor(max_workers=2)

# 全局 Whisper 模型 (启动时加载一次)
_whisper_model: WhisperModel = None


def init_whisper_model():
    """启动时预加载 Whisper 模型"""
    global _whisper_model
    settings = get_settings()
    logger.info(f"正在加载 Whisper 模型: {settings.WHISPER_MODEL_SIZE} (device={settings.WHISPER_DEVICE})...")
    _whisper_model = WhisperModel(
        settings.WHISPER_MODEL_SIZE,
        device=settings.WHISPER_DEVICE,
        compute_type=settings.WHISPER_COMPUTE_TYPE
    )
    logger.info("✅ Whisper 模型加载完成")


def get_whisper_model() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        init_whisper_model()
    return _whisper_model


def is_whisper_loaded() -> bool:
    return _whisper_model is not None


def submit_task(url: str, alias: str, joplin_path: str) -> str:
    """
    提交一个转换任务，立即返回 task_id。
    实际工作在后台线程中执行。
    """
    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {
        "task_id": task_id,
        "status": TaskStatus.PENDING,
        "progress": "排队中...",
        "error": None,
        "created_at": datetime.now(),
        "completed_at": None,
    }

    # 提交到线程池
    executor.submit(_run_conversion, task_id, url, alias, joplin_path)
    return task_id


def get_task_status(task_id: str) -> dict:
    """查询任务状态"""
    return tasks.get(task_id)


def _update_task(task_id: str, status: TaskStatus, progress: str = "", error: str = None):
    """更新任务状态"""
    if task_id in tasks:
        tasks[task_id]["status"] = status
        tasks[task_id]["progress"] = progress
        if error:
            tasks[task_id]["error"] = error
        if status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            tasks[task_id]["completed_at"] = datetime.now()


def _run_conversion(task_id: str, url: str, alias: str, joplin_path: str):
    """
    后台执行完整的转换流程：
    下载 MP3 → Whisper 转录 → LLM 整理 → 写入 Joplin
    """
    settings = get_settings()
    temp_dir = settings.TEMP_AUDIO_DIR
    os.makedirs(temp_dir, exist_ok=True)

    local_path = os.path.join(temp_dir, f"{alias}.mp3")

    try:
        # ===== 1. 下载 MP3 =====
        _update_task(task_id, TaskStatus.DOWNLOADING, f"正在下载: {alias}")
        logger.info(f"[{task_id}] 开始下载: {url}")

        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()

        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(f"[{task_id}] ✅ 下载完成: {local_path}")

        # ===== 2. Whisper 转文字 =====
        _update_task(task_id, TaskStatus.TRANSCRIBING, "正在识别音频内容（Whisper）...")
        logger.info(f"[{task_id}] 开始 Whisper 转录...")

        model = get_whisper_model()
        segments, _ = model.transcribe(local_path, beam_size=1, vad_filter=True)
        raw_text = "\n".join([s.text for s in segments])

        if not raw_text.strip():
            _update_task(task_id, TaskStatus.FAILED, error="音频识别结果为空")
            return

        logger.info(f"[{task_id}] ✅ 转录完成，共 {len(raw_text)} 字")

        # ===== 3. LLM 文本整理 =====
        _update_task(task_id, TaskStatus.LLM_PROCESSING, "正在调用 LLM 整理文本...")
        logger.info(f"[{task_id}] 开始 LLM 处理...")

        final_content = process_text_with_prompt(raw_text)
        logger.info(f"[{task_id}] ✅ LLM 处理完成")

        # ===== 4. 写入 Joplin =====
        _update_task(task_id, TaskStatus.SYNCING_JOPLIN, "正在同步到 Joplin...")
        logger.info(f"[{task_id}] 开始同步到 Joplin: {joplin_path}")

        joplin = JoplinToolbox(settings.JOPLIN_TOKEN, url=settings.JOPLIN_HOST)
        note_body = f"{final_content}\n\n---\n> **原始音频地址:** {url}"
        sync_result = joplin.create_note(
            title=alias,
            body=note_body,
            notebook_path=joplin_path,
            tags=[]
        )

        if sync_result:
            _update_task(task_id, TaskStatus.COMPLETED, "✅ 全部完成！已同步到 Joplin")
            logger.info(f"[{task_id}] ✅ 全部完成")
        else:
            _update_task(task_id, TaskStatus.FAILED, error="Joplin 同步失败，请检查路径和 Token")

    except requests.exceptions.RequestException as e:
        logger.error(f"[{task_id}] 下载失败: {e}")
        _update_task(task_id, TaskStatus.FAILED, error=f"MP3 下载失败: {str(e)}")
    except Exception as e:
        logger.error(f"[{task_id}] 处理出错: {e}", exc_info=True)
        _update_task(task_id, TaskStatus.FAILED, error=f"处理出错: {str(e)}")
    finally:
        # 清理临时文件
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
                logger.info(f"[{task_id}] 🗑️ 已清理临时文件")
            except OSError:
                pass
