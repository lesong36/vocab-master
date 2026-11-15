# 版本管理

唯一版本来源是仓库根目录 `release.json`。版本格式：`YYYY.MM.DD.N`，同一天每次正式发布递增 N。版本标识已加载页面的构建，不使用实时远端值替换当前版本，避免旧页面冒充新版。

发布步骤：

1. 更新 `release.json` 的版本、日期和面向用户的更新说明，将上一版加入 history。
2. 运行 `python3 scripts/prepare_release.py`，同步生成 `release.js`，更新页面资源版本与入口跳转。
3. 运行 `python3 scripts/prepare_release.py --check` 及相关回归；CI 会检查版本文件是否一致。
4. 提交到 main，建立同名 Git 标签 `vYYYY.MM.DD.N` 并推送；确认 Pages 发布与回归成功。
5. 在实际页面核对可见版本。检查更新读取最新 release.json；发现较新版本时提供刷新入口，当前版本标识保持不变。

UI 在标题旁常驻显示版本号，点击可见构建日期、当前更新说明、历史更新和 Git 发布标签入口。网络失败只提示无法检查更新，不影响学习和保存。
