"""TranscriptAnalyzer — analyze transcripts for topic/clip boundaries.

Detects natural topic shifts in conversational transcripts using:
- Topic marker keywords
- Pause duration between segments
- Keyword density changes

Clips are ranked by interest score and only the best ones are returned.
Target clip duration: 3-5 minutes (180-300s).
"""

from __future__ import annotations

import re
import math
from typing import Any, Optional

# Topic keywords that indicate a NEW topic starting
TOPIC_START_WORDS: set[str] = {
    "说起来", "话说", "对了", "哦对了",
    "最后", "另外", "还有一个", "再说",
    "讲到", "提到", "说到", "关于",
    "顺便", "对了还有", "哦还有",
    "我跟你讲", "我跟你说", "你知道吗",
    "我跟你说啊", "我跟你讲啊",
}

# Keywords indicating STORYTELLING / high-value content
STORY_WORDS: set[str] = {
    "有一次", "有一天", "当时", "那天",
    "结果", "然后呢", "你猜怎么着",
    "笑死", "笑死了", "太好笑了",
    "绝了", "真的绝", "我的天",
    "无语了", "受不了", "救命",
    "超好笑", "超好笑的", "笑到头掉",
    "我跟你说", "你知道吗",
    "关键", "重点是", "最重要的是",
    "没想到", "结果发现", "最后",
    "笑死我了", "哈哈哈", "哈哈哈哈哈",
}

# High-interest emotional markers
EXCITEMENT_WORDS: set[str] = {
    "哇塞", "哇", "天哪", "天呐",
    "好厉害", "真的假的", "不会吧",
    "太强了", "太猛了", "太离谱了",
    "绝了", "我靠", "不是吧",
    ""  "",
}

# Keywords that indicate the SAME topic is continuing
TOPIC_CONTINUE_WORDS: set[str] = {
    "然后", "所以", "但是", "不过", "而且",
    "就是", "其实", "也就是说", "对吧",
}

HIGH_VALUE_NOUNS = re.compile(r"[一-鿿]{2,}")

# Default clip duration range (3-5 minutes)
DEFAULT_MIN_CLIP_DURATION = 150   # 2.5 minutes
DEFAULT_MAX_CLIP_DURATION = 360   # 6 minutes
DEFAULT_TARGET_DURATION = 240     # 4 minutes (ideal)


class TopicSegment:
    """A detected topic segment within a transcript."""

    def __init__(
        self,
        index: int,
        start_time: float,
        end_time: float,
        text: str,
        label: str = "",
        segment_indices: Optional[list[int]] = None,
        score: float = 0.0,
    ) -> None:
        self.index = index
        self.start_time = start_time
        self.end_time = end_time
        self.text = text
        self.label = label
        self.segment_indices = segment_indices or []
        self.score = score

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "start_time": round(self.start_time, 2),
            "end_time": round(self.end_time, 2),
            "duration": round(self.duration, 1),
            "text": self.text[:120],
            "label": self.label,
            "score": round(self.score, 2),
        }


class ClipSuggestion:
    """A suggested video clip with interest score."""

    def __init__(
        self,
        topic: TopicSegment,
        start_buffer: float = 2.0,
        end_buffer: float = 3.0,
    ) -> None:
        self.topic = topic
        self.start_buffer = start_buffer
        self.end_buffer = end_buffer
        self.score = topic.score

    @property
    def clip_start(self) -> float:
        return max(0, self.topic.start_time - self.start_buffer)

    @property
    def clip_end(self) -> float:
        return self.topic.end_time + self.end_buffer

    @property
    def duration(self) -> float:
        return self.clip_end - self.clip_start

    def to_dict(self) -> dict:
        return {
            "label": self.topic.label or f"片段 {self.topic.index}",
            "start": round(self.clip_start, 2),
            "end": round(self.clip_end, 2),
            "duration": round(self.duration, 1),
            "preview": self.topic.text[:100],
            "score": round(self.score, 2),
        }


