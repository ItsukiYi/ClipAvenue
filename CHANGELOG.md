# Changelog — ClipAvenue

## v1.0.0 (2026-06-30)

### 🎬 核心功能
- **B站直播自动录制** — 添加直播间后自动检测开播/下播，支持轮询监控
- **纯 Python 录制引擎** — HTTP-FLV 直录，零 ffmpeg 依赖，参照 [BililiveRecorder](https://github.com/BililiveRecorder/BililiveRecorder) 和 [biliup](https://github.com/biliup/biliup)
- **画质选择** — 每个直播间独立设置（原画 10000 / 蓝光 400 / 超清 250 / 高清 150 / 流畅 80）
- **内置播放器** — ExoPlayer 支持 FLV 播放、全屏预览
- **B站扫码登录** — ZXing 本地生成 QR 码，Cookie 持久化存储，登录后解锁更高画质

### 🔔 智能通知
- 通知栏实时显示录制状态（时长 / 网速 / 文件大小）
- 开播/下播系统推送通知
- 前台 Service + WakeLock 确保后台录制不被系统杀掉

### 📁 文件管理
- 按主播自动分类（头像 + 封面图）
- 列表/网格双视图切换
- 一键系统播放器打开或 App 内预览
- 确认后安全删除

### 🎨 界面
- 极简黑白灰主题，深色模式自适应
- 直播间卡片：封面背景 + 脉冲动画 + 头像
- 仪表盘实时指标：文件时长 / 录制耗时 / 网速 / 速度比
- 编辑弹窗：修改备注 / 直播间 ID / 画质 / 删除

### 🛠️ 技术栈
- **UI**: Kotlin + Jetpack Compose + Material 3
- **引擎**: Python 3.8 (Chaquopy 嵌入)
- **播放器**: Media3 ExoPlayer
- **图像**: Coil + ZXing
- **数据库**: SQLite (5 张表 — rooms / live_sessions / recording_files / uploads / settings)
- **录制**: 纯 stdlib HTTP-FLV 直录（零第三方依赖）

### 🐛 修复（对比早期版本）
- 录制 FLV 文件损坏 → 改为"一个连接 = 一个文件"
- B站 QR 登录双层 code 解析
- SSL 证书主机名不匹配（CDN IP 节点）
- mcdn CDN 节点过滤（参照 BililiveRecorder）
- 录制超时优化（10s → 30s）
- 重复录制防护
- 添加直播间检测到开播立刻开始录制
- 文件管理器分类穿透平台层目录

### ⚠️ 已知限制
- 仅支持 B站直播平台（抖音开发中）
- 上传功能已实现但未完成端到端测试
- FLV 缩略图待实现（网格视图暂用占位图标）
- Android 16+ 公共目录写权限受限（默认存 app 专属外存）

### 🙏 致谢
本项目录制和上传协议参照了以下优秀开源项目：
- [biliup](https://github.com/biliup/biliup) — Rust/Python 直播录制与投稿工具
- [BililiveRecorder](https://github.com/BililiveRecorder/BililiveRecorder) — B站录播姬，C# FLV 直录标杆
