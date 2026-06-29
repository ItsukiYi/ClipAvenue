## ClipAvenue
适用于Android设备的哔哩哔哩、抖音直播录制app
### 🎬 核心功能
- **B站直播自动录制** — 添加直播间后自动检测开播/下播，轮询监控，默认1分钟间隔
- **纯 Python 录制引擎** — HTTP-FLV 直录，零 ffmpeg 依赖，参照 [BililiveRecorder](https://github.com/BililiveRecorder/BililiveRecorder) 和 [biliup](https://github.com/biliup/biliup)
- **画质选择** — 每个直播间独立设置（原画 10000 / 蓝光 400 / 超清 250 / 高清 150 / 流畅 80）
- **B站扫码登录** — Cookie 持久化存储，登录后解锁真原画

### 🔔 智能通知
- 通知栏实时显示录制状态（时长 / 网速 / 文件大小）
- 开播/下播系统推送通知

### 📁 文件管理
- 按主播分类，支持列表/网格双视图切换

### 🛠️ 技术栈
- **UI**: Kotlin + Jetpack Compose + Material 3
- **引擎**: Python 3.8 (Chaquopy 嵌入)
- **播放器**: Media3 ExoPlayer
- **图像**: Coil + ZXing
- **数据库**: SQLite
- **录制**: 纯 stdlib HTTP-FLV 直录

### ⚠️ 已知问题
- 仅支持bilibili（抖音开发中）
- 上传功能已实现但未完成测试
- FLV 缩略图待实现
- 内置播放器不明原因黑屏
- Android 16+ 公共目录写权限受限，目前只能存储在/Android/data 里

### ☢️ 潜在的高危问题
- 异常的app存储占用（测试中出现100+GB）
- 前台显示多直播流时异常发热
- 对Cookie等敏感信息未做加密，请注意隐私安全

## 构建
Android Studio 打开项目 → Sync Gradle → Build APK
