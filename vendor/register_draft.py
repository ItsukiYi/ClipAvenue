# -*- coding: utf-8 -*-
"""ClipAvenue: 把生成的剪映草稿注册进剪映草稿列表(root_meta_info.json)。

用法:
    python register_draft.py <草稿目录> [--duration <秒>] [--dry-run]

默认 `--duration` 从草稿 draft_content.json 的 duration 字段读取(微秒)。
先备份 root_meta_info.json(带时间戳),再追加/更新同名条目,最后同步
草稿 draft_meta_info.json 的 draft_id/draft_name 等字段。

安全规则:
- 剪映运行时不要写(root 索引会被剪映退出时覆盖)。
- 每次写入前自动备份;--dry-run 只预览不落盘。
"""
import argparse
import datetime
import json
import shutil
import sys
import uuid
from pathlib import Path

ROOT_DEFAULT = Path(r"C:\Users\13417\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft\root_meta_info.json")


def filetime_us() -> int:
    """Windows FILETIME(100ns since 1601-01-01)。"""
    delta = datetime.datetime.now(datetime.timezone.utc) - datetime.datetime(1601, 1, 1, tzinfo=datetime.timezone.utc)
    return int(delta.total_seconds() * 10_000_000)


def read_duration_us(draft_dir: Path) -> int:
    """从 draft_content.json 读总时长(微秒);失败返回 0。"""
    try:
        d = json.loads((draft_dir / "draft_content.json").read_text(encoding="utf-8"))
        return int(d.get("duration", 0))
    except Exception:
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="注册 ClipAvenue 生成的剪映草稿到剪映列表")
    ap.add_argument("draft_dir", help="草稿文件夹绝对路径, 如 D:/JianyingPro Drafts/xxx")
    ap.add_argument("--duration", type=float, default=None, help="时间轴总时长(秒);缺省从 draft_content.json 读取")
    ap.add_argument("--dry-run", action="store_true", help="只预览, 不落盘")
    ap.add_argument("--root", type=Path, default=ROOT_DEFAULT, help="root_meta_info.json 路径(缺省自动探测)")
    args = ap.parse_args()

    draft_dir = Path(args.draft_dir)
    if not draft_dir.is_dir():
        print(f"error: 草稿目录不存在: {draft_dir}", file=sys.stderr)
        return 2
    if not (draft_dir / "draft_content.json").is_file():
        print(f"error: 缺少 draft_content.json: {draft_dir}", file=sys.stderr)
        return 2

    if args.duration is not None:
        duration_us = int(args.duration * 10_000_000)
    else:
        duration_us = read_duration_us(draft_dir)

    root = args.root
    if not root.is_file():
        print(f"error: 找不到 root_meta_info.json: {root}", file=sys.stderr)
        return 2

    data = json.loads(root.read_text(encoding="utf-8"))
    store = data.setdefault("all_draft_store", [])
    fold = str(draft_dir).replace("\\", "/")

    existing = next((e for e in store if e.get("draft_fold_path", "").replace("\\", "/") == fold), None)

    draft_id = existing["draft_id"] if existing else str(uuid.uuid4()).upper()
    now = filetime_us()

    entry = {
        "cloud_draft_cover": False,
        "cloud_draft_sync": False,
        "draft_cloud_last_action_download": False,
        "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "",
        "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "",
        "draft_cover": "",
        "draft_fold_path": fold,
        "draft_id": draft_id,
        "draft_is_ai_shorts": False,
        "draft_is_cloud_temp_draft": False,
        "draft_is_infinite_canvas_draft": False,
        "draft_is_invisible": False,
        "draft_is_pippit_draft": False,
        "draft_is_web_article_video": False,
        "draft_json_file": fold + "/draft_content.json",
        "draft_name": draft_dir.name,
        "draft_new_version": "",
        "draft_root_path": str(draft_dir.parent).replace("\\", "/"),
        "draft_timeline_materials_size": 0,
        "draft_type": "",
        "draft_web_article_video_enter_from": "",
        "pippit_avatar_url": "",
        "pippit_extra_info": "",
        "pippit_id": "",
        "pippit_user_name": "",
        "streaming_edit_draft_ready": True,
        "tm_draft_cloud_completed": "",
        "tm_draft_cloud_entry_id": -1,
        "tm_draft_cloud_modified": 0,
        "tm_draft_cloud_parent_entry_id": -1,
        "tm_draft_cloud_space_id": -1,
        "tm_draft_cloud_user_id": -1,
        "tm_draft_create": now,
        "tm_draft_modified": now,
        "tm_draft_removed": 0,
        "tm_duration": duration_us,
    }

    if existing:
        store[store.index(existing)] = entry
        action = "update"
    else:
        store.append(entry)
        action = "insert"

    if args.dry_run:
        print(f"[dry-run] would {action} {draft_dir.name} (id={draft_id}, {duration_us / 1e7:.1f}s)")
        return 0

    bak = root.with_name(root.name + ".bak-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
    shutil.copy2(root, bak)
    root.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"{action} ok: {draft_dir.name} ({duration_us / 1e7:.1f}s) id={draft_id}")
    print(f"backup: {bak}")

    # 同步草稿自身的 meta 字段
    meta_path = draft_dir / "draft_meta_info.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["draft_id"] = draft_id
            meta["draft_name"] = draft_dir.name
            meta["draft_fold_path"] = fold
            meta["draft_root_path"] = str(draft_dir.parent).replace("\\", "/")
            meta["tm_duration"] = duration_us
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=4), encoding="utf-8")
            print("meta synced")
        except Exception as exc:
            print(f"warning: meta sync failed: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())