# ClipAvenue — 直播切片全流程自动化(独立项目)

录播下载 → 存储管理 → 自动剪辑(AI 切片 + 细剪规则) → 交付剪映可编辑草稿 → 投稿 → 归档

> 已从 OpenMontage 剥离(2026-09-22):代码不再依赖 OpenMontage 的 `tools` / `lib` 模块,
> 语音转写由 `clipavenue/clipper/asr.py`(faster-whisper)独立提供。

## 模块结构

```
clipavenue/
  agent.py            headless LLM agent(Anthropic SDK,skill 为 system prompt)
  clip_tools.py       机械工具(音频提取/转写/裁剪/字幕/压制/封面)
  worker.py           队列消费:job -> ClipAgent -> 产物
  server.py + ui/     FastAPI + 地铁图式 dashboard(端口 4850)
  queue.py            SQLite 任务队列
  state.py            盘面状态(只读观测)
  config.py           YAML 配置
  recorder/           BililiveRecorder / biliup 封装
  storage/            磁盘监控与清理策略
  clipper/            核心剪辑引擎
    asr.py            轻量语音转写(faster-whisper,独立实现)
    correction.py     ASR 三阶段纠错(字典/上下文/同音)
    segmenter.py      ASR 知识图谱断句(≤17 字/行,无标点)
    analyzer.py       话题检测 + 高光定位(3-5 分钟切片)
    pipeline.py       8 步流水线编排
    metadata.py       标题/标签/封面文案
  archiver/           备份/清理/通知
  uploader/           biliup-rs 投稿封装
  lib_paths.py        规范路径(PROJECTS_DIR,可用 CLIPAVENUE_PROJECTS_DIR 覆盖)
skills/clipavenue/    agent 技能(clip-workflow / jianying-draft / RULES-汇总)
vendor/               pyJianYingDraft(剪映草稿生成)、capcut-cli(校验/修复/预览)、
                      pyjd-venv(Python 3.12 环境)、editplan_to_spec.py 等脚本
projects/             运行时产物(每个 job 一个目录)
```

## 两条剪辑路径

- **成片路径**(clip-workflow 1-9 步):ffmpeg 裁剪 + ASS 压制字幕 + 封面,直接产出 `*_subbed.mp4`。
- **可编辑工程路径**(第 10 步 + `skills/clipavenue/jianying-draft.md`):
  `EditPlan JSON -> vendor/editplan_to_spec.py -> capcut compile -> lint -> render 预览`
  → 剪映专业版打开精剪(推荐 materialized 模式)。

## 快速开始

```bash
# Python 环境(已建)
E:\ClipAvenue\vendor\pyjd-venv\Scripts\python.exe -m clipavenue        # 启动 dashboard
E:\ClipAvenue\vendor\pyjd-venv\Scripts\python.exe -m clipavenue.agent   # 连通性 smoke

# 剪映草稿工具链(Node >= 18;ffmpeg 需在 PATH)
node E:\ClipAvenue\vendor\capcut-cli\dist\index.js --help
```

环境变量:`ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_MODEL`(agent 调用)、
`CLIPAVENUE_PROJECTS_DIR`(可选,覆盖 projects 根)。

## 规则

见 `skills/clipavenue/RULES-汇总.md`(字幕样式/断句/纠错/选题/细剪/工程交付/安全)。

## 文档

- `docs/LIVESTREAM_CLIP_WORKFLOW.md` — 直播切片原始工作流
- `docs/ClipAvenue_技术白皮书.md` — 全流程自动化目标与方案
- `AI剪辑直播切片视频-调研报告.md` — 行业调研
- `剪映工程交付-技术可行性分析.md` — 可编辑工程交付的可行性/实测/路线