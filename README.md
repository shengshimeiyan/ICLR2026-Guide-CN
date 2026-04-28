# 📚 ICLR 2026 · VLM / MLLM 论文中文导读

> 用 GPT-5 替你读完了 ICLR 2026 全部 **460** 篇多模态论文 🤯
> 中文六维度导读 · 18 个子领域 · 一个静态网页带你扫完前沿

🔗 **在线浏览**：<https://JenniferZhao0531.github.io/ICLR-VLM-MLLM-papers/>

![preview](preview.png)

---

## ✨ 这是什么

从 ICLR 2026 共 **5,352** 篇接收论文中筛选出 **460** 篇 VLM / MLLM 相关论文，按 18 个子领域分类，并由 **GPT-5** 基于 abstract 自动生成六个维度的中文导读：

| 维度 | 说明 |
| --- | --- |
| 🎯 研究动机 | 论文出发点 |
| ❓ 解决问题 | 具体要解决什么 |
| 🔍 现象分析 | 观察 / 经验性发现 |
| 🛠️ 主要方法 | 技术方案概览 |
| 📊 数据与实验 | 用了什么数据、怎么评 |
| ⭐ 主要贡献 | 一句话定位 |

---

## 📁 18 个子领域

评测基准与评估 (107) · 视频理解 VLM (29) · 3D 与空间理解 (28) · 具身智能与 Agent (83) · 医学多模态 (5) · 安全 / 对齐 / 鲁棒性 (24) · 推理与强化学习 (51) · 训练 / 微调 / 对齐方法 (15) · 效率与推理加速 (23) · 多模态生成 (11) · 视觉定位与分割 (10) · 音频-视觉多模态 (1) · OCR / 文档 / 图表理解 (1) · 可解释性与表征分析 (5) · 数据与预训练 (4) · 检索与 RAG (5) · 架构创新 (9) · 其他 (49)

---

## 🚀 用法

### 直接看
打开 [在线网页](https://JenniferZhao0531.github.io/ICLR-VLM-MLLM-papers/)，左侧导航跳转，顶部搜索框支持标题/关键词检索，点论文标题直达 OpenReview 原文。

### 本地浏览
```bash
git clone https://github.com/JenniferZhao0531/ICLR-VLM-MLLM-papers.git
cd ICLR-VLM-MLLM-papers
open index.html      # macOS
# 或直接双击 index.html
```

### 自己重跑中文分析（可换模型）
```bash
pip install openai tqdm

export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.openai.com/v1"   # 或你的代理地址
export OPENAI_MODEL="gpt-5-2025-08-07"               # 或 gpt-4o / claude / 其它

python translate_papers.py     # 生成 ICLR2026_VLM_MLLM_papers_CN.json
python build_html_cn.py        # 渲染成 index.html
```

支持断点续跑（中断后重跑会跳过已完成的论文）。

---

## 📂 文件说明

| 文件 | 说明 |
| --- | --- |
| `index.html` | 静态网页（主入口，零依赖） |
| `ICLR2026_VLM_MLLM_papers.json` | 460 篇论文原始数据（标题、摘要、关键词、URL …） |
| `ICLR2026_VLM_MLLM_papers_CN.json` | 加上 GPT-5 六维度中文分析的版本 |
| `translate_papers.py` | 调用 LLM 生成中文分析的脚本 |
| `build_html_cn.py` | 把 JSON 渲染成 HTML 的脚本 |

---

## ⚠️ 免责声明

- 中文分析由大模型自动生成，**仅供快速浏览参考**，详细内容请以 OpenReview 原文为准。
- 论文筛选基于关键词匹配，可能存在漏判 / 误判。
- 数据快照时间见 `ICLR2026_VLM_MLLM_papers.json` 的 `meta` 字段。

---

## 🌟 喜欢就点个 Star 吧

如果对你有帮助，欢迎 **Star** ⭐ 支持一下，也欢迎 PR 补充遗漏的论文 / 修正分类。

## 📜 License

MIT
