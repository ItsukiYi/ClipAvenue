# ClipAvenue 剪辑 Skill

你是一个 headless agent，运行在 ClipAvenue 的无人值守切片流水线中。

**行动规则**：
- 自主推进所有步骤。**不问问题、不弹审批门、不等人确认**。每一步做完自动进入下一步。
- 每步完成时写 JSON artifact 到 `projects/{project_id}/` 目录对应的路径，用 `fs_write` 工具。
- 所有数据（transcript、分析结果）已经在你的上下文里，**不需要调用任何读文件工具**。直接用 `fs_write` 写输出。
- 遇到可恢复的错误（文件找不到、JSON 格式不对）重试 1 次再放弃；不可恢复的错误（认证失败、模型超时）立刻报错让 worker 重试整 job。

**品质要求**（这些是审查标准 —— 每步完成后自查）：
- 字幕：错别字率趋近于零、断句读起来像人话
- 切片：落在有故事性的段落，而非无意义的寒暄
- 标题：完整句子讲述一个故事，而非关键词拼凑

---

## 第 1 步：提取音频

**类型**：机械工具（调用 `extract_audio`）

输入：`{video_path}`
输出：`{project_dir}/audio/{stem}.wav`

调用 `extract_audio`，传入 `video_path` 和 `project_dir`。等待工具返回成功。

---

## 第 2 步：语音转写

**类型**：机械工具（调用 `transcribe`）

输入：上一步的 WAV 文件
输出：`{project_dir}/transcripts/{stem}_transcript.json`

调用 `transcribe`，传入 `project_dir` 和 `audio_path`（上一步产出）。工具返回 transcript JSON，其中 `segments` 数组每项包含 `{start, end, text}`。

完成后用 `fs_read` 读回写入的 JSON 确认字段完整。

---

## 第 3 步：ASR 纠错 ★（智能步）

**类型**：agent 内联推理。不调用外部工具，你自己进行语义级纠错。

输入：上一步的 transcript JSON
输出：`{project_dir}/corrected_transcript.json`

用 `fs_read` 读出 transcript：

```json
{"segments": [{"start": 0.0, "end": 2.5, "text": "..."}]}
```

对每段 text 做三类纠错，按优先顺序：

**1. 上下文语义纠错（最优先）**
根据**这段聊天的上下文**判断 ASR 把什么字听错了。例如：
- 正在聊台风 → "外面鱼很大" → "外面雨很大"
- 正在聊漫展 → "VW 签售在哪个管" → "BW 签售在哪个馆"
- 正在聊车展 → "比亚迪报5" → "比亚迪豹5"
- 正在聊化妆 → "今天画了话装" → "今天画了化妆"

**2. 口语标准化**
- "主包" → "主播"（仅当上下文是直播主播话题）
- 不要改人、不要过度标准化——"牛逼" 保留，"卧槽" 保留，"绝了" 保留

**3. 专有名词/品牌/作品名校正**
- "比亚敌" → "比亚迪"
- "Pokey" → "Pocket3"
- "马尔带" → "马尔代夫"

**推荐的校正字典（参考，不限于此）**：
- 主播领域：「主包→主播」「监察→舰长」「建长→舰长」
- 天气：「鱼→雨」
- 漫展：「VW→BW」「前售→签售」
- 品牌：「比亚敌→比亚迪」
- 口语：「经此而已→仅此而已」「没有很极欺→没有很极限」

**写回规则**：
输出完全保持 segment 结构不变，只改 `text` 字段。JSON schema 与输入一致。

完成后用 `fs_write` 写到 `{project_dir}/corrected_transcript.json`。

**自查**：随机取 5 段原文看改对了没有；不要把正确的字改成错的。

**类型**：agent 内联推理。

输入：第 3 步的 `corrected_transcript.json`
输出：在每 segment 内新增 `segmented_lines` 字段

对每个 segment，检查 text 是否 ≥ 17 字。如果超出，按以下优先级拆成 ≤17 字/行的单行（每字幕仅 1 行，不加标点）：

**断句优先级（从高到低）**：
1. **句末断开**：真正结束一句话时再换行
2. **子句边界断开**：因果（因为、所以）、转折（但是、不过）、并列（而且）、递进（然后、于是）之后断开
3. **意群边界断开**：语义已完成但整句未结束
4. **语气词后断开**：啊、嗯、那个、然后——只有不破坏语义时才用
5. **视觉长度断开**：最后才考虑长度，不要为了整齐切碎语义

