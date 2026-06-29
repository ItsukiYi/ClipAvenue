# ClipAvenue — 直播录制自动上传App

Android B站直播录制工具，支持自动监控、原画录制、视频预览。

## 技术栈
- **UI**: Kotlin + Jetpack Compose + Material 3
- **引擎**: Python 3.8 (Chaquopy 嵌入)
- **录制**: 纯 Python HTTP-FLV 直录，零 ffmpeg 依赖
- **存储**: SQLite 数据库
- **参考**: [biliup](https://github.com/biliup/biliup) + [BililiveRecorder](https://github.com/BililiveRecorder/BililiveRecorder)

## 功能
- 轮询监控 + 自动录制
- 画质选择 (原画/蓝光/超清/高清/流畅)
- 内置播放器 (ExoPlayer)
- B站扫码登录 + Cookie 持久化
- 文件管理器 + 日志查看器
- 配置持久化 (重启恢复)

## 构建
Android Studio 打开项目 → Sync Gradle → Build APK

## 开发文档
- [规矩书](readme/CLAUDE.md)
- [进度](readme/PROGRESS.md)
- [验收](readme/VERIFY.md)
- [踩坑](readme/lessons-learned.md)
