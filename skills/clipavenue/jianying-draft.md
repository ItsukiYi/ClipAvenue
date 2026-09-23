# JianYing Draft — 剪映可编辑工程的生成/校验/修复/注册

> 状态:**已冻结 v1(2026-09-22)**,全链路在本机实测通过。
> 适用:把 ClipAvenue(或任意 AI 流水线)的切片结果交付成"剪映专业版可打开的可编辑草稿",而不是只交一个成品 mp4。

---

## 0. 已证明的关键事实(冻结依据)

本机实测(剪映专业版 **11.4.1.14443**,草稿目录 `D:\JianyingPro Drafts\`):

1. **pyJianYingDraft 生成的是明文 JSON 草稿**(`draft_content.json` 以 `{` 开头),结构符合剪映草稿 schema;加密只影响"读取已有草稿"(模板模式)。
2. **剪映 11.4.1 能直接打开明文草稿并就地升级**:打开后剪映会把 `draft_content.json` 重写为**加密格式**、新增 `Timelines/<draft_id>/` 多时间线目录、`timeline_layout.json`、`.locked` 等 11.x 原生结构,并更新 `draft_meta_info.json`。**升级后不要再尝试用工具写回**。
3. **capcut-cli 是校验/修复/预览的瑞士军刀**,`lint` 能发现 pyJianYingDraft 生成草稿的隐患并自动修复(素材未注册、悬空引用、字幕超长、素材在草稿目录外),修复后 `lint` 全绿;`lint --fix` 还会把外部素材 staged 进草稿 `assets/`,让草稿自包含。
4. **root_meta_info.json 是明文索引**:新草稿要出现在剪映列表,必须在 `all_draft_store` 数组里有一个条目(正斜杠路径,WINDOWS FILETIME 时间戳,`tm_duration` 为 100ns 单位)。**剪映正在运行时禁止写这个文件**(退出时会用内存索引覆盖)。
5. **capcut-cli 内置两条细剪规则的现成实现**:`detect-silence`(删空档)与 `detect-retakes`(去重复表述),输出 keep/cut 段(秒+微秒),可直接喂给 `compile`。

---

## 1. 环境与路径(冻结值)

| 项 | 路径 |
|---|---|
| Python venv | `D:\ClipAvenue\vendor\pyjd-venv`(Python 3.12,已装 pyJianYingDraft) |
| pyJianYingDraft | `D:\ClipAvenue\vendor\pyJianYingDraft`(GuanYixuan 版 0.3.x) |
| capcut-cli | `D:\ClipAvenue\vendor\capcut-cli`,入口 `node dist\index.js`(v0.25.0) |
| 剪映草稿目录 | `D:\JianyingPro Drafts\`(用户自定义位置;默认在 `%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft`) |
| root 索引 | `C:\Users\13417\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft\root_meta_info.json` |
| 辅助脚本 | `D:\ClipAvenue\vendor\gen_test_draft.py`(生成示例)、`register_draft.py`(参数化注册)、`check_draft.py`(解析校验) |

---

## 2. 标准操作链(5 步,全部本地执行)

约定:`$CAPCUT = node "D:\ClipAvenue\vendor\capcut-cli\dist\index.js"`,`$PY = "D:\ClipAvenue\vendor\pyjd-venv\Scripts\python.exe"`。

### 第 1 步:生成明文草稿(pyJianYingDraft)

```python
import pyJianYingDraft as draft
from pyJianYingDraft import TrackSpec, TrackType, trange

folder = draft.DraftFolder(r"D:\JianyingPro Drafts")
script = folder.create_draft("切片名-YYYYMMDD", 1080, 1920, allow_replace=True)
script.append_tracks([
    TrackSpec(TrackType.video, "main_video"),
    TrackSpec(TrackType.text, "caption"),
])
# 粗剪:目标时间轴上排布多个 source_timerange(源素材内区间)
v1 = draft.VideoSegment(src_path, trange("0s", "10s"), source_timerange=trange("8s", "10s"))
v2 = draft.VideoSegment(src_path, trange("10s", "12s"), source_timerange=trange("40s", "12s"))
script.add_segment(v1, "main_video").add_segment(v2, "main_video")
# 字幕轨(逐条 TextSegment 与视频段对齐)
script.add_segment(draft.TextSegment("第一句字幕", trange("0s", "10s")), "caption")
script.save()
```

要点:
- `trange(start, duration)` — 参数是**开始时间 + 持续时长**(都不是结束时间),单位秒;内部用微秒(µs)。
- `source_timerange` 超出素材时长会抛 ValueError。
- **细剪=跳区间,不是切成新文件**:多段 `VideoSegment` 共用同一源素材、时间轴连续排列即完成"删掉中间一段"的效果;后续所有段落的 `target_timerange` 必须重排(agent 职责)。
- 完成生成后,**不要**接着用 pyJianYingDraft 读回(明文可读,但没必要);校验交给 capcut-cli。

### 第 2 步:capcut-cli 校验

```bash
$CAPCUT lint "D:\JianyingPro Drafts\切片名-YYYYMMDD"
```

预期首轮:`errors=0`,可能有 warning/info(素材未注册 `media-unlinked`、字幕超长 `cue-too-long`、素材在草稿外 `media-outside-draft`、pyJianYingDraft 遗留 `dangling-companion-ref`)。

### 第 3 步:自动修复(必须做)

```bash
$CAPCUT register "D:\JianyingPro Drafts\切片名-YYYYMMDD" --materials --apply
$CAPCUT lint "D:\JianyingPro Drafts\切片名-YYYYMMDD" --fix
$CAPCUT lint "D:\JianyingPro Drafts\切片名-YYYYMMDD"   # 复检,必须全绿
```

- `register --materials` 把素材登记进 `draft_meta_info.json` 的 `draft_materials`(**新版剪映不登记会显示"文件不可访问"**)。
- `lint --fix` 补 `local_material_id`、清除悬空引用、把外部素材 staged 进草稿 `assets/video/`(自包含)。
- **验收线:复检 `summary` 为 errors=0, warnings=0, info=0。未全绿不交付。**

### 第 4 步:注册进剪映列表(剪映关闭时才做)

```bash
$PY "D:\ClipAvenue\vendor\register_draft.py" "D:\JianyingPro Drafts\切片名-YYYYMMDD" [--duration <秒>]
```

- 自动备份 `root_meta_info.json`(带时间戳),再插入/更新 `all_draft_store` 条目,并同步草稿 `draft_meta_info.json` 的 `draft_id/draft_name` 等。
- `--duration` 缺省从 `draft_content.json` 读取,若为 0(未打开过)须显式传秒数。
- `--dry-run` 先预览。
- ⛔ **硬性规则:剪映正在运行时禁止执行本步**(进程名 `JianyingPro*`);剪映退出会覆盖索引。

### 第 5 步:无剪映预览(可选但推荐)

```bash
$CAPCUT render "D:\JianyingPro Drafts\切片名-YYYYMMDD" --out preview.mp4 --burn-captions
```

- 用 ffmpeg 渲染低分辨率代理预览,验证时间轴(多段 concat、字幕位置)后再交给用户,避免把判断失误写进用户工程。
- 只是代理预览,不代表剪映最终渲染效果。

---

## 3. 细剪规则 → capcut-cli 命令映射(冻结)

| 用户细剪规则 | 命令 | 输出 | 接入方式 |
|---|---|---|---|
| 删除 >N 秒没人说话的空档 | `detect-silence <media> --min-silence 3 --pad 0.1` | keep 段(秒+微秒) | 喂给 `compile` 或 `cut` |
| 同一意思说几遍只留一遍 | `detect-retakes <project> --similarity 0.8 --window 60` | 前一遍为 cut、后一遍为 keep | 同上 |
| 场景切断点(硬切) | `detect-scenes <video> --threshold 0.4` | 分段(秒+微秒) | 同上 |

上述检测命令**只读不写草稿**,输出 JSON 可安全喂给 agent/管道。用 `compile <spec.json>` 把 keep 段声明式组装成新草稿(`compile` 是"闘*工程生成器"的现成实现,秒级时间、素材路径相对于 spec 文件)。

---

## 4. 安全规则与已知陷阱(冻结)

1. **剪映运行中一律不写**:草稿写入或 root 索引写入前先查进程(`Get-Process -Name "*Jianying*"`);capcut-cli 自己也检测剪映运行并拒绝写。
2. **剪映打开后草稿会被升级加密**:明文草稿被剪映打开保存后,`draft_content.json`、`draft_meta_info.json` 变成**加密格式**(base64 高熵)。此后**只读**(capcut-cli 的 `info/lint/decrypt` 能检测),要改就重新生成一份明文草稿。
3. **不逆向加密**:capcut-cli 官方立场是"只检测、不解密"(见 `docs/jianying-encryption.md`);读取加密草稿需要社区 fallback_loader,不在本 skill 范围。
4. **素材路径**:尽量让素材在草稿 `assets/` 内(靠 `lint --fix` staged)或固定在草稿同盘目录;拷走草稿时带着素材一起。
5. **时间单位**:剪映时间轴=微秒(µs);root 索引 `tm_duration`=100ns(WINDOWS FILETIME 语义);命令参数多用秒,注意单位换算。
6. **版本兼容**:冻结时剪映 11.4.1 通过;剪映升级后先跑一轮"生成→lint→(机器上)打开"回归,再批量使用。生产环境建议锁定剪映版本。
7. **人工验证必须保留**:程序化全部通过≠剪映一定打开没问题;交付后要求用户在剪映里打开一次确认(打开、检查轨段、保存),这是最终验收。

---

## 5. 与 clip-workflow.md 的关系

- 本 skill 对应 clip-workflow 的 **第 10 步(交付可编辑工程)**:当 job 需要"交给用户精剪"时,不直接压制字幕出成片,改为:
  1. 用 §6 的 **EditPlan 流水线**:`trim_clips` 区间/`detect-silence` keep 段 → EditPlan JSON → `editplan_to_spec.py` → `capcut compile`;
  2. 校正后的字幕行(单行 ≤17 字、无标点)映射为 EditPlan 的 `subtitles`(字幕样式:微软雅黑 48pt 白字,底部 y=-0.55,与剪映竖屏规范对齐);
  3. 走本 skill 第 2-5 步(校验→修复→注册→预览)。
- ffmpeg 压制字幕版本仍保留,作为快速预览兜底。

## 6. EditPlan 流水线(Phase 2,冻结 v1,2026-09-22 实测通过)

**推荐默认 = materialized 模式**(ClipAvenue 已按 keep 区间切出独立 clip 文件),全程无修复、lint 全绿:

```
直播/回放 → detect-silence(找空档 keep 段) → ffmpeg 切出 clip*.mp4
        → 组装 EditPlan JSON(片段 + 字幕)
        → python editplan_to_spec.py editplan.json spec.json
        → capcut compile spec.json --drafts "D:\JianyingPro Drafts"
        → capcut lint(应全绿)→ capcut render --burn-captions(预览)
        → 剪映关闭时 register_draft.py 注册进列表
```

EditPlan schema(秒级时间)与转换器 `D:\ClipAvenue\vendor\editplan_to_spec.py`:

```json
{
  "name": "切片名-YYYYMMDD",
  "canvas": {"width": 1080, "height": 1920, "fps": 30, "ratio": "9:16"},
  "mode": "materialized",                       // materialized | linked
  "clips": [{"path": "D:/x/seg1.mp4", "label": "seg1", "duration": 8.1}],
  "subtitles": [{"text": "第一句字幕", "start": 0.0, "duration": 2.3}]
}
```

两种模式:
- **materialized(推荐)**:`clips[]` 为已切好的独立文件,依次排布时间轴;`subtitles` 时间=成品时间轴。compile 自动把素材 staged 进草稿 `assets/video/`,lint 零修复全绿。
- **linked**:`source` + `selections[{source_start, source_end, subtitles(相对 selection)}]` + `fine_cuts{silence_delete[], retake_delete[]}`。转换器做"删区间→keep 子区间→时间轴拼接"和字幕源时间→轴时间映射。
  ⚠️ **linked 已知坑(实测)**:同一源文件多段(不同 sourceStart)时 capcut-cli 为每段建独立 material 且时长只记本段,剪映会把后段 clamp 到文件头播放。**多段场景勿用 linked,用 materialized;单段可用**。

细剪规则接入(全部只读检测,输出秒+微秒):
```bash
capcut detect-silence <media> --min-silence 3 --pad 0.1   # 删空档 → keeps 喂给切片段
capcut detect-retakes --srt <字幕.srt> --similarity 0.8    # 去重复表述 → drops 喂给 fine_cuts
```
`detect-retakes` 也可直接读已建草稿的字幕轨(`capcut detect-retakes <project>`)。

实测数据(2026-09-22):30s 测试"直播"(两段空档 3s/5s)→ keeps 3 段(8.1s/8.2s/6.1s)→ materialized 草稿 22.4s、3 视频段 + 3 字幕,compile warnings=0,lint **0 errors/0 warnings/0 info**,render 预览三字幕位置时长全部正确。

## 7. 与 clip-workflow.md 的组合建议

- clip-workflow 第 6 步 `trim_clips` 改为产出 EditPlan 所需的 clip 文件(keep 区间);
- 第 10 步按 §6 走 EditPlan 流水线;
- `detect-retakes` 需要先有字幕:在 clip-workflow 第 7 步(生成字幕)之后、交付工程之前执行,把 drops 写回 EditPlan `fine_cuts.retake_delete`(materialized 模式下,重拍检测在**单片段内**发生时才可删;跨片段依赖 linked 模式的能力,当前版本注意取舍)。