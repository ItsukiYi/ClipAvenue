# 直播切片工作流

## 概述

从长直播录播视频中，自动识别语音、分析话题、剪辑精彩片段、压制字幕的完整流水线。

## 环境依赖

- Python 3.10+（虚拟环境 `.venv/`）
- FFmpeg（含 ffprobe）
- Node.js 18+
- Python 包：`faster-whisper`、`huggingface_hub<0.27`（hf-mirror 兼容）

## 字幕样式规范

| 参数 | 值 |
|---|---|
| 字体 | 微软雅黑 |
| 字号 | 80pt |
| 加粗 | 是 |
| 文字颜色 | 白色 `&H00FFFFFF` |
| 描边颜色 | `#8F8DE9` → ASS格式 `&H00E98D8F` |
| 描边宽度 | 6px |
| 文字位置 | 竖屏从上至下 3/4 处（MarginV=400，底部上400px） |
| 每行字数 | ≤17 字（确保不超出 1080px 横向范围） |
| 行数 | **每字幕仅 1 行** |
| 标点 | **不要标点符号** |
| 每句时长 | 3-5 秒 |

## 工作流步骤

### 第1步：提取音频

从视频文件中提取 16kHz 单声道 WAV：

```bash
ffmpeg -i input.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 output.wav -y
```

### 第2步：语音转文字

使用 `faster-whisper` 的 `tiny` 模型（速度快，中文尚可）。先确保能从 HuggingFace 镜像站下载模型：

```python
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
# 如果遇到 XET 协议 401 错误，降级 huggingface_hub：
# pip install "huggingface_hub<0.27"
```

使用 OpenMontage 的 `Transcriber` 工具：

```python
from tools.analysis.transcriber import Transcriber
t = Transcriber()
result = t.execute({
    'input_path': 'audio.wav',
    'model_size': 'tiny',
    'language': 'zh',
    'output_dir': 'output_dir'
})
```

输出为 JSON 文件，包含带时间戳的 segments。

### 第3步：分析话题，确定切片范围

阅读转写文本，标记最有故事性/趣味性的段落。

### 第4步：裁剪原始视频

使用 ffmpeg 精确裁剪（**一定要用 re-encode 模式，不要用 `-c copy`**，否则时间不准）：

```bash
ffmpeg -i source.mp4 -ss START_TIME -to END_TIME \
  -c:v libx264 -crf 23 -preset fast \
  -c:a aac -b:a 128k \
  output_clip.mp4 -y
```

### 第5步：AI校正转写文本

Whisper tiny 模型的中文识别有很多错别字，需要逐条人工/LLM校正。

**典型错误模式：**
- 同音字错误：「知音漫客」→「之一漫客」「一漫客」
- 方言/口语识别不准：「脑子搭错那根筋了」→「打错拿根金了」
- 专有名词错误：「肯德基」→「肯的机」「车站」→「车家你」
- 上下文错误：「校门」→「笑门」「施压」→「失压」

**校正方法：** 建立 `raw_text → corrected_text` 的字典映射，逐条替换。

### 第6步：断句（单行约束 + ASR 知识图谱断句规范）

由于字幕为 **单行 ≤17 字**，需要对原始 segment 进行拆分。断句应遵循 **ASR 知识图谱规范**——优先保证"人话感"，避免把语素、固定搭配和逻辑短语切碎。

#### 断句优先级（从高到低）

1. **句末断开**：真正结束一句话时再换行
2. **子句边界断开**：因果、转折、并列、举例、递进之后
3. **意群边界断开**：语义已完成但整句未结束
4. **语气词后断开**：只有在不破坏上文逻辑时才允许
5. **视觉长度断开**：最后才考虑长度，不要为了整齐切碎语义

#### 明确禁止的切分

- ❌ 语素内部：~~高 / 低~~、~~比 / 较~~、~~喜 / 欢~~
- ❌ 固定搭配内部：~~因为我长得比较 / 高~~、~~我 / 跟你说~~、~~你知 / 道吧~~
- ❌ 结构助词附近破坏语义：的、地、得、了、着、过
- ❌ 程度补语内部：~~比较 / 高~~、~~有点 / 高~~、~~特别 / 高~~
- ❌ 逻辑主干内部：主语/谓语/宾语之间不要随意切开

#### 允许断开的位置

- ✅ 话题切换处
- ✅ 因果和转折连接词之后（因为、所以、但是、不过）
- ✅ 补充说明开始前
- ✅ 语气重启时："啊""嗯""那个""然后"
- ✅ 一个自然完整意思说完之后

#### 图谱节点类型（断句时识别这些不可拆分的节点）