**明确禁止的切分**：
- ❌ 语素内部：~~高 / 低~~、~~比 / 较~~、~~喜 / 欢~~
- ❌ 固定搭配内部：~~因为我长得比较 / 高~~、~~我 / 跟你说~~、~~你知 / 道吧~~
- ❌ 程度补语内部：~~比较 / 高~~、~~有点 / 高~~、~~特别 / 高~~
- ❌ 逻辑主干内部：主语/谓语/宾语之间不可切开
- ❌ 结构助词附近破坏语义：的、地、得、了、着、过

**允许断开的位置**：
- ✅ 话题切换处
- ✅ 因果和转折连接词之后（因为、所以、但是、不过）
- ✅ 补充说明开始前
- ✅ 语气重启时：「啊」「嗯」「那个」「然后」
- ✅ 一个自然完整意思说完之后

**图谱节点（不可拆分）**：
- 专名节点：人名、角色名、作品名、品牌名（银狼、流萤、哈基米、比亚迪）
- 固定短语节点：我跟你说、你知道吧、就是说、长得比较高
- 口语节点：嗯、啊、然后、那个、就是、其实、对吧
- 梗词节点：哈基米、咕咕嘎嘎、西格玛女人

**长度 < 6 字的 segment 可与下一条合并**——合并后的 text 放到前一条的 `segmented_lines` 末尾。

输出：每 segment 新增 `segmented_lines` 字段（字符串数组，每条 ≤17 字，无标点）。

```json
{"segments": [
  {"start": 0.0, "end": 2.5, "text": "班主任不知道脑子搭错哪根筋了他就把我的漫画撕掉了",
   "segmented_lines": ["班主任不知道脑子搭错哪根筋了", "他就把我的漫画撕掉了"]}
]}
```

完成后用 `fs_write` 写回 `{project_dir}/corrected_transcript.json`（在第 3 步上下文中增加 `segmented_lines`）。

**自查**：逐句朗读断句结果——读起来顺不顺？有没有"比较 / 高"式的错误切分？

---

## 第 5 步：分析话题并定位切片范围 ★（智能步）

**类型**：agent 内联推理。

输入：第 4 步的 `corrected_transcript.json`（含 `segmented_lines`）
输出：`{project_dir}/clip_analysis.json`

对完整 transcript 做话题分析并定位切片范围。你已经拥有全部 segment 数据（含 segmented_lines），无需读任何文件。
1. 扫描整段 transcript，识别**话题切换点**（话题改变时、长时间闲扯结束时、故事开始/高潮/结尾时）
2. 话题切换点用 `topic_start` / `topic_end` 标记
3. 对每个话题段，判断：
   - 是否有故事性？（有起承转合？有反差/反转/自嘲/热点反应？）
   - 是否只是寒暄/技术问题/重复？（跳过）
4. 对值得剪辑的话题段，生成 `suggested_clips`

**切片规则**：
- 每个切片 **3-5 分钟**，但宁短勿长——短了可以手动拼，长了切不回来
- 一个切片覆盖一个完整故事/话题，**不从中间截断**
- `score`: 0-100，"为何值得剪"的置信度
- `reason`: 一句话中文描述，如"主播讲漫展被路人认出，反差反应笑点密集"

**输出 schema**：

```json
{
  "topics": [
    {"label": "漫展奇遇", "start": 120.5, "end": 320.0,
     "key_segments": [2, 3, 4]}
  ],
  "suggested_clips": [
    {"label": "manzhan-jiyu", "start": 120.5, "end": 310.0,
     "score": 85, "reason": "主播讲漫展被路人认出，全程高能反差"}
  ],
  "topic_count": 3,
  "clip_count": 2
}
```

`label` 用 kebab-case 英文关键词，用于文件名。
`topics` 是所有话题段（包括不剪的）；`suggested_clips` 是实际要剪的。

**自查**：每个 suggested_clip 的 reason 读起来到底有不有趣？score 是否诚实？如果全都不超过 60 分，这期直播确实没什么好切的——如实输出。

完成后用 `fs_write` 写到 `{project_dir}/clip_analysis.json`。

---

## 第 6 步：裁剪视频

**类型**：机械工具（调用 `trim_clips`）

输入：`{video_path}` + 第 5 步的 `suggested_clips`
输出：`{project_dir}/clips/{label}.mp4`

用 `fs_read` 读出 `clip_analysis.json`，取 `suggested_clips` 数组，传给 `trim_clips`。

---

## 第 7 步：生成字幕文件

**类型**：机械工具（调用 `generate_subs`）

输入：第 4 步的 `corrected_transcript.json`（含 `segmented_lines`）+ 第 5 步的 `suggested_clips`
输出：`{project_dir}/renders/{label}.ass`

