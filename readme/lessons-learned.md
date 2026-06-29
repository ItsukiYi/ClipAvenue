# 踩坑档案 — ClipAvenue

## Android
1. **Android 16 Scoped Storage 限制**
   - `/storage/emulated/0/Movies/biliup/` 不可写入
   - 需用 app 专属外存目录 `getExternalFilesDir(null)`
   - 或 SAF 让用户手动选择目录

2. **Python `urlopen` 在 Android 上 SSL 证书问题**
   - CDN IP 主机名不匹配证书 → 需 `ssl.CERT_NONE + check_hostname=False`

3. **Raw socket 在 Android 上不稳定**
   - `socket.create_connection` 经常超时 15s → 直接改用 `urlopen`

## B站 API
4. **QR 登录 API 双层 code 结构**
   - 旧: `{"code": 86101}` → 直接读 code
   - 新: `{"code": 0, "data": {"code": 86101}}` → 需读 `data.code`

5. **mcdn CDN 节点不稳定**
   - 过滤 `.mcdn.bilivideo.cn` 域名 (参照 BililiveRecorder)
   - 保底: 全 mcdn 时不过滤

6. **B站直播流 URL 有时效**
   - 断连后必须重新调用 playUrl API 获取新地址
   - 不能复用旧 URL

## Gradle/构建
7. **Gradle 9.x 不兼容 Chaquopy 15.x**
   - `org.gradle.util.VersionNumber` 在 Gradle 9 被删除
   - 必须用 Gradle 8.10 + AGP 8.2.2 + Chaquopy 15.0.1

8. **Python 3.14 host 不兼容 Chaquopy pip**
   - `cgi` 模块被删除 → 改用零 pip 依赖 (纯 stdlib)

## 录制
9. **FLV 文件不能在中途切分**
   - 切在 tag 中间导致文件损坏
   - 正确做法: 一个 HTTP 连接 = 一个完整文件

10. **录制 10s 超时太短**
    - B站直播数据稀疏时触发假断连
    - 改为 30s (匹配 biliup)
