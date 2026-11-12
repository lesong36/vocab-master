# 答题存储满额：根因与修复证据

## 已确认的根因

答题先向 `localStorage` 写入不可变事件，成功后才更新答题结果。截图中的 `vocabmaster_learning_outbox_v3:…:event:…` 正是该事件键；浏览器拒绝了这次写入，答题流程因此返回失败。

先前版本 `9683e74` 的补救仍向同一个 `localStorage` 写入，只能通过合并完全相同的 `wordDefinition` 腾出空间。实际事件中的 `vocabMasterProgressUpdatedAt`、阅读复习状态会变化，因此即使同一单词也未必有完全相同的资料。新增的 1,000 条变化资料测试，压缩后大小为原来的 **99.4%**。上次使用完全相同资料的测试不能证明这种真实条件已经解决。

**尚未测得：** 用户当前浏览器各存储键的实际占用分布、是否有其他同源应用占用空间。没有删除或检查用户设备上的私有学习记录。

## 新修复

保留原有事件格式和压缩处理；当 `localStorage` 配额耗尽时，将答题事件与学习快照写入独立的 IndexedDB。必须等数据库事务提交后才能显示答题成功、加分或继续。启动时恢复数据库记录；同步前读取其他页面已提交的事件；只有云端回执与返回历史同时确认的事件才可移除。删除待同步事件前先持久化包含最新待同步记录的完整快照。

## 可重复的测试

需本地静态服务运行于端口 8767：

```sh
python3 -m http.server 8767 --bind 127.0.0.1
python3 tests/test_learning_indexeddb_quota_ui.py --reading --real-quota --baseline
python3 tests/test_learning_indexeddb_quota_ui.py --reading --real-quota
python3 tests/test_learning_indexeddb_sync.py
```

前两项使用真实 Chromium，将 `localStorage` 实际填至浏览器限制；不是仅替换错误文案或模拟成功。旧版与新版使用同一合成账号、同一 `plastic` 四选一题和相同占用条件。测试数据与用户账号隔离。

- 旧版：复现配额错误，积分为 0，无法继续。
- 新版：答案保存成功，下一题可用并能进入完成页；刷新后通过应用自身的“导出记录”读取到唯一的答题事件、正确次数 1 和积分 10。
- 备用数据库也禁止写入：显示失败、积分保持 0、无法继续。
- 学习快照写入被故意中止，但独立答题事件已提交：刷新后从事件恢复记录和积分。
- 事务中止：写入被拒绝，不把内存中的事件误报为成功。
- 两个独立页面的答题与请求期间新增的答题均保留；部分云端确认只移除确认 ID，其他账号记录保持不变。

线上整页验证命令（使用真实线上 HTML，学习资料为隔离合成资料；云端接口不可用）：

```sh
python3 tests/test_learning_indexeddb_quota_ui.py --reading --real-quota --online
```

## 证据文件

生成于 `outputs/recovery/indexeddb-quota/`：

- `baseline-reading-real-quota.json`：旧版真实配额测试的占用与结果。
- `fixed-reading-real-quota.json`：新版真实配额测试的占用与结果。
- `online-fixed-reading-real-quota.json`：线上版本整页验证结果。
- `database-evidence.json`：跨页面、事务中止与部分同步确认结果。
- `reading-restored-backup.json`：刷新后由应用导出的合成学习记录。
- `baseline-reading.png`：旧版失败截图。
- `real-quota-reading-saved.png`：新版真实配额下成功截图。

## 验证范围

这些证据能证明：新版在真实浏览器存储满额的相同触发条件下，保存、继续答题、刷新恢复与待同步事件处理有效。云端回执测试使用受控接口，没有冒用用户账号写入生产数据库。用户原浏览器当前会话是否加载新版、以及原有存储具体分布，需要该设备的实际运行信息，不能由隔离测试替代。
