# 规矩书 — ClipAvenue 开发规则

## 🔴 红线
1. **改完代码必须推到 GitHub** — 每次功能完成或 bug 修复后立刻 `git commit && git push`
2. **改完代码必须追加 VERIFY 条目** — 方便验收确认改了什么
3. **禁止大范围重写** — 优先小步修改, 降低引入新 bug 风险
4. **修改 Python 代码后验证语法** — `python -m py_compile *.py`

## 工作流程
1. 明确任务 → 写入 PROGRESS.md NOW
2. 查阅 lessons-learned.md 避免重犯
3. 实现 → 改小步, 每次改完编译验证
4. 验证 → 追加 VERIFY.md 验收条目
5. 提交 → `git add . && git commit -m "描述" && git push`
6. 完成 → 移到 PROGRESS.md 归档
