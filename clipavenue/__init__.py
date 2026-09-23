"""ClipAvenue — livestream recording-to-publishing pipeline.

A self-contained dashboard for managing:
  Live recording → Storage management → Auto-clipping → Upload → Archive

Independent project(自 2026-09-22 起脱离 OpenMontage):
语音转写由 clipavenue.clipper.asr(faster-whisper)提供,
规范路径由 clipavenue.lib_paths 提供。
"""

DEFAULT_PORT = 4850