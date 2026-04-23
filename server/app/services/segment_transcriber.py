import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Segment:
    index: int
    start_sec: float
    end_sec: float
    path: str


def _run_cmd(cmd: List[str]) -> None:
    """Run a command and raise a rich error on failure."""
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode("utf-8", errors="ignore")
        stdout = (e.stdout or b"").decode("utf-8", errors="ignore")
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        ) from e


def probe_duration_seconds(audio_path: str) -> float:
    """Get audio duration (seconds) via ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    out = subprocess.check_output(cmd).decode("utf-8", errors="ignore").strip()
    try:
        return float(out)
    except ValueError as e:
        raise RuntimeError(f"Unable to parse duration from ffprobe output: {out!r}") from e


def build_duration_segments(
    audio_path: str,
    segments_dir: str,
    target_seconds: int,
    overlap_seconds: int,
    min_seconds: int,
) -> List[Segment]:
    """Create fixed-size segments (with overlap) by copying stream via ffmpeg."""
    os.makedirs(segments_dir, exist_ok=True)

    duration = probe_duration_seconds(audio_path)
    if duration <= 0:
        raise RuntimeError("Audio duration is zero")

    step = max(1, int(target_seconds - overlap_seconds))
    if step <= 0:
        raise ValueError("SEGMENT_TARGET_SECONDS must be > SEGMENT_OVERLAP_SECONDS")

    segments: List[Segment] = []
    idx = 0
    start = 0.0
    while start < duration:
        end = min(duration, start + float(target_seconds))
        seg_len = end - start
        if seg_len < float(min_seconds) and segments:
            break

        seg_path = os.path.join(segments_dir, f"seg_{idx:04d}.m4a")
        # Use m4a container (AAC) for smaller temp files; ffmpeg will decode anyway for ASR.
        # -ss before -i + -t is fast seek; good enough for speech.
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            str(start),
            "-t",
            str(seg_len),
            "-i",
            audio_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "aac",
            seg_path,
        ]
        _run_cmd(cmd)

        segments.append(Segment(index=idx, start_sec=start, end_sec=end, path=seg_path))
        idx += 1
        start += float(step)

    return segments


def _manifest_path(work_dir: str) -> str:
    return os.path.join(work_dir, "manifest.json")


def load_manifest(work_dir: str) -> Optional[Dict]:
    p = _manifest_path(work_dir)
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_manifest(work_dir: str, manifest: Dict) -> None:
    p = _manifest_path(work_dir)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def init_or_load_manifest(
    work_dir: str,
    source_audio_path: str,
    segments: List[Segment],
) -> Dict:
    existing = load_manifest(work_dir)
    if existing:
        return existing

    manifest = {
        "version": 1,
        "source": {"path": source_audio_path},
        "segments": [
            {
                "index": s.index,
                "start_sec": s.start_sec,
                "end_sec": s.end_sec,
                "path": s.path,
                "status": "pending",  # pending|done|failed
                "retries": 0,
                "error": None,
                "text_path": os.path.join(work_dir, "segments", f"seg_{s.index:04d}.txt"),
            }
            for s in segments
        ],
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    save_manifest(work_dir, manifest)
    return manifest


def transcribe_segments(
    *,
    model: WhisperModel,
    work_dir: str,
    beam_size: int,
    vad_filter: bool,
    max_retries: int,
    retry_backoff_sec: float,
    on_progress=None,
) -> str:
    """Transcribe all segments described by manifest; returns merged raw text."""
    manifest = load_manifest(work_dir)
    if not manifest:
        raise RuntimeError("manifest.json not found")

    segs = manifest.get("segments", [])
    total = len(segs)
    if total == 0:
        raise RuntimeError("No segments")

    for i, seg in enumerate(segs, start=1):
        if seg.get("status") == "done" and os.path.exists(seg.get("text_path", "")):
            if on_progress:
                on_progress(i - 1, total, f"跳过已完成分段 {seg['index']}")
            continue

        idx = seg["index"]
        seg_path = seg["path"]
        text_path = seg["text_path"]

        last_err = None
        for attempt in range(int(seg.get("retries", 0)), max_retries):
            try:
                if on_progress:
                    on_progress(i - 1, total, f"转写分段 {idx+1}/{total} (attempt {attempt+1})")

                segments_iter, _info = model.transcribe(
                    seg_path,
                    beam_size=beam_size,
                    vad_filter=vad_filter,
                )
                text = "".join([s.text for s in segments_iter]).strip()
                if not text:
                    raise RuntimeError("Empty transcription")

                os.makedirs(os.path.dirname(text_path), exist_ok=True)
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(text)

                seg["status"] = "done"
                seg["error"] = None
                seg["retries"] = attempt
                break
            except Exception as e:
                last_err = str(e)
                seg["status"] = "failed"
                seg["error"] = last_err
                seg["retries"] = attempt + 1
                manifest["updated_at"] = time.time()
                save_manifest(work_dir, manifest)
                if attempt + 1 >= max_retries:
                    raise RuntimeError(f"Segment {idx} failed after retries: {last_err}") from e
                time.sleep(float(retry_backoff_sec))

        manifest["updated_at"] = time.time()
        save_manifest(work_dir, manifest)

        if on_progress:
            done = sum(1 for s in segs if s.get("status") == "done")
            on_progress(done, total, f"完成分段 {idx+1}/{total}")

    # merge
    merged_parts: List[str] = []
    for seg in segs:
        tp = seg.get("text_path")
        if not tp or not os.path.exists(tp):
            continue
        with open(tp, "r", encoding="utf-8") as f:
            merged_parts.append(f.read().strip())

    return "\n".join([p for p in merged_parts if p])

