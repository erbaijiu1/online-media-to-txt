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
from app.services.segment_transcriber import (
    build_duration_segments,
    init_or_load_manifest,
    transcribe_segments,
)

logger = logging.getLogger(__name__)

# 全局任务存储 (内存中，重启会丢失；生产环境可换 Redis)
tasks: Dict[str, dict] = {}

# 线程池 (Whisper 是 CPU 密集型，限制并发)
_settings_for_executor = get_settings()
executor = ThreadPoolExecutor(max_workers=_settings_for_executor.MAX_WORKERS)

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
    
    缓存策略：
    - MP3 已存在则跳过下载
    - _final.txt 已存在则跳过 Whisper + LLM，直接同步 Joplin
    - 只有 Joplin 同步成功后才删除 MP3（保留 txt 备份）
    """
    settings = get_settings()
    temp_dir = settings.TEMP_AUDIO_DIR
    os.makedirs(temp_dir, exist_ok=True)

    # 为每个任务使用独立 workdir，避免 alias 冲突，并支持断点续跑
    safe_alias = alias.replace(os.sep, "_")
    work_dir = os.path.join(temp_dir, safe_alias)
    segments_dir = os.path.join(work_dir, "segments")
    os.makedirs(work_dir, exist_ok=True)

    local_path = os.path.join(work_dir, "source.mp3")
    final_txt_path = os.path.join(work_dir, "final.txt")
    raw_txt_path = os.path.join(work_dir, "raw.txt")

    try:
        final_content = None

        # 检查是否有已处理好的文本文件（之前处理过但 Joplin 同步失败的情况）
        if os.path.exists(final_txt_path):
            logger.info(f"[{task_id}] 📄 发现已处理的文本文件，跳过下载和转录: {final_txt_path}")
            _update_task(task_id, TaskStatus.LLM_PROCESSING, "发现缓存的文本，跳过下载和转录")
            with open(final_txt_path, "r", encoding="utf-8") as f:
                final_content = f.read()
            if final_content.strip():
                logger.info(f"[{task_id}] ✅ 从缓存读取文本，共 {len(final_content)} 字")

        # 如果没有缓存的最终文本，执行完整流程
        if not final_content or not final_content.strip():
            # ===== 1. 下载 MP3 =====
            if os.path.exists(local_path):
                logger.info(f"[{task_id}] ⏩ MP3 已存在，跳过下载: {local_path}")
                _update_task(task_id, TaskStatus.DOWNLOADING, f"MP3 已存在，跳过下载")
            else:
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

            def _on_seg_progress(done: int, total: int, msg: str):
                _update_task(task_id, TaskStatus.TRANSCRIBING, f"{msg} ({done}/{total})")

            if settings.TRANSCRIBE_SEGMENT_ENABLE and settings.SEGMENT_STRATEGY == "duration":
                _update_task(task_id, TaskStatus.TRANSCRIBING, "正在按时长分段并转写（Whisper）...")
                logger.info(
                    f"[{task_id}] 分段转写启用: target={settings.SEGMENT_TARGET_SECONDS}s overlap={settings.SEGMENT_OVERLAP_SECONDS}s"
                )

                # 若 segments 已存在则尽量复用（断点续跑）
                if not os.path.exists(segments_dir) or not os.listdir(segments_dir):
                    segments_list = build_duration_segments(
                        local_path,
                        segments_dir=segments_dir,
                        target_seconds=settings.SEGMENT_TARGET_SECONDS,
                        overlap_seconds=settings.SEGMENT_OVERLAP_SECONDS,
                        min_seconds=settings.SEGMENT_MIN_SECONDS,
                    )
                    init_or_load_manifest(work_dir, local_path, segments_list)
                else:
                    # segments 已存在，但 manifest 可能不存在（兼容手工恢复）
                    # 通过重新探测并重建分段列表（不会覆盖已有文件名规律）
                    segments_list = build_duration_segments(
                        local_path,
                        segments_dir=segments_dir,
                        target_seconds=settings.SEGMENT_TARGET_SECONDS,
                        overlap_seconds=settings.SEGMENT_OVERLAP_SECONDS,
                        min_seconds=settings.SEGMENT_MIN_SECONDS,
                    )
                    init_or_load_manifest(work_dir, local_path, segments_list)

                raw_text = transcribe_segments(
                    model=model,
                    work_dir=work_dir,
                    beam_size=settings.WHISPER_BEAM_SIZE,
                    vad_filter=settings.WHISPER_VAD_FILTER,
                    max_retries=settings.SEGMENT_MAX_RETRIES,
                    retry_backoff_sec=settings.SEGMENT_RETRY_BACKOFF_SEC,
                    on_progress=_on_seg_progress,
                )
            else:
                segments, _ = model.transcribe(
                    local_path,
                    beam_size=settings.WHISPER_BEAM_SIZE,
                    vad_filter=settings.WHISPER_VAD_FILTER,
                )
                raw_text = "\n".join([s.text for s in segments])

            if not raw_text.strip():
                _update_task(task_id, TaskStatus.FAILED, error="音频识别结果为空")
                return

            logger.info(f"[{task_id}] ✅ 转录完成，共 {len(raw_text)} 字")

            with open(raw_txt_path, "w", encoding="utf-8") as f:
                f.write(raw_text)
            logger.info(f"[{task_id}] 💾 已保存原始转录文本: {raw_txt_path}")

            # ===== 3. LLM 文本整理 =====
            _update_task(task_id, TaskStatus.LLM_PROCESSING, "正在调用 LLM 整理文本...")
            logger.info(f"[{task_id}] 开始 LLM 处理...")

            final_content = process_text_with_prompt(raw_text)
            logger.info(f"[{task_id}] ✅ LLM 处理完成")

            # 保存处理后的文本到本地（缓存，防止 Joplin 同步失败后需要重新处理）
            with open(final_txt_path, "w", encoding="utf-8") as f:
                f.write(final_content)
            logger.info(f"[{task_id}] 💾 已保存处理结果: {final_txt_path}")

        # ===== 4. 写入 Joplin =====
        _update_task(task_id, TaskStatus.SYNCING_JOPLIN, "正在同步到 Joplin...")
        logger.info(f"[{task_id}] 开始同步到 Joplin: {joplin_path}")

        joplin = JoplinToolbox(settings.JOPLIN_TOKEN, url=settings.JOPLIN_HOST)
        note_body = f"{final_content}\n\n---\n> **原始音频地址:** {url}"
        sync_result, error_msg = joplin.create_note(
            title=alias,
            body=note_body,
            notebook_path=joplin_path,
            tags=[]
        )

        if sync_result:
            _update_task(task_id, TaskStatus.COMPLETED, "✅ 全部完成！已同步到 Joplin")
            logger.info(f"[{task_id}] ✅ 全部完成")

            # 同步成功后清理 workdir
            try:
                for root, dirs, files in os.walk(work_dir, topdown=False):
                    for name in files:
                        os.remove(os.path.join(root, name))
                    for name in dirs:
                        os.rmdir(os.path.join(root, name))
                os.rmdir(work_dir)
                logger.info(f"[{task_id}] 🗑️ 已清理所有临时文件: {work_dir}")
            except Exception as cleanup_err:
                logger.warning(f"[{task_id}] 清理临时文件失败(可忽略): {cleanup_err}")
        else:
            error_detail = error_msg or "Joplin 同步失败，请检查路径和 Token"
            _update_task(task_id, TaskStatus.FAILED, error=error_detail)
            logger.warning(f"[{task_id}] ⚠️ Joplin 同步失败: {error_detail}，保留所有文件以备重试")

    except requests.exceptions.RequestException as e:
        logger.error(f"[{task_id}] 下载失败: {e}")
        _update_task(task_id, TaskStatus.FAILED, error=f"MP3 下载失败: {str(e)}")
    except Exception as e:
        logger.error(f"[{task_id}] 处理出错: {e}", exc_info=True)
        _update_task(task_id, TaskStatus.FAILED, error=f"处理出错: {str(e)}")
