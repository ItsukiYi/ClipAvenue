# Session Start — 开发上下文快速恢复

## 当前任务
1. QR 扫码登录 — B站 API 双层 code 解析修复 (待验证)
2. 录制断连优化 — SSL + 超时 + 流地址刷新
3. 画质选择 — 每个直播间独立设置

## 最近踩坑 (详见 lessons-learned.md)
- B站 QR 轮询 API 改为双层 code 结构
- Android 16 scoped storage 限制公共目录写入
- urllib socket 模式在 Android 上不稳定
- 录制文件损坏 — FLV mid-tag 切分 → 改成每连接一个文件

## 待完成
- 上传功能 (B站 web投稿已实现, 待测试)
- 抖音支持
- 弹幕录制
