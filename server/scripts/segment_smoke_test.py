import os
import tempfile

from faster_whisper import WhisperModel

from app.services.segment_transcriber import (
    build_duration_segments,
    init_or_load_manifest,
    transcribe_segments,
)


def main() -> None:
    # Generate a short test audio with macOS `say` + ffmpeg
    with tempfile.TemporaryDirectory() as td:
        aiff_path = os.path.join(td, "tts.aiff")
        audio_path = os.path.join(td, "tts.mp3")

        text = "Hello. This is a segmentation smoke test for whisper transcription."
        rc = os.system(f"say -o {aiff_path} {text!r}")
        if rc != 0:
            raise RuntimeError("Failed to run `say` (macOS required)")

        rc = os.system(
            f"ffmpeg -hide_banner -loglevel error -y -i {aiff_path} -ac 1 -ar 16000 {audio_path}"
        )
        if rc != 0:
            raise RuntimeError("Failed to convert TTS audio with ffmpeg")

        work_dir = os.path.join(td, "work")
        segments_dir = os.path.join(work_dir, "segments")
        os.makedirs(work_dir, exist_ok=True)

        segments = build_duration_segments(
            audio_path,
            segments_dir=segments_dir,
            target_seconds=7,
            overlap_seconds=2,
            min_seconds=3,
        )
        init_or_load_manifest(work_dir, audio_path, segments)

        model = WhisperModel("tiny", device="cpu", compute_type="int8")

        def on_progress(done: int, total: int, msg: str):
            print(f"[{done}/{total}] {msg}")

        raw = transcribe_segments(
            model=model,
            work_dir=work_dir,
            beam_size=1,
            vad_filter=True,
            max_retries=2,
            retry_backoff_sec=0.2,
            on_progress=on_progress,
        )

        if not raw.strip():
            raise RuntimeError("Transcription is empty; smoke test failed")

        print("OK. RAW_LEN=", len(raw))


if __name__ == "__main__":
    main()


