"""ClipAvenue Clipper — auto-clip pipeline.

Orchestrates: audio extraction → transcription → ASR correction →
topic analysis → video clipping → subtitle generation → subtitle burn-in.
"""

from clipavenue.clipper.pipeline import ClipPipeline
from clipavenue.clipper.correction import CorrectionEngine
from clipavenue.clipper.analyzer import TranscriptAnalyzer
from clipavenue.clipper.segmenter import TextSegmenter

__all__ = ["ClipPipeline", "CorrectionEngine", "TranscriptAnalyzer", "TextSegmenter"]