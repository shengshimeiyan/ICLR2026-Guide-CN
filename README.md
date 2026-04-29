# 📚 ICLR 2026 全部接收论文 · 中文导读

> 大模型替你读完了 ICLR 2026 全部 **5,352** 篇接收论文 🤯
> 中文六维度导读 · 21 大类 / 126 细分两级目录 · 🎤 Oral 高亮标识

🔗 **在线浏览**：<https://JenniferZhao0531.github.io/ICLR2026-Guide-CN/>

![preview](preview.png)

---

## ✨ 这是什么

把 ICLR 2026 全部 **5,352** 篇接收论文整理成一个零依赖的静态网页。每篇论文自动生成六个维度的中文分析：

| 维度 | 说明 |
| --- | --- |
| 🎯 研究动机 | 论文出发点 |
| ❓ 解决问题 | 具体要解决什么 |
| 🔍 现象分析 | 观察 / 经验性发现 |
| 🛠️ 主要方法 | 技术方案概览 |
| 📊 数据与实验 | 用了什么数据、怎么评 |
| ⭐ 主要贡献 | 一句话定位 |

并按**两级目录**组织：

- **大类**（一级）：直接用 ICLR 官方让作者填的 `primary_area`，21 个一级研究方向（基础/前沿模型、生成模型、CV 应用、机器人、强化学习、对齐安全……）
- **细分**（二级）：调 LLM 在每个大类下进一步打 5–10 个细分小类，全站共 **126** 个细分（如 *视觉-语言模型 (VLM/MLLM)* / *扩散模型* / *离线 RL* / *机制可解释性* …）

🎤 全部 **224 篇 Oral** 论文在卡片上加金色徽章 + 边条高亮，顶部一键筛选只看 Oral。

---

## 📁 21 个大类（按论文数排序）

基础/前沿模型 (含LLM) (845) · 应用：CV/音频/语言等 (733) · 生成模型 (498) · 数据集与基准 (439) · 对齐/安全/公平性/隐私 (423) · 强化学习 (306) · 表征学习 (268) · 应用：物理科学 (220) · 可解释 AI (200) · 优化 (191) · 学习理论 (189) · 应用：机器人/自动化/规划 (178) · 其他 ML 主题 (165) · 概率方法 (118) · 迁移/元/终身学习 (118) · 图与几何拓扑学习 (113) · 应用：神经/认知科学 (112) · 时间序列与动力系统 (100) · 因果推理 (46) · 神经符号/混合 AI (46) · 基础设施/软硬件 (44)

> 每个大类下还有 4–10 个细分小类，详见网页左侧折叠导航。

---

## 🚀 用法

### 直接看
打开 [在线网页](https://JenniferZhao0531.github.io/ICLR2026-Guide-CN/)：

- **左侧两级导航**：点大类标题展开/收起细分小类，点细分跳转到对应内容
- **顶部 chip**：一键筛选 `📚 全部 / 🎤 Oral 224 篇`
- **顶部搜索框**：标题 / 关键词全文检索（搜索时左边大类计数会动态重算）
- **每篇论文卡片**：标题 → OpenReview 原文；🎤 Oral 徽章一眼可见；六维度中文分析；可展开查看完整 Abstract

### 本地浏览
```bash
git clone https://github.com/JenniferZhao0531/ICLR2026-Guide-CN.git
cd ICLR2026-Guide-CN
open index.html      # macOS（直接双击也行）
```

### 自己定制（从爬虫开始走完整套）

完整流水线四步，所有 LLM 调用走 OpenAI 兼容接口，**用你自己的 key**：

```bash
pip install openreview-py openai tqdm
```

在仓库根目录建一个 `.env` 文件（已在 `.gitignore`，不会上 GitHub）：

```
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
```

> `OPENAI_BASE_URL` 也可以填 DeepSeek / Qwen / Claude / 智谱 / 月之暗面 / OpenRouter 等任何 OpenAI 兼容代理。
> 性价比推荐：分类阶段用 `deepseek-ai/DeepSeek-V3.2`（任务简单、原生中文、约 GPT-4o 1/10 价格），翻译阶段用 `gpt-4o` 或 `claude-sonnet-4-6`（中文表达更精致）。

**Step 1 · 爬 + 二级分类**

```bash
python crawl_all_papers.py
```

从 OpenReview 拉全部 5,352 篇接收论文 → 大类直接复用 ICLR 官方 `primary_area` → LLM 给每篇打细分小类。

> 想自己定制大类下的细分小类（比如把"扩散模型"拆得更细），改 `crawl_all_papers.py` 顶部的 `SUBCATEGORIES_BY_PRIMARY` 字典即可，每个 primary_area 下放任意数量小类。

**Step 2 · 中文六维度分析**

```bash
python translate_all_papers.py
```

会自动复用旧版已经翻译过的论文（如果存在 `ICLR2026_VLM_MLLM_papers_CN.json`），只对新增论文调 LLM。

**Step 3 · 拉 Oral 标识**

```bash
python enrich_venues.py
```

从 OpenReview 再拉一次 venue 字段，识别 Oral / Poster / (Spotlight)，写回到 JSON。免费、~1 分钟。

**Step 4 · 渲染网页**

```bash
python build_html_full.py    # 输出 index.html
```

---

四步全部支持断点续跑：中断后重跑会自动跳过已完成的论文。

---

## 📂 文件说明

| 文件 | 说明 |
| --- | --- |
| `index.html` | 静态网页（主入口，零依赖） |
| `ICLR2026_all_papers.json` | 5,352 篇原始数据（标题、摘要、关键词、primary_area、tier、URL …） |
| `ICLR2026_all_papers_CN.json` | 在原始数据上叠加六维度中文分析 |
| `crawl_all_papers.py` | 爬取 + 二级分类（大类 = ICLR primary_area，小类 = LLM 标） |
| `translate_all_papers.py` | 调 LLM 生成中文六维度分析（自动复用旧翻译） |
| `enrich_venues.py` | 补丁脚本：拉 venue 字段，识别 Oral / Spotlight / Poster |
| `build_html_full.py` | 把 JSON 渲染成 HTML（含搜索 + 两级折叠目录 + Oral 筛选） |
| `preview.png`, `social-preview.html` | 仓库预览图 |

---

## ⚠️ 免责声明

- 中文分析由大语言模型基于英文 abstract 自动生成，**仅供快速浏览参考**，详细内容请以 OpenReview 原文为准。
- 二级小类由 LLM 自动打标，可能存在错分，欢迎 PR 修正。
- 数据快照时间见 `ICLR2026_all_papers.json` 的 `meta.generated_at` 字段。

---

## 🌟 喜欢就点个 Star 吧

如果对你有帮助，欢迎 **Star** ⭐ 支持一下，也欢迎 PR 补充遗漏的论文 / 修正分类 / 改进小类设计。

## 📜 License

MIT