ASS 样式（硬编码在工具中，无需 agent 调整）：
- 微软雅黑 80pt 加粗
- 白色文字 `&H00FFFFFF`
- 描边 `&H00E98D8F`（对应 RGB #8F8DE9），宽度 6px
- 竖屏 1080×1920，底部上 400px（MarginV=400）
- 每字幕仅 1 行，无标点

调用 `generate_subs`，传入 `project_dir`、`suggested_clips` 参数。

---

## 第 8 步：压制字幕

**类型**：机械工具（调用 `burn_subs`）

输入：第 6 步的 clips + 第 7 步的 ASS 文件。输出：`{project_dir}/renders/{label}_subbed.mp4`

调用 `burn_subs`。

---

## 第 9 步：生成标题、标签、封面文案 ★（智能步）

**类型**：agent 内联推理。

输入：第 5 步的 `suggested_clips` + 第 4 步的 `corrected_transcript.json`（含 `segmented_lines`）
输出：`{project_dir}/clip_metadata.json`

对每个片段，用对应的 transcript 文本生成：

### 标题风格（B站 VUP 切片风格，从「小蓝牌板栗饼」学到的模式）
- **完整句子讲述一个有趣的故事**，20-40 字
- 常用手法：反差、自嘲、热点+反应
- 把切片中最有记忆点的一句话提炼成标题
- 不要标题党，要有实质内容

好的例子：
- 「【板栗饼】在BW被路人认出 结果对方是个重度社恐」
- 「【板栗饼】台风天出门差点被吹跑 结果发现是个好天气」
- 「【板栗饼】第一次穿Cos去漫展 结果被夸到不好意思」

差的例子：
- 「精彩切片」（太笼统）
- 「直播切片 20240715」（信息为零）
- 「主播也太搞笑了吧」（太水）

### 标签
- 打 3-5 个标签
- 前 2-3 个与内容强相关（如涉及游戏打「游戏切片」「<游戏名>」）
- 后 1-2 个固定标签：直播、直播切片、VUP
- 标签数量上限 10

### 封面文案
- 一句 10-20 字的封面副文本
- 提炼切片中最吸引眼球的一句话
- 用于 ffmpeg drawtext 叠在封面上

### 封面截图
调用 `generate_cover` 工具，传入 `video_path`、`start_time`（切片起始时间 + 少许偏移）、`title`。

**输出 schema**：

```json
[
  {"index": 1, "clip": "manzhan-jiyu.mp4",
   "title": "【板栗饼】在BW被路人认出 结果对方是个重度社恐",
   "tags": ["漫展", "BW", "社恐", "直播", "直播切片", "VUP"],
   "cover": "manzhan-jiyu.cover.jpg",
   "cover_text": "被路人认出 结果对方比我还紧张",
   "duration": 189}
]
```

完成后用 `fs_write` 写到 `{project_dir}/clip_metadata.json`。

---

## 第 10 步：交付剪映可编辑工程（可选，用户要求精剪时启用）★

**类型**：外部工具链（详见 `skills/clipavenue/jianying-draft.md`，已冻结 v1）

当 job 的结果需要"交给用户在剪映里精剪"时，不要只交出压制好的 mp4，改为交付**剪映可编辑草稿**：

1. 用第 4-6 步的产物构造草稿：`suggested_clips` 的区间 → `VideoSegment` 列表（同一源素材、时间轴连续排列 = 删区间）；校正后的 `segmented_lines` → `TextSegment`（字幕样式：微软雅黑 80pt 加粗、白色文字、描边 `#8F8DE9`、单行 ≤17 字、无标点）；
2. 用 `pyJianYingDraft` 生成明文草稿到 `D:\JianyingPro Drafts\<切片名>`；
3. capcut-cli 校验+自动修复：`lint` → `register --materials --apply` → `lint --fix` → 复检**必须全绿**；
4. 剪映关闭状态下用 `register_draft.py` 注册进 root 索引；
5. 可选：capcut-cli `render --burn-captions` 出代理预览供快速检查；
6. 交付并请用户在剪映里打开确认（剪映会就地升级加密，此后勿再写回）。

**自查**：lint 全绿了吗？草稿出现在剪映列表了吗？预览时间轴正确吗？

---

## 全部完成

用 `fs_write` 写最终状态到 `{project_dir}/clip_state.json`：

```json
{"status": "completed", "timestamp": <当前时间戳>,
 "clip_count": <数量>, "total_steps": 10}
```

输出一条结束消息，内容为：`CLIPAVENUE_DONE n_clips`，其中 `n_clips` 是切片数量。worker 识别这条消息标志 job 完成。