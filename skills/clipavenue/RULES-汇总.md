# ClipAvenue 规则汇总(冻结 v1,2026-09-22)

> 本文把所有散落在代码/skill/工作流文档中的规则集中成一份,供 agent 与人工对照。
> 来源:LIVESTREAM_CLIP_WORKFLOW.md、skills/clipavenue/clip-workflow.md、skills/clipavenue/jianying-draft.md、
> clipavenue/clipper/{correction,segmenter,analyzer,metadata}.py。

---

## A. 内容规则(定"剪什么、怎么呈现")

### A1. 字幕样式
| 项 | 值 |
|---|---|
| 字体 | 微软雅黑 |
| 字号 | 80pt(剪映工程中约 48pt,竖屏 1080x1920) |
| 加粗 | 是 |
| 颜色 | 白色 `#FFFFFF` |
| 描边 | `#8F8DE9`,宽 6px |
| 位置 | 竖屏底部上 400px|
| 行数 | 每字幕仅 1 行 |
| 字数 | ≤17 字 |
| 标点 | **不带标点** |
| 时长 | 每句 3-5 秒(超过 7s 视为问题) |

### A2. 断句规则(ASR 知识图谱,先保逻辑再保节奏最后排版)
优先级:句末断开 > 子句边界(因为/所以/但是/不过/而且/然后)> 意群边界 > 语气词后 > 视觉长度。
- ❌ 禁止切开:语素内部(比/较)、固定搭配内部(因为我长得比较/高)、结构助词(的/地/得/了/着/过)、程度补语(比较/高)、逻辑主干(主谓宾之间)。
- ✅ 允许断开:话题切换处、因果/转折连接词之后、补充说明开始前、语气重启(啊/嗯/那个/然后)、一个完整意思说完后。
- 图谱节点不可拆:专名(银狼/流萤/比亚迪)、固定短语(我跟你说/你知道吧)、口语词(然后/就是/其实/对吧)、梗词(哈基米/西格玛女人)。
- 聚合规则:<6 字与下一条合并;>17 字必须拆。

### A3. ASR 纠错规则(三阶段)
1. **字典纠错**(已知错误 raw→corrected):主播域(主包→主播、监察/见长→舰长)、品牌(比亚敌→比亚迪、Pokey→Pocket3)、地名(天伏/天服机场→天府机场、马尔带→马尔代夫)、口语(经此而已→仅此而已、没有很极欺→没有很极限)等,可持续扩充。
2. **上下文语义纠错**(话题感知):按当段话题推断 ASR 听错,如聊台风→"外面鱼很大"→"外面雨很大";聊漫展→"VW 前售在哪"→"BW 签售在哪";聊车展→"比亚迪报5"→"比亚迪豹5"。
3. **同音兜底**(拼音相似度,未知错误)。
- 只改 text,保持 segment 时间戳结构不变;不得过度标准化("牛逼/卧槽/绝了"保留)。

### A4. 选题/切片规则(agent 第 5 步)
- 切片时长 **3-5 分钟,宁短勿长**(短了能拼,长了切不回)。
- **一个切片覆盖一个完整故事/话题,不从中间截断**。
- 跳过:寒暄、技术问答、纯重复段。
- score(0-100)必须诚实;全部 <60 如实报告"本期无可切内容"。
- reason:一句话中文说明"为何值得剪"。

### A5. 标题/标签/封面规则(B站 VUP 切片风格)
- 标题:完整句子讲一个有趣故事,20-40 字;手法:反差、自嘲、热点+反应;**不标题党、有实质内容**。
- 标签:3-5 个;前 2-3 个内容强相关,后 1-2 个固定(直播、直播切片、VUP)。
- 封面文案:一句 10-20 字,提炼最抓眼球的一句。
- 封面图:切片起始帧 + 少许偏移截取。

