# 踩坑档案 — ClipAvenue

## Android
1. **Android 16 Scoped Storage 限制** — 公共目录不可写, 用 app 专属外存
2. **Python SSL 证书问题** — CDN IP 主机名不匹配 → `ssl.CERT_NONE`
3. **Raw socket 在 Android 上不稳定** → 直接用 `urlopen`
4. **Compose BOM 版本限制** — 部分图标(Icons.Filled.Videocam等)不存在 → 用emoji

## B站 API
5. **QR 登录 API 双层 code** — 外层 HTTP code=0, 真正状态在 data.code
6. **mcdn CDN 节点不稳定** → 过滤 .mcdn.bilivideo.cn, 全mcdn时保留
7. **直播流 URL 有时效** — 断连后必须重新调 playUrl 获取新地址
8. **QR 轮询不能带 Cookie** — generate_qr 设的跟踪 Cookie 会让 B站误判已登录

## Gradle/构建
9. **Gradle 9.x 不兼容 Chaquopy 15.x** → Gradle 8.10 + AGP 8.2.2
10. **Python 3.14 host 不兼容 Chaquopy pip** → 零 pip 依赖 (纯 stdlib)

## UI/Compose
11. **SwipeToDismissBox 是实验性API** → 需 @OptIn(ExperimentalMaterial3Api::class)
12. **文件预览黑屏** → media3-extractor + 文件存在性检查

## 录制
13. **FLV 文件不能在中途切分** → 一个HTTP连接 = 一个完整文件
14. **录制 10s 超时太短** → 改为 30s (匹配 biliup)
15. **重复录制** → 同房间多线程 → startRecording 加防重复检查
