#!/usr/bin/env python3
"""
HEIC/HIF → JPEG 转换 + 同名 ARW 提取工具

工作流:
  1. 输入源目录
  2. 转换所有 .heic/.hif → .jpg
  3. 你手动从生成的 jpg 中挑选好的，放到 ./selected/ 下
  4. 运行本脚本的 --copy-arw 模式，将同名 .arw 文件复制到 ./selected_arw/

用法:
    python heic_to_jpg.py                              # 交互式：输入目录，执行转换
    python heic_to_jpg.py /path/to/photos --convert    # 直接指定目录转换
    python heic_to_jpg.py /path/to/photos --copy-arw   # 根据 selected/ 中的 jpg 复制同名 .arw

依赖:
    pip install Pillow pillow-heif
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

try:
    from PIL import Image
    import pillow_heif
except ImportError:
    print("缺少必要依赖，请运行：pip install Pillow pillow-heif")
    sys.exit(1)

pillow_heif.register_heif_opener()

# ── 支持的扩展名 ────────────────────────────────────────────────────────────
EXTENSIONS = {".heic", ".hif", ".heif"}


# ═══════════════════════════════════════════════════════════════════════════
#  Phase 1 — 转换
# ═══════════════════════════════════════════════════════════════════════════

def convert_heic_to_jpg(src_dir: Path, quality: int = 90) -> None:
    """将源目录下所有 HEIC/HIF 转为 JPG（平铺在 src_dir 下）。"""
    files = sorted([
        f for f in src_dir.iterdir()
        if f.is_file() and f.suffix.lower() in EXTENSIONS
    ])

    if not files:
        print(f"⚠  目录中没有找到 HEIC/HIF 文件：{src_dir}")
        return

    print(f"找到 {len(files)} 个 HEIC/HIF 文件，开始转换（quality={quality}）...\n")

    ok = 0
    skip = 0
    fail = 0
    for f in files:
        dst = src_dir / f.with_suffix(".jpg").name
        if dst.exists():
            print(f"  ⏭  跳过（目标已存在）：{dst.name}")
            skip += 1
            continue
        try:
            img = Image.open(f)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(dst, "JPEG", quality=quality, optimize=True)
            img.close()
            src_size = f.stat().st_size
            dst_size = dst.stat().st_size
            ratio = dst_size / src_size * 100 if src_size else 0
            print(f"  ✅ {f.name} → {dst.name}  ({ratio:.0f}% 大小)")
            ok += 1
        except Exception as e:
            print(f"  ❌ {f.name}: {e}")
            fail += 1

    print(f"\n转换完成：成功 {ok}，跳过 {skip}，失败 {fail} / 共 {len(files)}")
    print(f"JPG 已输出到：{src_dir}")
    if ok:
        print(f"→ 请将挑选好的 JPG 文件放入 {src_dir / 'selected'}/ 目录下，")
        print(f"  然后运行 --copy-arw 来提取同名 ARW 文件。")


# ═══════════════════════════════════════════════════════════════════════════
#  Phase 2 — 复制同名 ARW
# ═══════════════════════════════════════════════════════════════════════════

def copy_arw_by_selection(src_dir: Path) -> None:
    """根据 selected/ 下的 JPG 文件名，从 src_dir 复制同名 .arw 到 selected_arw/。"""
    selected_dir = src_dir / "selected"
    selected_arw_dir = src_dir / "selected_arw"

    # ── 检查 selected/ 目录 ────────────────────────────────────────────
    if not selected_dir.is_dir():
        print(f"❌ 目录不存在：{selected_dir}")
        print(f"   请先将挑选好的 JPG 文件放入该目录。")
        return

    selected_jpgs = sorted([
        f for f in selected_dir.iterdir()
        if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg")
    ])

    if not selected_jpgs:
        print(f"⚠  {selected_dir}/ 下没有找到 JPG 文件。")
        return

    # ── 创建目标目录 ────────────────────────────────────────────────────
    selected_arw_dir.mkdir(parents=True, exist_ok=True)

    # ── 逐个匹配 ────────────────────────────────────────────────────────
    ok = 0
    miss = 0
    for jpg in selected_jpgs:
        stem = jpg.stem  # 不带扩展名的文件名
        arw_path = src_dir / f"{stem}.arw"
        dst_path = selected_arw_dir / f"{stem}.arw"

        if not arw_path.is_file():
            # 也尝试 .ARW（大写扩展名）
            arw_path = src_dir / f"{stem}.ARW"
            if not arw_path.is_file():
                print(f"  ⚠  未找到同名 ARW：{stem}.arw")
                miss += 1
                continue

        if dst_path.exists():
            print(f"  ⏭  跳过（目标已存在）：{dst_path.name}")
            continue

        shutil.copy2(arw_path, dst_path)
        print(f"  ✅ {arw_path.name} → {dst_path.parent.name}/")
        ok += 1

    # ── 汇总 ────────────────────────────────────────────────────────────
    print(f"\nARW 提取完成：成功 {ok}，缺失 {miss} / 共 {len(selected_jpgs)} 个选中 JPG")
    print(f"ARW 已输出到：{selected_arw_dir}/")

    if miss:
        print(f"\n⚠  有 {miss} 个文件的 ARW 未找到，请检查源目录。")
        print(f"   可能原因：文件名不一致，或该照片只拍了 HEIC 没有 ARW。")


# ═══════════════════════════════════════════════════════════════════════════
#  交互式输入目录
# ═══════════════════════════════════════════════════════════════════════════

def interactive_mode() -> Path:
    """提示用户输入目录路径，直到有效为止。"""
    while True:
        raw = input("请输入待转换的源目录路径：").strip()
        if not raw:
            print("输入不能为空，请重试。")
            continue
        p = Path(raw).resolve()
        if not p.is_dir():
            print(f"目录不存在：{p}，请重新输入。")
            continue
        return p


# ═══════════════════════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="HEIC → JPG 转换 + 同名 ARW 提取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "工作流示例:\n"
            "  1. 交互模式：python heic_to_jpg.py\n"
            "  2. 直接转换：python heic_to_jpg.py /d/photos --convert\n"
            "  3. 挑选 JPG 后提取 ARW：python heic_to_jpg.py /d/photos --copy-arw\n"
        ),
    )
    parser.add_argument("path", nargs="?", help="源目录路径（留空则交互输入）")
    parser.add_argument("--convert", action="store_true", help="转换 HEIC → JPG")
    parser.add_argument("--copy-arw", action="store_true", help="根据 selected/ 中的 JPG 提取同名 ARW 到 selected_arw/")
    parser.add_argument("--quality", type=int, default=90, help="JPEG 质量 (1-100，默认 90)")

    args = parser.parse_args()

    # ── 确定源目录 ────────────────────────────────────────────────────
    if args.path:
        src_dir = Path(args.path).resolve()
        if not src_dir.is_dir():
            print(f"错误：目录不存在 — {src_dir}", file=sys.stderr)
            sys.exit(1)
    else:
        # 无参数 → 交互模式
        print("=" * 50)
        print("  HEIC → JPG 转换 + ARW 提取工具")
        print("=" * 50)
        src_dir = interactive_mode()
        # 默认进入转换模式
        args.convert = True

    # ── 执行模式 ──────────────────────────────────────────────────────
    if args.copy_arw:
        copy_arw_by_selection(src_dir)
    elif args.convert:
        convert_heic_to_jpg(src_dir, quality=args.quality)
    else:
        print(f"请指定操作模式：--convert 或 --copy-arw")
        print(f"  使用 --convert  转换 HEIC → JPG")
        print(f"  使用 --copy-arw 提取同名 ARW")


if __name__ == "__main__":
    main()