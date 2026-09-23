"""lib_paths — 独立项目的规范路径(替代 OpenMontage 的 lib.paths)。

PROJECTS_DIR 是所有运行时产物(clip 工程、日志、队列)的根,
可用环境变量 CLIPAVENUE_PROJECTS_DIR 覆盖(测试/迁移用)。
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PROJECTS_DIR = Path(os.environ.get("CLIPAVENUE_PROJECTS_DIR") or (REPO_ROOT / "projects"))