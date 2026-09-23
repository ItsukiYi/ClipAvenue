"""asr — 轻量语音转写(替代 OpenMontage 的 tools.analysis.transcriber)。

独立实现:仅依赖 faster-whisper。接口与旧 Transcriber 兼容:
    t = Transcriber()
    result = t.execute({"input_path": "...", "model_size": "tiny",
                        "language": "zh", "output_dir": "..."})
    result.success / result.error / result.data["segments"]

data["segments"] 每项: {"start": 秒, "end": 秒, "text": "..."}(另有 id)。
写出的 JSON 路径:<output_dir>/<stem>_transcript.json
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional


class ToolResult:
    def __init__(self, success: bool, data: Optional[dict] = None, error: str = ""):
        self.success = success
        self.data = data or {}
        self.error = error


class Transcriber:
    name = "transcriber"
    provider = "faster-whisper"

    def execute(self, params: dict) -> ToolResult:
        input_path = params.get("input_path", "")
        model_size = params.get("model_size", "tiny")
        language = params.get("language", "zh")
        output_dir = params.get("output_dir", ".")

        if not input_path or not Path(input_path).is_file():
            return ToolResult(False, error=f"input not found: {input_path}")

        ip = Path(input_path)
        od = Path(output_dir)
        od.mkdir(parents=True, exist_ok=True)
        out_path = od / f"{ip.stem}_transcript.json"
        if out_path.is_file():
            try:
                data = json.loads(out_path.read_text(encoding="utf-8"))
                return ToolResult(True, data=data)
            except (OSError, json.JSONDecodeError):
                pass

        try:
            # 国内网络: 优先走 HuggingFace 镜像
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            from faster_whisper import WhisperModel

            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            t0 = time.time()
            segments_iter, info = model.transcribe(
                str(ip),
                language=language,
                vad_filter=True,
                beam_size=5,
            )
            segments = []
            for seg in segments_iter:
                segments.append({
                    "id": len(segments),
                    "start": round(float(seg.start), 3),
                    "end": round(float(seg.end), 3),
                    "text": seg.text.strip(),
                })
            data = {"segments": segments, "language": getattr(info, "language", language)}
            out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return ToolResult(True, data=data)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, error=f"transcribe failed: {exc}")


def transcribe(audio_path: str, project_dir: str, model_size: str = "tiny", language: str = "zh") -> ToolResult:
    """便捷入口: 与 clip_tools.transcribe 相同的调用姿势。"""
    return Transcriber().execute({
        "input_path": audio_path,
        "model_size": model_size,
        "language": language,
        "output_dir": project_dir,
    })