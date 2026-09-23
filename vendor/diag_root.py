# -*- coding: utf-8 -*-
import json
from pathlib import Path

ROOT = Path(r"C:\Users\13417\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft\root_meta_info.json")
BACKUPS = sorted(Path(r"C:\Users\13417\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft").glob("root_meta_info.json.bak*"))

print("root mtime :", ROOT.stat().st_mtime)
print("backups    :", [b.name for b in BACKUPS])

raw = ROOT.read_text(encoding="utf-8", errors="replace")
print("size       :", len(raw))

try:
    data = json.loads(raw)
    print("JSON valid  : YES")
    store = data.get("all_draft_store", [])
    print("entries     :", len(store))
    hits = [e for e in store if "AI" in e.get("draft_name", "") or "切片" in e.get("draft_name", "")]
    print("our entries :", [(e.get("draft_name"), e.get("draft_id")) for e in hits])
except json.JSONDecodeError as exc:
    print("JSON valid  : NO ->", exc)
    # 找损坏位置附近的上下文
    pos = exc.pos
    print("context     :", raw[max(0, pos - 120):pos + 120])