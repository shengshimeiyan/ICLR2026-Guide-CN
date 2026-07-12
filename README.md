# ACL 2026 全部论文 · 中文导读

> 面向 ACL 2026 全部公开论文的中文导读项目。数据源优先使用 ACL Anthology，并按 NLP / Computational Linguistics 研究方向组织。

---

## 这是什么

本项目把 ACL 2026 公开论文整理成一个零依赖的静态网页。每篇论文保留标题、作者、来源 track、ACL Anthology 链接、PDF 链接和摘要，并可通过大语言模型自动生成六个维度的中文分析：

| 维度 | 说明 |
| --- | --- |
| 研究动机 | 论文出发点 |
| 解决问题 | 具体要解决什么 |
| 现象分析 | 观察 / 经验性发现 |
| 主要方法 | 技术方案概览 |
| 数据集与实验 | 用了什么数据、怎么评 |
| 主要贡献 | 一句话定位 |

页面按研究方向组织，例如大语言模型与基础模型、机器翻译与多语言、信息抽取与知识、问答检索与 RAG、对话系统、多模态 NLP、评测基准、安全伦理等。Main、Findings、Workshop、Demo 等来源信息作为 track 标签和筛选项保留。

---

## 数据源策略

本项目采用 **ACL Anthology 优先**：

- ACL Anthology 是最终公开论文、PDF 和元数据的权威入口。
- OpenReview 只作为可选补充来源，不作为默认主数据源。
- 如果 ACL 2026 尚未在 ACL Anthology 发布，爬虫会明确报错，并提示稍后重试或通过 `ACL_ANTHOLOGY_EVENT_URL` 指向已发布页面。

---

## 本地运行

安装依赖：

```bash
pip install openai tqdm requests beautifulsoup4
```

在仓库根目录创建 `.env`：

```bash
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
```

运行完整流水线：

```bash
python crawl_all_papers.py
python translate_all_papers.py
python build_html_full.py
```

如果 ACL Anthology 的 ACL 2026 页面地址需要手动指定：

```bash
ACL_ANTHOLOGY_EVENT_URL=https://aclanthology.org/events/acl-2026/ python crawl_all_papers.py
```

---

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `index.html` | 静态网页入口 |
| `ACL2026_all_papers.json` | 原始规范化数据和研究方向分类 |
| `ACL2026_all_papers_CN.json` | 在原始数据上叠加中文六维度分析 |
| `crawl_all_papers.py` | ACL Anthology 爬取 + 研究方向分类 |
| `translate_all_papers.py` | 调 LLM 生成中文六维度分析 |
| `build_html_full.py` | 把 JSON 渲染成 HTML |

---

## 免责声明

中文分析由大语言模型基于英文 abstract 自动生成，仅供快速浏览参考，详细内容请以 ACL Anthology 原文和 PDF 为准。研究方向分类由 LLM 自动打标，可能存在错分。

## License

MIT
