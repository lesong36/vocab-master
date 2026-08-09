# VocabMaster 单词达人

小学英语背单词 Web 应用：单元选择、拼写/认词练习、错题本、课文例句、打印卡片。

## 在线使用（GitHub Pages）

打开仓库 Pages 地址即可。线上为纯静态托管：

- 学习进度保存在浏览器 `localStorage`
- AI 助记需本地服务（见下方）

## 本地运行（完整功能）

1. 复制配置：`cp ai_config.example.json ai_config.json`，填入 API Key  
2. 双击 `启动单词.command`，或：

```bash
python3 vocab_server.py 8080
```

3. 浏览器打开 <http://127.0.0.1:8080/vocabulary_app.html>

本地服务可把进度写入 `vocab_data.json`，并代理 AI 助记接口。

## 主要文件

| 文件 | 说明 |
|------|------|
| `vocabulary_app.html` | 主应用 |
| `词库.md` | 词库 |
| `四上英语课文.md` | 课文原文（中英） |
| `vocab_server.py` | 本地持久化 + AI 代理 |
| `ai_config.example.json` | AI 配置模板（勿提交真实 Key） |

## 从英语阅读器导入生词

在英语阅读器的「我的生词本」点击「传到 VocabMaster」，然后在本应用创建或选择用户并点击「导入阅读生词本」。这些词位于独立的「阅读生词本」，只进行“见英选义”，不会进入错题本或要求拼写。

跨设备使用时，先在阅读器登录同一 Supabase 账号；本应用会读取该账号同步的生词。学习进度仍保存在本应用的浏览器或本地服务中。