class TranscriptAnalyzer:
    """Analyze a transcribed conversation for topic segments & clip candidates.

    Strategy:
    1. Detect fine-grained topics (topic markers + pause gaps)
    2. Merge consecutive topics into groups of ~3-5 minutes
    3. Score each merged group by interest level
    4. Return only the top-scoring groups as clip suggestions

    Signals for scoring:
    - Story marker density (storytelling keywords)
    - Excitement markers (laughter, emotion)
    - Word density (richer = better)
    - Duration fitness (closer to 4min = better)
    """

    def __init__(
        self,
        min_topic_duration: float = 10.0,
        target_duration: float = DEFAULT_TARGET_DURATION,
        max_duration: float = DEFAULT_MAX_CLIP_DURATION,
        pause_threshold: float = 3.0,
        max_suggestions: int = 8,
    ) -> None:
        self.min_topic_duration = min_topic_duration
        self.target_duration = target_duration
        self.max_duration = max_duration
        self.pause_threshold = pause_threshold
        self.max_suggestions = max_suggestions

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score_topic(self, text: str, start: float, end: float) -> float:
        """Score a topic segment by estimated interest level.

        Signals (each contributes 0-1, weighted):
        - Story marker density: presence of storytelling keywords
        - Excitement markers: laughter, exclamation, emotional words
        - Word density: more words per second = richer content
        - Duration fitness: closer to target = better
        """
        duration = max(1, end - start)
        score = 0.0

        # Signal 1: Story marker density (权重 0.3)
        story_count = sum(1 for w in STORY_WORDS if w in text)
        story_density = min(1.0, story_count / (duration / 60 * 2))  # 2 per minute = max
        score += story_density * 0.3

        # Signal 2: Excitement markers (权重 0.2)
        excite_count = sum(1 for w in EXCITEMENT_WORDS if w in text)
        excite_score = min(1.0, excite_count / 3)
        score += excite_score * 0.2

        # Signal 3: Word density (权重 0.25)
        words = HIGH_VALUE_NOUNS.findall(text)
        wpm = len(words) / (duration / 60)  # words per minute
        density_score = min(1.0, wpm / 60)  # 60 words/min = full score
        score += density_score * 0.25

        # Signal 4: Duration fitness (权重 0.25)
        # Closer to target = higher score
        ratio = duration / self.target_duration
        if ratio < 0.5:
            dur_score = ratio  # too short, penalized
        elif ratio <= 1.5:
            dur_score = 1.0  # in sweet spot
        else:
            dur_score = max(0, 2.0 - ratio)  # too long, penalized
        score += dur_score * 0.25

        # Bonus: Topic markers at start = natural segment start
        for w in TOPIC_START_WORDS:
            if text.startswith(w):
                score += 0.1
                break

        return score

    # ------------------------------------------------------------------
    # Topic segmentation
    # ------------------------------------------------------------------

    def detect_topics(self, segments: list[dict]) -> list[TopicSegment]:
        """Split transcript segments into topic groups."""
        if not segments:
            return []

        topics: list[TopicSegment] = []
        current_segments: list[int] = []
        current_text_parts: list[str] = []

        def flush() -> None:
            if not current_segments:
                return
            segs = [segments[i] for i in current_segments]
            text = " ".join(part for part in current_text_parts if part)
            start = segs[0]["start"]
            end = segs[-1]["end"]
            score = self._score_topic(text, start, end)
            label = self._label_topic(text)
            topic = TopicSegment(
                index=len(topics) + 1,
                start_time=start,
                end_time=end,
                text=text.strip(),
                label=label,
                segment_indices=list(current_segments),
                score=score,
            )
            topics.append(topic)

        for i, seg in enumerate(segments):
            text = (seg.get("text") or "").strip()
            if not text:
                continue

            is_start = self._is_topic_start(text)
            has_pause_gap = False
            if current_segments and i > 0:
                prev_end = segments[i - 1].get("end", 0)
                gap = seg.get("start", 0) - prev_end
                has_pause_gap = gap > self.pause_threshold

            if is_start or has_pause_gap:
                flush()
                current_segments = [i]
                current_text_parts = [text]
            else:
                current_segments.append(i)
                current_text_parts.append(text)

        flush()
        return topics

    def _is_topic_start(self, text: str) -> bool:
        """Check if text signals the start of a new topic."""
        for word in TOPIC_START_WORDS:
            if word in text:
                return True
        stripped = text.lstrip()
        if stripped.startswith("然后") and len(stripped) > 6:
            return True
        return False

    def _label_topic(self, text: str) -> str:
        """Generate a short label from key content words."""
        words = HIGH_VALUE_NOUNS.findall(text)
        if not words:
            return ""
        seen: set[str] = set()
        label_words: list[str] = []
        for w in words:
            if len(w) >= 2 and w not in seen:
                seen.add(w)
                label_words.append(w)
                if len(label_words) >= 3:
                    break
        return "".join(label_words) if label_words else ""

    # ------------------------------------------------------------------
    # Clip suggestion with ranking
    # ------------------------------------------------------------------

    def suggest_clips(self, topics: list[TopicSegment]) -> list[ClipSuggestion]:
        """Merge fine-grained topics into 3-5 minute clip groups.

        1. Skip very short topics (< 10s — likely noise)
        2. Merge consecutive topics into groups targeting target_duration
        3. Score each group by interest level
        4. Return top-scoring groups
        """
        # Step 1: Filter noise
        valid = [t for t in topics if t.duration >= self.min_topic_duration]
        if not valid:
            return []

        # Step 2: Merge into groups of ~target_duration
        groups: list[TopicSegment] = []
        current_topics: list[TopicSegment] = []

        def _flush_group():
            if not current_topics:
                return
            start = current_topics[0].start_time
            end = current_topics[-1].end_time
            text = " ".join(t.text for t in current_topics)
            score = self._score_topic(text, start, end)
            label = self._label_topic(text)
            group = TopicSegment(
                index=len(groups) + 1,
                start_time=start,
                end_time=end,
                text=text,
                label=label,
                score=score,
            )
            groups.append(group)

        for topic in valid:
            duration_so_far = (topic.end_time - (current_topics[0].start_time if current_topics else topic.start_time))

            # If adding this topic would exceed max duration, flush first
            if current_topics and duration_so_far > self.max_duration:
                _flush_group()
                current_topics = [topic]
            else:
                current_topics.append(topic)

        _flush_group()

        # Step 3: Score groups and rank
        # Duration bonus: prefer groups closer to target_duration
        for group in groups:
            ratio = group.duration / self.target_duration
            if ratio < 0.3:
                group.score *= 0.5  # too short, penalize heavily
            elif 0.5 <= ratio <= 1.5:
                group.score *= 1.2  # sweet spot, bonus
            elif ratio > 2.0:
                group.score *= 0.7  # too long, penalize

        # Step 4: Sort by score, take top N, re-sort by time
        groups.sort(key=lambda g: -g.score)
        selected = groups[:self.max_suggestions]
        selected.sort(key=lambda g: g.start_time)

        return [ClipSuggestion(g) for g in selected]

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def analyze(self, transcript_data: dict) -> dict:
        """Run full analysis on a transcript JSON object.

        Returns structured analysis result with topics and ranked clip suggestions.
        """
        segments = transcript_data.get("segments", [])
        for seg in segments:
            lines = seg.get("segmented_lines")
            if lines:
                seg["text"] = " ".join(lines)

        topics = self.detect_topics(segments)
        clips = self.suggest_clips(topics)

        return {
            "topic_count": len(topics),
            "clip_count": len(clips),
            "total_duration": (
                segments[-1]["end"] - segments[0]["start"]
                if len(segments) >= 2 else 0
            ),
            "topics": [t.to_dict() for t in topics],
            "suggested_clips": [c.to_dict() for c in clips],
        }