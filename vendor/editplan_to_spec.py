# -*- coding: utf-8 -*-
"""editplan_to_spec — 把 ClipAvenue 的 EditPlan 转成 capcut-cli compile spec。

EditPlan 是 agent 与工程生成器之间的中间表示(秒级时间, 面向人/LLM);
compile spec 是 capcut-cli `compile` 命令的输入。

两种素材形态(二选一):
A. linked   — 引用整段直播源文件 + sourceStart(保留完整源, 用户可在剪映里重取切点)。
   ⚠️ 已知坑(2026-09 实测): 同一源文件多段(不同 sourceStart)时 capcut-cli 为每段建
      独立 material 且时长只记该段, 剪映会把后段 clamp 到文件头播放。当前版本请勿用于
      多段场景, 单段安全。
B. materialized — 引用 ClipAvenue 已切好的独立 clip 文件(整文件一段, sourceStart=0)。
   推荐默认: 无同源坑, 语义清晰; 用户拿到"AI 已切好的片段 + 字幕"在剪映里精剪。
   完整源素材可另放入草稿 assets/ 备查。

EditPlan schema:
{
  "name": "切片名-YYYYMMDD",
  "canvas": {"width": 1080, "height": 1920, "fps": 30, "ratio": "9:16"},
  "mode": "materialized",                     // "materialized" | "linked"

  // linked 模式:
  "source": "D:/path/直播.mp4",
  "selections": [
    {"label": "...", "source_start": 0, "source_end": 30,
     "subtitles": [{"text": "...", "start": 0.0, "duration": 2.3}]}   // 相对 selection 起点
  ],
  "fine_cuts": {
    "silence_delete": [{"start": 8.1, "end": 10.9}],   // detect-silence 输出
    "retake_delete": [{"start": 5.0, "end": 7.0}]      // detect-retakes 输出
  }

  // materialized 模式:
  "clips": [{"path": "D:/x/clip1.mp4", "label": "seg1"},
            {"path": "D:/x/clip2.mp4", "label": "seg2"}],   // 依序排布在时间轴
  "subtitles": [{"text": "...", "start": 0.0, "duration": 2.3}]   // 相对成品时间轴
}

用法: python editplan_to_spec.py editplan.json out_spec.json
"""

import argparse
import json
import sys
from pathlib import Path

FONT_SIZE = 48
FONT_COLOR = "#FFFFFF"
TEXT_Y = -0.55


def subtract_spans(start: float, end: float, deletes: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """从区间 [start, end] 中减去若干删除区间, 返回按序 keep 子区间。"""
    cuts = sorted([(max(ds, start), min(de, end)) for ds, de in deletes if de > start and ds < end])
    keeps, cursor = [], start
    for ds, de in cuts:
        if ds > cursor:
            keeps.append((cursor, ds))
        cursor = max(cursor, de)
    if cursor < end:
        keeps.append((cursor, end))
    return keeps


def _text_item(sub: dict, start: float, duration: float) -> dict:
    return {
        "text": sub["text"],
        "start": round(start, 3),
        "duration": round(duration, 3),
        "fontSize": sub.get("fontSize", FONT_SIZE),
        "color": sub.get("color", FONT_COLOR),
        "y": sub.get("y", TEXT_Y),
    }


def build_materialized(plan: dict) -> dict:
    clips = plan.get("clips", [])
    if not clips:
        raise ValueError("materialized mode requires editplan.clips")
    subtitles = plan.get("subtitles", [])
    video_items, text_items = [], []
    axis = 0.0
    for c in clips:
        path = c.get("path", "")
        if not path:
            raise ValueError("clip item requires path")
        dur = c.get("duration")
        item = {"path": path, "start": round(axis, 3), "sourceStart": 0}
        if dur:
            item["duration"] = round(dur, 3)
        video_items.append(item)
        axis += round(dur or 0.0, 3)
    for sub in subtitles:
        text_items.append(_text_item(sub, sub["start"], sub.get("duration", 2.0)))
    return video_items, text_items


def build_linked(plan: dict) -> tuple[list, list]:
    source = plan.get("source", "")
    if not source:
        raise ValueError("linked mode requires editplan.source")
    fine_cuts = plan.get("fine_cuts", {}) or {}
    delete_spans = [(d["start"], d["end"]) for d in
                    fine_cuts.get("silence_delete", []) + fine_cuts.get("retake_delete", [])]
    video_items, text_items = [], []
    for sel in plan.get("selections", []):
        sel_start = sel.get("source_start", 0.0)
        sel_end = sel.get("source_end", sel_start)
        keeps = subtract_spans(sel_start, sel_end, delete_spans)
        axis = 0.0
        for ks, ke in keeps:
            video_items.append({
                "path": source,
                "start": round(axis, 3),
                "duration": round(ke - ks, 3),
                "sourceStart": round(ks, 3),
            })
            for sub in sel.get("subtitles", []):
                s_src = sel_start + sub["start"]
                s_end = s_src + sub.get("duration", 2.0)
                if s_end <= ks or s_src >= ke:
                    continue
                s_axis = axis + max(0.0, s_src - ks)
                dur = min(ke, s_end) - max(ks, s_src)
                if dur > 0.05:
                    text_items.append(_text_item(sub, s_axis, dur))
            axis += round(ke - ks, 3)
    return video_items, text_items


def build_spec(plan: dict) -> dict:
    name = plan.get("name") or "clipavenue-edit"
    canvas = plan.get("canvas", {})
    mode = plan.get("mode", "materialized")

    if mode == "materialized":
        video_items, text_items = build_materialized(plan)
    else:
        video_items, text_items = build_linked(plan)

    tracks = []
    if video_items:
        tracks.append({"type": "video", "items": video_items})
    if text_items:
        tracks.append({"type": "text", "items": text_items})
    if not tracks:
        raise ValueError("editplan produced no tracks — check selections/clips/fine_cuts")

    return {
        "name": name,
        "width": canvas.get("width", 1080),
        "height": canvas.get("height", 1920),
        "fps": canvas.get("fps", 30),
        "ratio": canvas.get("ratio", "9:16"),
        "tracks": tracks,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="EditPlan -> capcut-cli compile spec")
    ap.add_argument("editplan", help="EditPlan JSON 文件路径")
    ap.add_argument("out", help="输出的 compile spec JSON 路径")
    args = ap.parse_args()

    plan = json.loads(Path(args.editplan).read_text(encoding="utf-8"))
    spec = build_spec(plan)
    Path(args.out).write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(t["items"]) for t in spec["tracks"])
    print(f"spec ok: {spec['name']} [{plan.get('mode', 'materialized')}] | "
          f"{spec['width']}x{spec['height']} | tracks={len(spec['tracks'])} items={total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())