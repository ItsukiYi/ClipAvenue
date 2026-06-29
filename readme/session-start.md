# Session Start — 开发上下文快速恢复

## 当前任务 (最近一次改动)
1. 文件管理器重做 — 按主播分类/列表&网格/左滑删除 (刚完成, 待编译验证)
2. 房间UI重设计 — 封面背景+头像+脉冲动画+录制切换+编辑弹窗 (已完成)
3. QR登录修复 — B站双层code解析 (已完成, 待实地验证)

## 最近踩坑
- SwipeToDismissBox 需要 @OptIn(ExperimentalMaterial3Api::class)
- Icons.Filled.LiveTv/Videocam 在当前Compose BOM版本不存在 → 用emoji替代
- 文件预览黑屏 → 加了media3-extractor + 文件存在性检查
- 冷启动房间标题消失 → 需从DB加载last-known title

## 待完成
- 上传功能端到端测试
- 抖音直播支持 (参照 biliup douyin.rs)
- FLV缩略图生成 (grid视图封面)
- 弹幕录制
