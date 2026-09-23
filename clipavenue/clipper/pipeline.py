"""ClipPipeline — orchestrate the full clip creation chain.

Chain:
  1. extract_audio()   → ffmpeg WAV
  2. transcribe()      → Transcriber (faster-whisper)
  3. correct_asr()     → CorrectionEngine
  4. segment_text()    → TextSegmenter (ASR knowledge graph)
  5. analyze()         → TranscriptAnalyzer (topic detection)
  6. trim_clips()      → ffmpeg trim
  7. generate_subs()   → ASS subtitles
  8. burn_subs()       → ffmpeg subtitle burn-in
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Optional, Callable

from clipavenue.clipper.correction import CorrectionEngine
from clipavenue.clipper.segmenter import TextSegmenter
from clipavenue.clipper.analyzer import TranscriptAnalyzer
from clipavenue.logger import log
from clipavenue.clipper.metadata import to_simplified_text


# Progress callback type
ProgressCallback = Callable[[str, float], None]


class ClipPipeline:
    """Orchestrates the full clip creation pipeline.

    Each step writes its output to the project directory and updates
    the progress callback. The pipeline is resumable — if a step's
    output already exists, it can be skipped.
    """

    def __init__(
        self,
        project_dir: Path,
        whisper_model: str = "tiny",
        language: str = "zh",
        max_chars_per_line: int = 17,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        self.project_dir = project_dir
        self.whisper_model = whisper_model
        self.language = language
        self.max_chars_per_line = max_chars_per_line
        self.progress_callback = progress_callback

        # Sub-directories
        self.audio_dir = project_dir / "audio"
        self.transcript_dir = project_dir / "transcripts"
        self.clips_dir = project_dir / "clips"
        self.renders_dir = project_dir / "renders"

        # Engines
        self.correction = CorrectionEngine()
        self.segmenter = TextSegmenter(max_chars=max_chars_per_line)
        self.analyzer = TranscriptAnalyzer()

    def _progress(self, stage: str, pct: float) -> None:
        if self.progress_callback:
            self.progress_callback(stage, pct)
        log.info("剪辑", f"[{pct:.0f}%] {stage}")
        self._write_state({"status": "in_progress", "stage": stage, "progress_pct": pct})
    def _write_state(self, extra: dict | None = None) -> None:
        state = {"status": "in_progress", "project_id": self.project_dir.name}
        if extra:
            state.update(extra)
        try:
            path = self.project_dir / "clip_state.json"
            path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Step 1: Extract audio
    # ------------------------------------------------------------------

    def extract_audio(self, video_path: Path) -> Optional[Path]:
        """Extract 16kHz mono WAV from video."""
        log.info("剪辑", f"1/8 提取音频: {video_path.name}")
        log.info("剪辑", f"    源文件: {video_path.stat().st_size // 1024 // 1024} MB")
        self._progress("extract_audio", 0)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.audio_dir / f"{video_path.stem}.wav"

        if output_path.is_file():
            log.info("剪辑", f"    音频已存在: {output_path.name}")
            self._progress("extract_audio", 100)
            return output_path

        log.info("剪辑", f"    输出: {output_path.name}")
        t0 = time.time()
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-i", str(video_path),
                 "-vn", "-acodec", "pcm_s16le",
                 "-ar", "16000", "-ac", "1",
                 str(output_path)],
                capture_output=True, timeout=3600,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            log.error("剪辑", f"    ffmpeg 失败: {exc}")
            return None

        elapsed = time.time() - t0
        size_mb = output_path.stat().st_size / 1024 / 1024 if output_path.is_file() else 0
        log.info("剪辑", f"    音频提取完成: {size_mb:.0f} MB ({elapsed:.0f}s)")
        self._progress("extract_audio", 100)
        return output_path if output_path.is_file() else None

    # ------------------------------------------------------------------
    # Step 2: Transcribe
    # ------------------------------------------------------------------

    def transcribe(self, audio_path: Path) -> Optional[dict]:
        """Run faster-whisper transcription."""
        log.info("剪辑", f"2/8 语音转写: {audio_path.name}")
        size_mb = audio_path.stat().st_size / 1024 / 1024
        log.info("剪辑", f"    音频大小: {size_mb:.0f} MB, 模型: {self.whisper_model}")
        log.info("剪辑", f"    转写耗时取决于音频长度，请耐心等待...")
        self._progress("transcribe", 0)
        self.transcript_dir.mkdir(parents=True, exist_ok=True)

        output_path = self.transcript_dir / f"{audio_path.stem}_transcript.json"
        if output_path.is_file():
            try:
                data = json.loads(output_path.read_text(encoding="utf-8"))
                segs = len(data.get("segments", []))
                log.info("剪辑", f"    转写结果已存在: {segs} 段")
                self._progress("transcribe", 100)
                return data
            except (OSError, json.JSONDecodeError):
                log.warn("剪辑", "    转写文件损坏，重新转写")
                pass

        # 轻量转写(clipavenue.clipper.asr,独立于 OpenMontage)
        try:
            from clipavenue.clipper.asr import Transcriber
            t = Transcriber()
            result = t.execute({
                "input_path": str(audio_path),
                "model_size": self.whisper_model,
                "language": self.language,
                "output_dir": str(self.transcript_dir),
            })
            if not result.success:
                print(f"clipavenue: transcription failed: {result.error}")
                return None
            self._progress("transcribe", 100)
            return result.data
        except Exception as exc:
            print(f"clipavenue: transcriber error: {exc}")
            return None

    # ------------------------------------------------------------------
    # Step 3: Correct ASR
    # ------------------------------------------------------------------

    def correct_asr(self, transcript_data: dict) -> dict:
        """Apply correction dictionary to transcript."""
        log.info("剪辑", "3/8 ASR 校正")
        self._progress("correct_asr", 0)
        corr_file = self.project_dir / "corrections.json"
        if corr_file.is_file():
            n = self.correction.load_json(corr_file)
            log.info("剪辑", f"    加载校正字典: {self.correction.corrections_count} 条")
        else:
            log.info("剪辑", f"    使用默认校正字典: {self.correction.corrections_count} 条")

        corrected = self.correction.correct_transcript(transcript_data)
        segments = corrected.get("segments", [])
        from clipavenue.clipper.correction import correct_transcript_full
        correct_transcript_full(segments, self.correction)
        self._progress("correct_asr", 100)
        return corrected

    # ------------------------------------------------------------------
    # Step 4: Segment text
    # ------------------------------------------------------------------

    def segment_text(self, transcript_data: dict) -> dict:
        """Apply ASR knowledge graph segmentation."""
        log.info("剪辑", "4/8 ASR 知识图谱断句")
        self._progress("segment_text", 0)
        segs = len(transcript_data.get("segments", []))
        segmented = self.segmenter.segment_transcript(transcript_data)
        total_lines = sum(len(s.get("segmented_lines", [])) for s in segmented.get("segments", []))
        log.info("剪辑", f"    断句完成: {segs} 段 -> {total_lines} 行 (每行 ≤{self.max_chars_per_line} 字)")
        self._progress("segment_text", 100)
        return segmented

    # ------------------------------------------------------------------
    # Step 5: Analyze transcript
    # ------------------------------------------------------------------

    def analyze(self, transcript_data: dict) -> dict:
        """Detect topics and suggest clip ranges."""
        log.info("剪辑", "5/8 话题分析")
        self._progress("analyze", 0)
        analysis = self.analyzer.analyze(transcript_data)

        log.info("剪辑", f"    检测到 {analysis['topic_count']} 个话题, {analysis['clip_count']} 个推荐切片")
        for c in analysis.get('suggested_clips', [])[:3]:
            log.info("剪辑", f"       [{c['start']:.0f}s-{c['end']:.0f}s] {c['label'] or '(话题)'}")

        analysis_path = self.project_dir / "clip_analysis.json"
        analysis_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")

        self._progress("analyze", 100)
        return analysis

    # ------------------------------------------------------------------
    # Step 6: Trim clips
    # ------------------------------------------------------------------

    def trim_clips(
        self,
        video_path: Path,
        clips: list[dict],
    ) -> list[Path]:
        """Trim video segments into individual clip files."""
        log.info("剪辑", f"6/8 裁剪视频: {len(clips)} 个切片")
        self._progress("trim_clips", 0)
        self.clips_dir.mkdir(parents=True, exist_ok=True)

        output_paths: list[Path] = []
        total = len(clips)

        for i, clip in enumerate(clips):
            label = clip.get("label", f"clip{i + 1:02d}")
            start = clip.get("start", 0)
            end = clip.get("end", 0)
            duration = end - start
            output_path = self.clips_dir / f"{label}.mp4"

            if output_path.is_file():
                log.info("剪辑", f"    [{i+1}/{total}] {label}: 已存在")
                output_paths.append(output_path)
                continue

            log.info("剪辑", f"    [{i+1}/{total}] {label}: {start:.0f}s-{end:.0f}s ({duration:.0f}s)")
            t0 = time.time()
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error",
                     "-ss", str(start), "-to", str(end),
                     "-i", str(video_path),
                     "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                     "-c:a", "aac", "-b:a", "128k",
                     str(output_path)],
                    capture_output=True, timeout=3600,
                )
                if output_path.is_file():
                    output_paths.append(output_path)
            except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
                print(f"clipavenue: clip trim failed for {label}: {exc}")

            self._progress("trim_clips", (i + 1) / total * 100)

        return output_paths

    # ------------------------------------------------------------------
    # Step 7: Generate subtitles
    # ------------------------------------------------------------------

    def generate_subtitles(
        self,
        transcript_data: dict,
        clips: list[dict],
        video_path: Path,
    ) -> list[Path]:
        """Generate ASS subtitle files for each clip.

        Uses the existing generate_subs.py pattern reimplemented
        for per-clip subtitle generation.
        """
        self._progress("generate_subs", 0)
        self.renders_dir.mkdir(parents=True, exist_ok=True)

        sub_paths: list[Path] = []
        total = len(clips)

        # ── ASS style header ──────────────────────────────────────
        ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,微软雅黑,80,&H00FFFFFF,&H000000FF,&H00E98D8F,&H80000000,1,0,0,0,100,100,0,0,1,6,1,2,100,100,400,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        def _fmt_ts(seconds: float) -> str:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = seconds % 60
            return f"{h}:{m:02d}:{s:05.2f}"

        for i, clip in enumerate(clips):
            clip_start = clip.get("start", 0)
            clip_end = clip.get("end", 0)
            label = clip.get("label", f"clip{i + 1:02d}")
            ass_path = self.renders_dir / f"{label}.ass"

            if ass_path.is_file():
                sub_paths.append(ass_path)
                continue

            # Find transcript segments that overlap this clip
            segments = transcript_data.get("segments", [])
            overlapping = [
                s for s in segments
                if s.get("start", 0) < clip_end and s.get("end", 0) > clip_start
            ]

            # Build ASS events
            ass_lines = [ass_header]
            for seg in overlapping:
                # Use segmented lines if available
                lines = seg.get("segmented_lines") or [seg.get("text", "")]
                for line in lines:
                    if not line.strip():
                        continue
                    rel_start = max(0, seg["start"] - clip_start)
                    rel_end = max(0, seg["end"] - clip_start)
                    if rel_end <= rel_start:
                        rel_end = rel_start + 0.8
                    ass_lines.append(
                        f"Dialogue: 0,{_fmt_ts(rel_start)},{_fmt_ts(rel_end)},"
                        f"Default,,0,0,0,,{line.strip()}\n"
                    )

            ass_path.write_text("".join(ass_lines), encoding="utf-8")
            sub_paths.append(ass_path)
            self._progress("generate_subs", (i + 1) / total * 100)

        return sub_paths

    # ------------------------------------------------------------------
    # Step 8: Burn subtitles
    # ------------------------------------------------------------------

    def burn_subtitles(
        self,
        clip_paths: list[Path],
        sub_paths: list[Path],
    ) -> list[Path]:
        """Burn ASS subtitles into clip videos."""
        log.info("剪辑", f"8/8 压制字幕: {len(clip_paths)} 个视频")
        self._progress("burn_subs", 0)
        output_paths: list[Path] = []
        total = len(clip_paths)
        import shutil

        for i, (clip_path, sub_path) in enumerate(zip(clip_paths, sub_paths)):
            output_path = self.renders_dir / f"{clip_path.stem}_subbed.mp4"
            if output_path.is_file():
                output_paths.append(output_path)
                continue

            # Copy ASS to same dir as clip for simple relative path
            local_ass = clip_path.parent / "subs_temp.ass"
            try:
                shutil.copy2(sub_path, local_ass)
            except OSError:
                local_ass = sub_path

            try:
                r = subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error",
                     "-i", clip_path.name,
                     "-vf", f"subtitles={local_ass.name}:original_size=1080x1920",
                     "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                     "-c:a", "copy",
                     output_path.name],
                    capture_output=True, timeout=3600,
                    cwd=clip_path.parent,
                )
                if r.returncode != 0:
                    err = r.stderr.decode('utf-8', 'replace')[:100]
                    log.warn("剪辑", f"    压制失败: {err}")
                if output_path.is_file():
                    log.info("剪辑", f"    [{i+1}/{total}] {output_path.name}")
                    output_paths.append(output_path)
                else:
                    log.warn("剪辑", f"    未生成: {output_path.name}")
            except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
                log.error("剪辑", f"    压制异常: {exc}")

        for f in clip_path.parent.glob("subs_temp.ass"):
            try: f.unlink()
            except: pass
        log.info("剪辑", f"压制完成: {len(output_paths)}/{total} 个视频")
        return output_paths
    def _generate_clip_meta(
        self, clip_paths: list[Path], suggested_clips: list[dict],
        transcript_data: dict,
    ) -> list[dict]:
        """Generate title, tags, and cover for each clip."""
        from clipavenue.clipper.metadata import generate_clip_meta
        from clipavenue.clipper.correction import detect_context

        all_segments = transcript_data.get("segments", [])
        meta_list = []
        current_context = ""

        for i, (clip_path, clip_def) in enumerate(zip(clip_paths, suggested_clips)):
            # Find matching transcript segments for this clip
            cs, ce = clip_def.get("start", 0), clip_def.get("end", 0)
            segs = [s for s in all_segments if s.get("start", 0) < ce and s.get("end", 0) > cs]

            text = " ".join(s.get("text", "") for s in segs)
            label = clip_def.get("label", "")
            ctx = detect_context(text, label)
            if ctx:
                current_context = ctx

            meta = generate_clip_meta(i + 1, clip_path, segs, current_context, label)
            meta_list.append(meta)
            log.info("剪辑", f"    封面 #{i+1}: {meta['title'][:30]}")

        # Save metadata as JSON
        meta_path = self.project_dir / "clip_metadata.json"
        meta_path.write_text(
            __import__("json").dumps(meta_list, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return meta_list

    def run(self, video_path: Path) -> dict[str, Any]:
        """Run the full clip pipeline on a video file."""
        start_time = time.time()
        log.info("剪辑", "=" * 40)
        log.info("剪辑", f"剪辑流水线启动: {video_path.name}")
        log.info("剪辑", f"视频大小: {video_path.stat().st_size // 1024 // 1024} MB")
        log.info("剪辑", f"项目目录: {self.project_dir}")
        log.info("剪辑", "=" * 40)
        self._progress("start", 0)

        # Step 1: Audio
        log.info("剪辑", "--- 步骤 1/8 ---")
        audio_path = self.extract_audio(video_path)
        if not audio_path:
            log.error("剪辑", "音频提取失败，终止")
            return {"success": False, "error": "audio extraction failed"}
        self._progress("audio_extracted", 15)

        # Step 2: Transcribe
        log.info("剪辑", "--- 步骤 2/8 (最耗时) ---")
        t0 = time.time()
        transcript = self.transcribe(audio_path)
        if not transcript:
            log.error("剪辑", "语音转写失败，终止")
            return {"success": False, "error": "transcription failed"}
        seg_count = len(transcript.get("segments", []))
        log.info("剪辑", f"转写完成: {seg_count} 段, 耗时 {time.time()-t0:.0f}s")
        self._progress("transcribed", 35)

        # Step 3: Correct ASR
        log.info("剪辑", "--- 步骤 3/8 ---")
        transcript = self.correct_asr(transcript)
        self._progress("corrected", 45)

        # Step 4: Segment text
        log.info("剪辑", "--- 步骤 4/8 ---")
        transcript = self.segment_text(transcript)
        self._progress("segmented", 55)

        # Step 5: Analyze
        log.info("剪辑", "--- 步骤 5/8 ---")
        analysis = self.analyze(transcript)
        self._progress("analyzed", 65)

        suggested_clips = analysis.get("suggested_clips", [])
        if not suggested_clips:
            log.warn("剪辑", "未检测到可剪辑片段")
            return {
                "success": True,
                "warning": "no clip suggestions found",
                "analysis": analysis,
                "transcript": transcript,
            }
        log.info("剪辑", f"建议剪辑: {len(suggested_clips)} 个片段")

        # Step 6: Trim clips
        log.info("剪辑", "--- 步骤 6/8 ---")
        clip_paths = self.trim_clips(video_path, suggested_clips)
        self._progress("clips_trimmed", 80)

        # Step 7: Generate subtitles
        log.info("剪辑", "--- 步骤 7/8 ---")
        sub_paths = self.generate_subtitles(transcript, suggested_clips, video_path)
        self._progress("subtitles_generated", 90)

        # Step 8: Burn subtitles
        log.info("剪辑", "--- 步骤 8/8 ---")
        rendered_paths = self.burn_subtitles(clip_paths, sub_paths)
        self._progress("subtitled", 92)

        # Step 9: Generate metadata (titles, tags, covers)
        log.info("剪辑", "--- 步骤 9/9 ---")
        clip_meta = self._generate_clip_meta(
            clip_paths, suggested_clips, transcript,
        )
        self._progress("completed", 100)

        elapsed = time.time() - start_time

        # Write pipeline result
        result = {
            "success": True,
            "video_source": str(video_path),
            "audio": str(audio_path) if audio_path else None,
            "transcript_segments": len(transcript.get("segments", [])),
            "clip_count": len(suggested_clips),
            "clips": [str(p) for p in clip_paths],
            "subtitles": [str(p) for p in sub_paths],
            "rendered": [str(p) for p in rendered_paths],
            "topics": analysis.get("topics", []),
            "duration_seconds": round(elapsed, 1),
            "meta": clip_meta,
        }

        # Write clip state file for dashboard
        state_path = self.project_dir / "clip_state.json"
        state_path.write_text(
            json.dumps({
                "status": "completed",
                "clips": suggested_clips,
                "result": result,
                "timestamp": time.time(),
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return result