| 节点类型 | 说明 | 例子 |
|---------|------|------|
| 专名节点 | 人名、角色名、作品名、品牌名 | 银狼、流萤、哈基米、LLM、比亚迪 |
| 固定短语节点 | 不可切分的固定表达 | 我跟你说、你知道吧、就是说、长得比较高 |
| 口语节点 | 口头禅、停顿词 | 嗯、啊、然后、那个、就是、其实、对吧 |
| 梗词节点 | 网络梗、方言词 | 哈基米、咕咕嘎嘎、西格玛女人 |

#### 分段逻辑

- 保留每个 segment 独立成一句（大部分原始 segment 已够短）
- 长度 > 17 字的 segment 需要按上述优先级拆成多条
- 长度 < 6 字的 segment 可与下一条合并
- 拆分时优先在**子句边界**（因为、所以、但是、不过、然后）后断开，其次在**虚词**（的、了、是、就、也、在、把、跟、和）后断开
- 例句（正确）：`班主任不知道脑子搭错哪根筋了/他就把我的漫画撕掉了`
- 例句（错误）：~~因为我长得比较 / 高~~ → 应为~~因为我长得比较高~~（固定搭配不拆）

```python
# 断句逻辑核心 — 先保逻辑，再保节奏，最后才是排版
MAX_CHARS_PER_LINE = 17

# 子句边界连接词（优先级高 — 在此处断开保留语义完整性）
CLAUSE_BOUNDARIES = ["因为", "所以", "但是", "不过", "而且", "然后", "但是", "虽然", "如果", "于是"]

# 虚词断点（优先级中 — 语法边界）
FUNCTION_WORDS = ["的", "了", "是", "就", "也", "在", "把", "跟", "和", "吧", "吗", "呢", "啊"]

# 不可拆分固定搭配（以及专名）由 WORDS 集合保护 — 断句时跳过这些词

if len(text) > MAX_CHARS_PER_LINE:
    # 优先在子句边界断开
    for sep in CLAUSE_BOUNDARIES:
        pos = text.rfind(sep, 0, MAX_CHARS_PER_LINE + 3)
        if pos > MAX_CHARS_PER_LINE * 0.4:
            # 在连接词之后断开（保留连接词在上行）
            pos += len(sep)
            break
    else:
        # 回退到虚词断开
        for sep in FUNCTION_WORDS:
            pos = chunk.rfind(sep)
            if pos > MAX_CHARS_PER_LINE * 0.4:
                # 在虚词后断开
                break
```

#### 一句话原则

先保逻辑，再保节奏，最后才是排版。

### 第7步：生成 ASS 字幕文件

```ass
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,微软雅黑,80,&H00FFFFFF,&H000000FF,&H00E98D8F,&H80000000,1,0,0,0,100,100,0,0,1,6,1,2,100,100,400,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.24,Default,,0,0,0,,确实算因为我有一个
Dialogue: 0,0:00:02.24,0:00:03.64,Default,,0,0,0,,非常经典的事例
```

**关于 ASS 颜色格式：** ASS 使用 `&HAABBGGRR` 格式（Alpha-蓝-绿-红）。RGB `#8F8DE9` 在 ASS 中为 `&H00E98D8F`（BGRA 字节序反转）。

**注意：** 绝对不要用文本替换的方式直接修改生成的 ASS 文件（如 `replace_all` 删标点），这会破坏格式结构。所有修改应通过脚本重新生成。

### 第8步：压制字幕到视频

必须使用**相对路径**（ffmpeg 的 subtitles filter 对 Windows 绝对路径解析有问题）：

```bash
ffmpeg -i clip.mp4 \
  -vf "subtitles=subs.ass:original_size=1080x1920" \
  -c:v libx264 -crf 23 -preset fast \
  -c:a copy \
  output.mp4 -y
```

## 常见问题

### Q: ffmpeg 报错 `Unable to parse "original_size" option value`
路径问题。ASS 文件路径含 Windows 盘符 `/d/` 时，ffmpeg 可能把路径解析成 `original_size` 参数值。改用相对路径。

### Q: HuggingFace 下载模型报 401/超时
国内网络问题：
1. 设置镜像：`export HF_ENDPOINT=https://hf-mirror.com`
2. 降级 huggingface_hub：`pip install "huggingface_hub<0.27"`（新版用 XET 协议，镜像不支持）

### Q: ffmpeg 剪切出的时长不准
用 `-c copy` 时 ffmpeg 只能关键帧对齐。需要精确到秒级的切割，必须用 `-c:v libx264 -c:a aac` 重新编码。

### Q: ASS 字幕乱码/不显示
- 确保 ASS 文件是 UTF-8 编码（无 BOM）
- 检查字体名是否正确（Windows 用「微软雅黑」）
- 检查时间格式：`H:MM:SS.cc`（百分秒，两位小数）

### Q: 字幕长度超出屏幕
在 1080px 宽的竖屏视频中，80pt 字体每个汉字约占 56px。合理上限为 17 字。如果超了，减小字号或拆分句子。