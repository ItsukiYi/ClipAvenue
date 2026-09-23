"""ClipMetadata — B站 VUP 切片风格的标题/标签/封面生成。

从 小蓝牌板栗饼 (UID:193383609) 学到的模式：
  【VUP名字】故事性叙事标题
  特点: 完整句子讲述有趣故事, 20-40字
  常用手法: 反差, 自嘲, 热点+反应

全输出简体中文。
"""

from __future__ import annotations

import json
import os
import subprocess
import re
from pathlib import Path
from typing import Any

from clipavenue.logger import log

# ---------------------------------------------------------------------------
# Traditional → Simplified Chinese
# ---------------------------------------------------------------------------

try:
    import opencc
    _converter = opencc.OpenCC('t2s')
except ImportError:
    _converter = None


def to_simplified(text: str) -> str:
    if _converter and text:
        return _converter.convert(text)
    return text


# ---------------------------------------------------------------------------
# Title generation — 小蓝牌板栗饼 风格
# ---------------------------------------------------------------------------

TITLE_PATTERNS: dict[str, list[str]] = {
    "台风": ["说起台风{s}", "台风天{s}"],
    "天气": ["天气{s}", "{s}这天气绝了"],
    "BW": ["在BW{s}", "BW遇到{s}"],
    "漫展": ["漫展{s}", "在漫展{s}"],
    "主播": ["主播{s}", "直播的时候{s}"],
    "直播": ["直播{s}", "开播{s}"],
}

DEFAULT_PATTERNS = ["{s}", "{s}真的太搞笑了", "{s}这段绷不住了"]


def generate_title(segments: list[dict], label: str = "", context: str = "") -> str:
    """生成B站VUP切片风格标题(简体)."""
    if not segments:
        return "精彩切片"

    texts = [s.get("text", "").strip() for s in segments if s.get("text")]
    if not texts:
        return "精彩切片"

    # 找有故事性的片段
    best = ""
    for t in texts:
        t = to_simplified(t)
        cleaned = _clean_text(t)
        if len(cleaned) < 8:
            continue
        hooks = ["然后", "结果", "没想到", "最后", "发现", "突然", "原来"]
        has_hook = any(h in t[:15] for h in hooks)
        has_content = sum(1 for c in cleaned if '一' <= c <= '鿿') >= 4
        if has_hook and has_content:
            best = cleaned
            break

    if not best:
        for t in texts:
            cleaned = _clean_text(to_simplified(t))
            if 10 <= len(cleaned) <= 35 and len(cleaned) > len(best):
                best = cleaned

    if not best:
        best = to_simplified(label or "")[:30]
    if not best:
        return "精彩切片"

    summary = best[:28]
    if len(best) > 28:
        summary = best[:25] + "..."

    patterns = TITLE_PATTERNS.get(context, DEFAULT_PATTERNS)
    idx = abs(hash(best)) % len(patterns)
    title = patterns[idx].format(s=summary)

    title = to_simplified(title)
    if len(title) > 35:
        title = title[:32] + "..."

    return title


def _clean_text(text: str) -> str:
    """去标点去填充词."""
    text = to_simplified(text)
    text = re.sub(r'[，。、！？：；""''（）【】《》—…·,.!?:;()\[\]{}]', '', text)
    fillers = ["嗯", "啊", "哎", "哦", "呀", "啦", "吧", "吗", "呢",
               "然后", "就是", "其实", "那个", "这个", "所以", "但是",
               "不过", "而且", "对了", "算了", "完了", "好了",
               "一个", "什么", "怎么", "这样", "那样",
               "我们", "你们", "他们", "咱们",
               "可以", "没有", "不是", "还是", "觉得",
               "时候", "地方", "东西", "事情", "的话"]
    for f in fillers:
        text = text.replace(f, "")
    return text.strip()


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

CONTEXT_TAGS: dict[str, list[str]] = {
    "台风": ["台风", "天气", "自然灾害"],
    "天气": ["天气"],
    "BW": ["BW", "漫展", "BilibiliWorld", "二次元"],
    "漫展": ["漫展", "BW", "二次元"],
    "主播": ["主播", "直播", "虚拟主播", "VUP"],
    "直播": ["直播", "主播", "VUP"],
}

DEFAULT_TAGS = ["直播", "直播切片", "VUP"]


def generate_tags(text: str, context: str = "", topic_label: str = "") -> list[str]:
    text = to_simplified(text)
    tags = set(DEFAULT_TAGS)
    if context:
        for k, v in CONTEXT_TAGS.items():
            if k in context or context in k:
                tags.update(v)
    if topic_label:
        for w in re.findall(r'[一-鿿]{2,}', to_simplified(topic_label))[:3]:
            if len(w) >= 2:
                tags.add(w)
    if any(k in text for k in ["游戏", "抽卡"]):
        tags.add("游戏切片")
    if any(k in text for k in ["故事", "经历", "日常"]):
        tags.add("日常")
    return list(tags)[:10]


# ---------------------------------------------------------------------------
# Cover
# ---------------------------------------------------------------------------


def generate_cover(video_path: Path, output_path: Path, title: str) -> bool:
    if not video_path.is_file():
        return False
    title = to_simplified(title)
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
             str(video_path)],
            capture_output=True, text=True, timeout=15,
        )
        duration = float(r.stdout.strip()) if r.stdout.strip() else 60
    except Exception:
        duration = 60.0

    seek_time = max(1.0, duration * 0.2)
    temp = output_path.with_suffix(".raw.jpg")

    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-ss", str(seek_time), "-i", str(video_path),
         "-frames:v", "1", "-q:v", "2", str(temp)],
        capture_output=True, timeout=30,
    )
    if not temp.is_file():
        return False

    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-i", str(temp),
         "-vf", f"drawtext=text={title}:fontsize=42:fontcolor=white:box=1:boxcolor=black@0.5:x=(w-text_w)/2:y=h-text_h-40",
         "-q:v", "2", str(output_path)],
        capture_output=True, timeout=30,
    )

    temp.unlink(missing_ok=True)

    if output_path.is_file():
        return True
    if temp.is_file():
        temp.rename(output_path)
        return True
    return False


# ---------------------------------------------------------------------------
# Full metadata
# ---------------------------------------------------------------------------


def generate_clip_meta(
    clip_index: int, clip_path: Path,
    transcript_segments: list[dict],
    context: str = "", topic_label: str = "",
) -> dict[str, Any]:
    title = generate_title(transcript_segments, topic_label, context)
    full_text = " ".join(s.get("text", "") for s in transcript_segments)
    tags = generate_tags(full_text, context, topic_label)

    cover_path = clip_path.with_suffix(".cover.jpg")
    if not cover_path.is_file():
        generate_cover(clip_path, cover_path, title)

    return {
        "index": clip_index,
        "clip": clip_path.name,
        "title": title,
        "tags": tags,
        "cover": cover_path.name if cover_path.is_file() else "",
        "duration": round(
            transcript_segments[-1]["end"] - transcript_segments[0]["start"]
            if len(transcript_segments) >= 2 else 0
        ),
    }


def to_simplified_text(text: str) -> str:
    return to_simplified(text)