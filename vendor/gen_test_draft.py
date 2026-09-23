# -*- coding: utf-8 -*-
"""Phase 1 验证:用 pyJianYingDraft 生成一个剪映可编辑草稿。

模拟 ClipAvenue 的粗剪+细剪语义:
  源素材   : test_live_source.mp4 (60s 假直播源)
  切片1    : 取素材 8s-18s  -> 时间轴 0s-10s
  切片2    : 取素材 40s-52s -> 时间轴 10s-22s (同时演示"跳过"素材 18s-40s 的空档)
  字幕轨   : 两条与切片对齐的字幕
"""

import os
from pathlib import Path
import pyJianYingDraft as draft
from pyJianYingDraft import TrackSpec, TrackType, trange

DRAFTS_DIR = r"D:\JianyingPro Drafts"
VENDOR_DIR = Path(__file__).resolve().parent
SOURCE = str(VENDOR_DIR / "test_live_source.mp4")
DRAFT_NAME = "AI切片测试-20260922"

# 1. 打开剪映草稿文件夹
folder = draft.DraftFolder(DRAFTS_DIR)

# 2. 新建草稿(1080x1920 竖屏)
script = folder.create_draft(DRAFT_NAME, 1080, 1920, allow_replace=True)

# 3. 建轨道:视频主轨 + 文本字幕轨
script.append_tracks([
    TrackSpec(TrackType.video, "main_video"),
    TrackSpec(TrackType.text, "caption"),
])

# 4. 粗剪:从源素材截取两段(不同 source_timerange)
vseg1 = draft.VideoSegment(
    SOURCE,
    trange("0s", "10s"),            # 时间轴 0-10s
    source_timerange=trange("8s", "10s"),  # 源素材 8s-18s
)
vseg2 = draft.VideoSegment(
    SOURCE,
    trange("10s", "12s"),           # 时间轴 10-22s
    source_timerange=trange("40s", "12s"), # 源素材 40s-52s,中间 18s-40s 即为"被细剪跳过的空档"
)

# 5. 字幕(与切片对齐)
tseg1 = draft.TextSegment("主播讲了个趣事", trange("0s", "10s"))
tseg2 = draft.TextSegment("话题一转聊到别的事", trange("10s", "12s"))

# 6. 挂到轨道
script.add_segment(vseg1, "main_video")
script.add_segment(vseg2, "main_video")
script.add_segment(tseg1, "caption")
script.add_segment(tseg2, "caption")

# 7. 保存
script.save()
print("saved:", os.path.join(DRAFTS_DIR, DRAFT_NAME))