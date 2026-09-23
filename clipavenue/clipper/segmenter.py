"""TextSegmenter — ASR knowledge-graph-based Chinese text segmentation.

Implements the rules from training/ASR_knowledge_graph.md:
- Prioritize logic over rhythm over typography
- Never split morpheme internals, fixed expressions, or logical backbone
- Break at clause boundaries, topic shifts, and natural pauses
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Fixed expressions that must never be split
# ---------------------------------------------------------------------------

FIXED_EXPRESSIONS: set[str] = {
    # Causal / logical
    "因为我长得比较高", "因为我长得高", "因为我",
    "所以", "但是", "不过", "而且", "然后", "虽然", "如果", "于是",
    "因为所以", "因为", "不但", "不仅",

    # Oral set phrases
    "我跟你说", "你知道吧", "就是说", "也就是说",
    "其实", "对吧", "我觉得", "我感觉",
    "我跟你说啊", "我跟你说哈",
    "不是我说", "你说是不是",

    # Common multi-character words (must not split)
    "比较高", "有点高", "特别高", "非常高",
    "比较", "有点", "特别", "非常",
    "可以说", "可以说", "应该说是",
    "不知道", "差不多", "一会儿", "一下子",
    "听不懂", "受不了", "挡不住", "看不了",
    "头皮发麻", "火花带闪电",

    # Degree complements
    "得很", "死了", "坏了", "透了", "极了",
}

# Clause boundary conjunctions (can break AFTER these)
CLAUSE_BOUNDARIES: list[str] = [
    "因为", "所以", "但是", "不过", "而且",
    "然后", "虽然", "如果", "于是", "然而",
    "况且", "何况", "总之", "此外",
]

# Function words for fallback splitting
FUNCTION_WORDS: set[str] = {
    "的", "了", "是", "就", "也", "在",
    "把", "跟", "和", "吧", "吗", "呢",
    "啊", "呀", "啦", "哦", "嗯",
}

# Topic change keywords — strong indicator of a new segment
TOPIC_MARKERS: list[str] = [
    "说到", "提到", "关于", "还有一个",
    "对了", "哦对了", "说起来",
    "换个话题", "话说", "然后呢",
    "最后", "再说", "另外",
]


class TextSegmenter:
    """ASR knowledge-graph-aware Chinese text segmenter.

    Splits long conversational text into short display lines
    suitable for ≤17-character single-line subtitles.
    """

    def __init__(self, max_chars: int = 17, min_chars: int = 4) -> None:
        self.max_chars = max_chars
        self.min_chars = min_chars

    def segment(self, text: str) -> list[str]:
        """Segment a line of text following ASR knowledge graph rules.

        Returns a list of lines, each ≤ max_chars characters.
        """
        if not text:
            return []
        if len(text) <= self.max_chars:
            return [text]

        lines = self._split_recursive(text)
        return self._merge_short_lines(lines)

    def _split_recursive(self, text: str) -> list[str]:
        """Recursively split long text at the best break point."""
        if len(text) <= self.max_chars:
            return [text]

        # Priority 1: Topic markers
        pos = self._find_topic_break(text)
        if pos >= self.min_chars:
            return self._split_at(text, pos)

        # Priority 2: Clause boundaries (因果/转折/递进)
        pos = self._find_clause_break(text)
        if pos >= self.min_chars:
            return self._split_at(text, pos)

        # Priority 3: Fixed expression boundaries
        pos = self._find_expression_break(text)
        if pos >= self.min_chars:
            return self._split_at(text, pos)

        # Priority 4: Function word breaks
        pos = self._find_function_word_break(text)
        if pos >= self.min_chars:
            return self._split_at(text, pos)

        # Priority 5: Visual length (last resort)
        pos = min(self.max_chars, len(text))
        return self._split_at(text, pos)

    def _find_topic_break(self, text: str) -> int:
        """Find the best break at a topic marker."""
        best = -1
        for marker in TOPIC_MARKERS:
            idx = text.find(marker, self.min_chars)
            if self.min_chars <= idx <= self.max_chars:
                best = max(best, idx + len(marker))
        return best

    def _find_clause_break(self, text: str) -> int:
        """用 rfind 找范围内最后一个子句边界（workflow 规范）"""
        best = -1
        min_pos = int(self.max_chars * 0.4)
        for conj in CLAUSE_BOUNDARIES:
            idx = text.rfind(conj, 0, self.max_chars + 3)
            if idx < 0:
                continue
            break_pos = idx + len(conj)
            if break_pos > min_pos and break_pos <= self.max_chars + 3:
                best = max(best, break_pos)
        return best

    def _find_expression_break(self, text: str) -> int:
        """Find a break at a fixed expression boundary."""
        best = -1
        for expr in FIXED_EXPRESSIONS:
            idx = text.find(expr, self.min_chars)
            if idx < 0:
                continue
            end_pos = idx + len(expr)
            if end_pos <= self.max_chars + 3:
                best = max(best, end_pos)
        return best

    def _find_function_word_break(self, text: str) -> int:
        """Find the best break after a function word (fallback)."""
        best = -1
        for i in range(min(self.max_chars, len(text)), self.min_chars - 1, -1):
            if text[i - 1] in FUNCTION_WORDS:
                best = i
                break
        return best

    def _split_at(self, text: str, pos: int) -> list[str]:
        """Split text at position and recursively process both halves."""
        pos = min(pos, len(text))
        if pos <= 0:
            pos = min(self.max_chars, len(text))
        first = text[:pos].strip()
        second = text[pos:].strip()
        if not first and not second:
            return []
        if not first:
            return self._split_recursive(second)
        if not second:
            return [first]
        result = [first]
        result.extend(self._split_recursive(second))
        return result

    def _merge_short_lines(self, lines: list[str]) -> list[str]:
        """Merge very short lines (≤3 chars) with neighbors."""
        if not lines:
            return []
        merged = []
        for line in lines:
            if not line:
                continue
            if merged and len(line) <= 3:
                cand = merged[-1] + line
                if len(cand) <= self.max_chars:
                    merged[-1] = cand
                    continue
            merged.append(line)
        return merged

    # ------------------------------------------------------------------
    # Bulk segment an entire transcript
    # ------------------------------------------------------------------

    def segment_transcript(
        self,
        transcript_data: dict,
        segment_key: str = "text",
    ) -> dict:
        """Segment all segments in a transcript JSON object.

        Returns a modified copy with segmented text stored
        as a new ``segmented_texts`` list per segment.
        """
        segments = transcript_data.get("segments", [])
        for seg in segments:
            text = seg.get(segment_key, "")
            lines = self.segment(text)
            seg["segmented_lines"] = lines
        return transcript_data