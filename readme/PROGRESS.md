# 进度仪表盘 — ClipAvenue

## NOW (最多3个)
1. 🟡 文件管理器完善 — FLV缩略图生成 / 预览黑屏修复
2. 🟡 上传功能端到端测试 — B站投稿流程在 App 内跑通
3. 🟢 抖音直播支持 — API 对接 (参照 biliup douyin.rs)

## NEXT (排队中)
1. 弹幕录制 — WebSocket 接入
2. 后台录制保活优化
3. 多平台支持扩展

## LATER (想法)
1. 剪辑功能 — 录制片段合并/裁剪
2. Google Play 发布
3. 多语言支持

## 已完成 (归档)
- ✅ v1.0 基础架构 — Kotlin/Compose + Chaquopy Python
- ✅ 纯 Python 录制引擎 — HTTP-FLV 直录 (参照 BililiveRecorder)
- ✅ SQLite 数据库持久化 (5张表)
- ✅ 轮询自动录制 + 下播确认 + 画质选择
- ✅ ExoPlayer 内置播放器
- ✅ B站扫码登录 (ZXing本地QR生成 + Cookie持久化)
- ✅ 灰度配色主题
- ✅ 文件管理器 v1 (按主播分类/列表&网格双模式/左滑删除)
- ✅ 直播间卡片重设计 (封面背景/头像/脉冲动画/录制切换/编辑弹窗)
- ✅ QR登录修复 (双层code: data.code)
- ✅ 录制稳定性 (SSL跳过/30s超时/URL刷新/mcdn过滤)
- ✅ 开发规范体系 (readme/)
