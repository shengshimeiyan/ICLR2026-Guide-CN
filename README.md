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

在仓库根目录创建 `.env`。所有 LLM 脚本都使用 OpenAI-compatible 参数，因此可切换到 Zhipu、OpenAI、Kimi 等兼容接口：

```bash
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
```

推荐流水线：

```bash
# 1. 从 ACL Anthology 抓取论文和摘要，并生成初始一级分类
python crawl_all_papers.py

# 2. 优化一级大类和二级小类，可本地小样本或用 GitHub Actions 全量跑
python refine_primary_areas.py

# 3. 生成中文六维度分析
python translate_all_papers.py

# 4. 生成静态页面
python build_html_full.py
```

如果 ACL Anthology 的 ACL 2026 页面地址需要手动指定：

```bash
ACL_ANTHOLOGY_EVENT_URL=https://aclanthology.org/events/acl-2026/ python crawl_all_papers.py
```

`build_html_full.py` 支持显式输入输出路径，避免把中间结果复制成固定文件名：

```bash
INPUT_JSON=ACL2026_all_papers.json \
CN_OVERLAY_JSON=ACL2026_all_papers_CN.json \
OUTPUT_HTML=index.html \
python build_html_full.py
```

Windows PowerShell 示例：

```powershell
$env:INPUT_JSON="ACL2026_all_papers.json"
$env:CN_OVERLAY_JSON="ACL2026_all_papers_CN.json"
$env:OUTPUT_HTML="index.html"
python build_html_full.py
```

---

## GitHub Actions 工作流

项目包含三个手动触发的 workflow：

| Workflow | 用途 | 典型场景 |
| --- | --- | --- |
| `refine-primary-areas.yml` | 同时重分配 `primary_area` 和 `category` | 优化大类分布。先用 `limit_papers=40`、`stratified_sample=1` smoke test，再用 `limit_papers=0` 全量跑 |
| `refine-categories.yml` | 在已有 `primary_area` 下重跑二级 `category` | 大类已确定，只想优化细分类 |
| `merge-refined-categories.yml` | 只合并某次二级分类 run 的 artifacts | 原 run 的 merge job 失败，但 shard artifacts 已完整生成 |

Actions 默认使用：

- `OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4`
- `OPENAI_MODEL=glm-4.7-flash`
- `OPENAI_API_KEY` 从 GitHub Secrets 读取
- `NOTIFYX_API_KEY` 可选，用于单 shard 进度推送

建议参数：

```text
shard_total=16
max_workers=1
batch_size=5
limit_papers=40  # smoke test
stratified_sample=1
```

全量运行通过后，下载 merged artifact，检查报告中的 `missing=0`、`invalid=0`、`error_warnings=0`、`duplicate_ids=0`，再替换主数据并重建页面。

---

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `index.html` | 静态网页入口 |
| `ACL2026_all_papers.json` | 原始规范化数据和研究方向分类 |
| `ACL2026_all_papers_CN.json` | 在原始数据上叠加中文六维度分析 |
| `crawl_all_papers.py` | ACL Anthology 爬取 + 研究方向分类 |
| `refine_primary_areas.py` | 同时优化一级大类和二级分类 |
| `refine_categories.py` | 在固定一级大类下优化二级分类 |
| `merge_refined_primary_area_shards.py` | 合并一级大类优化的 Actions 分片结果 |
| `merge_refined_category_shards.py` | 合并二级分类优化的 Actions 分片结果 |
| `translate_all_papers.py` | 调 LLM 生成中文六维度分析 |
| `build_html_full.py` | 把 JSON 渲染成 HTML |

---

## 页面功能

`index.html` 是零依赖静态页面，支持：

- 左侧两级目录：`primary_area -> category`
- 大类分布条形图
- 搜索标题、作者、关键词、摘要相关字段
- 按 ACL Anthology track 筛选
- 展示一级分类优化说明，提醒“LLM 只是方法或工具时按任务/应用归类”
- 展示每篇论文的六维度中文分析和完整 abstract

---

## 免责声明

中文分析由大语言模型基于英文 abstract 自动生成，仅供快速浏览参考，详细内容请以 ACL Anthology 原文和 PDF 为准。研究方向分类由 LLM 自动打标，可能存在错分。

## License

MIT