### A6. 细剪规则(Phase 2,capcut-cli 检测)
| 规则 | 参数 | 落点 |
|---|---|---|
| 删空档 | `detect-silence --min-silence 3 --threshold-db -30 --pad 0.1` | keeps→切片段;silences→fine_cuts.silence_delete |
| 去重复表述 | `detect-retakes --similarity 0.8 --min-words 4 --window 60`,保留**后一次** | drops→fine_cuts.retake_delete |
| 场景切分 | `detect-scenes --threshold 0.4` | 长视频预分段种子 |

---

## B. 工程交付规则(skill jianying-draft.md)

### B1. 标准 5 步链
1. **生成**:pyJianYingDraft 写明文草稿(建议 materialized:用已切好的独立 clip 文件)。
2. **校验**:`capcut lint`。
3. **修复**:`capcut register --materials --apply` → `capcut lint --fix` → 复检。
4. **注册**:剪映关闭时 `register_draft.py <草稿目录> [--duration <秒>]`。
5. **预览**:`capcut render --burn-captions`(代理预览,非最终渲染)。

### B2. 验收线
- **lint 必须全绿(errors=0, warnings=0, info=0)才可交付**。
- 交付后人工在剪映打开确认 = 最终验收(程序化无法替代)。

### B3. 安全规则(硬性)
1. **剪映运行中禁止写**:任何草稿/索引写入前查 `Get-Process -Name "*Jianying*"`;剪映退出会用内存索引覆盖 root_meta_info.json。
2. **剪映打开后草稿被加密升级 = 只读**:`draft_content.json` 变加密(base64 高熵);要改就重新生成一份明文,不逆向加密(capcut-cli 官方只检测不解密)。
3. **素材路径**:优先让素材进草稿 `assets/video/`(lint --fix 自动 staged)或固定在草稿同盘;迁移草稿必须带素材。
4. **单位换算**:剪映时间轴=微秒(µs);root 索引 `tm_duration`=100ns(WINDOWS FILETIME 语义);CLI 参数多用秒。
5. **版本兼容**:冻结在剪映 11.4.1;剪映升级后先跑一轮"生成→lint→打开"回归。
6. **写入前自动备份**:register 脚本对 root_meta_info.json 打时间戳备份。

### B4. EditPlan 规则
- **默认 materialized 模式**:`clips[]`(独立文件)+ `subtitles`(成品时间轴时间);compile 自动 staged 素材、lint 零修复。
- **linked 模式**(引用源 + sourceStart)**:仅单段可用**;多段同一源文件有已知坑(capcut-cli 每段建独立 material 且时长只记本段,剪映 clamp 从头播)。
- 字幕映射:落在删除区间内的字幕会被丢弃;keep 区间按序拼接、轴位置累计。
- name 必须是纯文件夹名(禁止路径字符),canvas 竖屏 9:16 / 1080x1920 / 30fps。

---

## C. 流程规则(9 步 + 第 10 步)

1. 提取音频(16kHz 单声道 WAV)
2. 语音转写(faster-whisper tiny,中文)
3. ASR 纠错(规则 A3)
4. 断句(规则 A2)
5. 话题分析 + 切片定位(规则 A4)
6. 粗剪(ffmpeg 按时间戳;也可作为 materialized 素材来源)
7. 字幕生成(规则 A1)
8. 压制字幕 / 或直接进入第 10 步
9. 标题/标签/封面(规则 A5)
10. **交付剪映可编辑工程**(规则 B;用户要求精剪时启用)— 替换纯成片交付

---

## D. 工具操作规则(ffmpeg/ASS)

- ffmpeg 剪切必须 **re-encode**(-c:v libx264 -c:a aac),`-c copy` 时间不准。
- ASS 烧录用**相对路径**,Windows 绝对路径/盘符会让 subtitles filter 解析失败。
- **不要文本替换改 ASS 文件**(replace_all 删标点会破坏格式),一律脚本重新生成。
- ASS 文件 UTF-8 无 BOM;颜色为 `&HAABBGGRR` 格式(#8F8DE9 → &H00E98D8F)。
- 剪映工程对齐:1080x1920 竖屏、字幕单行 ≤17 字无标点。