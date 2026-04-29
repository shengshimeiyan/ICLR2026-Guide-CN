# -*- coding: utf-8 -*-
"""
ICLR 2026 OpenReview 论文爬取 + 智能子领域分类脚本
==================================================

功能流水线：
  1. 从 OpenReview 拉取 ICLR 2026 全部接收论文（约 5,352 篇）
  2. 用顶部的关键词 INCLUDE_KEYWORDS 筛出你感兴趣的方向（默认 = VLM/MLLM）
  3. 调用 LLM，把命中的论文打上你自定义的子领域标签（SUBCATEGORIES 完全由你决定，多少个、叫啥都行）
  4. 输出和 ICLR2026_VLM_MLLM_papers.json 完全一致格式的 JSON
     —— 之后可以直接用同目录下的 translate_papers.py + build_html_cn.py 走完中文化和网页生成

使用方法（订阅者用自己的 API key）：
  pip install openreview-py openai tqdm

  export OPENAI_API_KEY="sk-..."
  export OPENAI_BASE_URL="https://api.openai.com/v1"     # 可选，第三方代理填自己的
  export OPENAI_MODEL="gpt-5-2025-08-07"                  # 可选，gpt-4o / claude / qwen / ... 都行

  # 改下面几个常量定义你自己的方向 + 子领域，然后：
  python crawl_papers.py

中断后重跑会自动续跑（已分类的论文不会再调一次 LLM）。
"""

import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


# ---- 自动加载同目录下的 .env 文件（不依赖 python-dotenv） ----
# .env 文件示例（已在 .gitignore，不会上 GitHub）：
#   OPENAI_API_KEY=sk-...
#   OPENAI_BASE_URL=https://api.openai.com/v1   # 或任意 OpenAI 兼容代理
#   OPENAI_MODEL=gpt-4o                          # 或 deepseek-ai/DeepSeek-V3.2 等
# 注意：.env 中的值会**覆盖** shell 里 export 的同名变量（避免旧 export 干扰）。
def _load_dotenv():
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ[k.strip()] = v.strip().strip("'\"")

_load_dotenv()

from openai import OpenAI
from tqdm import tqdm


# ============ 1. 基本配置 ============
VENUE_ID = "ICLR.cc/2026/Conference"
OUTPUT_JSON = "ICLR2026_VLM_MLLM_papers.json"        # 改成你想要的输出文件名
DESCRIPTION = "ICLR 2026 接收的 VLM/MLLM 相关论文"   # 改成你的方向描述（写进 meta）

# OpenReview API（用官方 openreview-py 客户端，自动处理限流/分页/重试）
OPENREVIEW_API = "https://api2.openreview.net"

# LLM（订阅者用自己的 API key，从环境变量读）
API_KEY = os.environ.get("OPENAI_API_KEY", "YOUR_API_KEY_HERE")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-2025-08-07")
MAX_WORKERS = 5
RESUME = True
# 把已落到"其他"的论文重新分一次（不重新拉 OpenReview）。
# 第一次跑完发现"其他"特别多时，把这个开成 True 再跑一次即可。
RECATEGORIZE_OTHERS =  False


# ============ 2. 关键词筛选 ============
# 大小写不敏感、子串匹配；论文 title / abstract / tldr / keywords 任意一处出现就算命中。
# 改成你自己感兴趣方向的关键词即可：
#   想筛 "扩散视频生成" → ["diffusion", "video generation", "T2V", ...]
#   想筛 "强化学习"      → ["reinforcement learning", "RL ", "RLHF", "GRPO", ...]
#   想筛 "图神经网络"    → ["graph neural", "GNN", "graph transformer", ...]
INCLUDE_KEYWORDS = [
    "vision-language", "vision language",
    "multimodal", "multi-modal", "multi-modality",
    "VLM", "MLLM", "LMM",
    "visual instruction", "instruction tuning",
    "visual grounding", "visual reasoning", "visual question",
    "image-text", "vision-text", "language-image", "visual language",
    "cross-modal", "VQA",
    "image understanding", "visual understanding", "image captioning",
    "CLIP", "LLaVA",
]


# ============ 3. 子领域分类（你想要哪些子领域、给 LLM 看什么提示，全部由你决定）============
# 不限定个数，5 个 / 30 个都行；hint 越具体，分类越准。
# 默认沿用本项目的 18 个子领域。每个子领域是 {"name": 中文名, "hint": 给 LLM 的提示}。
SUBCATEGORIES = [
    {"name": "评测基准与评估",        "hint": "benchmarks, evaluation suites, metrics, leaderboards, diagnostic tests"},
    {"name": "视频理解 VLM",          "hint": "video, temporal, action recognition, long-form video, streaming video"},
    {"name": "3D 与空间理解",         "hint": "3D, point cloud, depth, spatial reasoning, scene understanding, indoor/outdoor 3D"},
    {"name": "具身智能与 Agent",      "hint": "embodied, robot, manipulation, vision-language-action (VLA), GUI agent, web agent, mobile agent"},
    {"name": "医学多模态",            "hint": "medical, clinical, biomedical, radiology, pathology, diagnosis"},
    {"name": "安全 / 对齐 / 鲁棒性",  "hint": "safety, alignment, jailbreak, adversarial, hallucination, red-teaming, robustness"},
    {"name": "推理与强化学习",        "hint": "reasoning, chain-of-thought, RL, RLHF, GRPO, mathematical / scientific reasoning"},
    {"name": "训练 / 微调 / 对齐方法", "hint": "training recipe, fine-tuning, instruction tuning, SFT, DPO, preference optimization"},
    {"name": "效率与推理加速",        "hint": "efficiency, acceleration, KV-cache, token pruning, quantization, distillation, speculative decoding"},
    {"name": "多模态生成",            "hint": "image / video generation, T2I / T2V / I2V, unified understanding-generation models"},
    {"name": "视觉定位与分割",        "hint": "grounding, segmentation, detection, referring expression"},
    {"name": "音频-视觉多模态",       "hint": "audio-visual, speech, sound understanding, audio captioning"},
    {"name": "OCR / 文档 / 图表理解", "hint": "OCR, document understanding, chart / table understanding, GUI / screen, scientific figures"},
    {"name": "可解释性与表征分析",    "hint": "interpretability, mechanistic analysis, probing, representation learning analysis"},
    {"name": "数据与预训练",          "hint": "pretraining data, data curation, synthetic data, captioning data, data filtering"},
    {"name": "检索与 RAG",            "hint": "retrieval, RAG, multimodal retrieval, knowledge-augmented generation"},
    {"name": "架构创新",              "hint": "architecture, tokenizer, vision encoder, mixture-of-experts, novel backbone"},
    {"name": "其他",                  "hint": "fallback：以上都不太合适的归这里"},
]


# ============ 4. primary_area 中英文对照 ============
# ICLR 投稿表单的 primary_area 是固定选项，预先维护好对照表，避免重复调用 LLM。
PRIMARY_AREA_ZH = {
    "alignment, fairness, safety, privacy, and societal considerations": "对齐/安全/公平性/隐私",
    "applications to computer vision, audio, language, and other modalities": "应用：CV/音频/语言等",
    "applications to neuroscience & cognitive science": "应用：神经/认知科学",
    "applications to physical sciences (physics, chemistry, biology, etc.)": "应用：物理科学",
    "applications to robotics, autonomy, planning": "应用：机器人/自动化/规划",
    "datasets and benchmarks": "数据集与基准",
    "foundation or frontier models, including LLMs": "基础/前沿模型 (含LLM)",
    "generative models": "生成模型",
    "infrastructure, software libraries, hardware, systems, etc.": "基础设施/软硬件",
    "interpretability and explainable AI": "可解释 AI",
    "neurosymbolic & hybrid AI systems (physics-informed, logic & formal reasoning, etc.)": "神经符号/混合 AI",
    "neurosymbolic & hybrid AI systems": "神经符号/混合 AI",
    "optimization": "优化",
    "other topics in machine learning (i.e., none of the above)": "其他 ML 主题",
    "other topics in machine learning": "其他 ML 主题",
    "probabilistic methods (Bayesian methods, variational inference, sampling, UQ, etc.)": "概率方法",
    "probabilistic methods": "概率方法",
    "reinforcement learning": "强化学习",
    "transfer learning, meta learning, and lifelong learning": "迁移/元/终身学习",
    "unsupervised, self-supervised, semi-supervised, and supervised representation learning": "表征学习",
}


# ============ 5. 拉 OpenReview ============
def _v(field):
    """OpenReview v2 字段是 {'value': X} 包了一层；这个 helper 拆开。"""
    if isinstance(field, dict) and "value" in field:
        return field["value"]
    return field


def fetch_all_iclr_papers():
    """拉取 ICLR 2026 全部接收论文。

    用官方 openreview-py 客户端：它会自动处理速率限制 / 分页 / 重试，
    比直接 HTTP 调 OpenReview 稳得多（匿名 HTTP 经常被 429 限流）。

    OpenReview v2 中接收论文的 venueid = 'ICLR.cc/2026/Conference'
    （投稿期/被拒/撤稿的 venueid 不同，所以这一步天然过滤掉非接收）
    """
    try:
        import openreview
    except ImportError:
        raise SystemExit(
            "❌ 未安装 openreview-py。请先执行：\n"
            "    pip install openreview-py\n"
            "（OpenReview 官方维护的 Python 客户端，自动处理速率限制/分页/重试）"
        )

    print(f"[1/3] 从 OpenReview 拉取 {VENUE_ID} 接收论文...")
    client = openreview.api.OpenReviewClient(baseurl=OPENREVIEW_API)
    notes = client.get_all_notes(content={"venueid": VENUE_ID})
    print(f"  共拉到 {len(notes)} 篇接收论文。")
    # 转成 dict 形式（保留 v2 schema 的 {"value": ...} 包装），让 normalize_paper 直接用
    return [{"id": n.id, "content": n.content} for n in notes]


def normalize_paper(note):
    """OpenReview note → 我们的 paper 字典格式（category 待 LLM 填）。"""
    content = note.get("content", {}) or {}
    pid = note.get("id", "")
    keywords = _v(content.get("keywords", [])) or []
    if isinstance(keywords, str):
        keywords = [keywords]
    return {
        "id": pid,
        "url": f"https://openreview.net/forum?id={pid}",
        "title": (_v(content.get("title", "")) or "").strip(),
        "category": None,
        "primary_area": "",
        "primary_area_en": (_v(content.get("primary_area", "")) or "").strip(),
        "keywords": keywords,
        "tldr": (_v(content.get("TLDR", "")) or _v(content.get("tldr", "")) or "").strip(),
        "abstract": (_v(content.get("abstract", "")) or "").strip(),
    }


# ============ 6. 关键词筛选 ============
def matches_filter(paper):
    haystack = " ".join([
        paper.get("title", ""),
        paper.get("abstract", ""),
        paper.get("tldr", ""),
        " ".join(paper.get("keywords", []) or []),
    ]).lower()
    return any(kw.lower() in haystack for kw in INCLUDE_KEYWORDS)


# ============ 7. LLM 子领域分类 ============
SYSTEM_PROMPT_CAT = (
    "你是一位精通中英文的 AI 研究员。给定一篇论文和一组子领域，"
    "选出最匹配的一个。严格只输出 JSON：{\"category\": \"<中文名>\"}，"
    "不要写任何解释、Markdown、思考过程。"
)


def build_categorize_prompt(paper):
    cat_list = "\n".join(f"- {c['name']}：{c['hint']}" for c in SUBCATEGORIES)
    keywords = "、".join(paper.get("keywords", []) or [])
    fallback = SUBCATEGORIES[-1]["name"]
    return f"""请从下列子领域中为这篇论文选**最匹配的一个**，输出 JSON：

{cat_list}

规则：
1. 只能从上面列表里选，名字一字不差。
2. 不到万不得已不要选 "{fallback}"。如果论文明显属于其中某个具体类别，必须选具体类别。
3. 若论文同时涉及多个，选**研究焦点最集中**的那个（例：以提出 benchmark 为主 → 评测基准与评估；以提出方法+顺带 benchmark → 选方法所属的类）。

【论文标题】{paper['title']}
【关键词】{keywords}
【TL;DR】{paper.get('tldr') or '(无)'}
【Abstract】
{paper.get('abstract', '')}

只输出 JSON：{{"category": "<中文名>"}}"""


def _parse_category(text, valid_names):
    """从 LLM 返回里提取最匹配的 category 名。返回 (name | None, raw_text)。"""
    raw = (text or "").strip()
    # 1. 直接 JSON 解析
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "category" in obj:
            cand = str(obj["category"]).strip()
            if cand in valid_names:
                return cand, raw
    except Exception:
        pass
    # 2. 从文本里抠出 {"category": "..."}
    m = re.search(r'"category"\s*:\s*"([^"]+)"', raw)
    if m and m.group(1) in valid_names:
        return m.group(1), raw
    # 3. 去除常见包裹符号后精确匹配
    cleaned = re.sub(r"[\"'`*【】「」\s]", "", raw)
    for name in valid_names:
        if cleaned == re.sub(r"\s", "", name):
            return name, raw
    # 4. substring 兜底，但跳过 "其他" 类先扫具体类，全失败才考虑 "其他"
    real_names = [n for n in valid_names if n != SUBCATEGORIES[-1]["name"]]
    hits = [n for n in real_names if n in raw]
    if len(hits) == 1:
        return hits[0], raw
    if len(hits) > 1:
        # 多个候选时，挑最长的名字（信息量最大），降低误命中
        return max(hits, key=len), raw
    if SUBCATEGORIES[-1]["name"] in raw:
        return SUBCATEGORIES[-1]["name"], raw
    return None, raw


def _extract_text(resp):
    """从 LLM 响应中提取 content。OpenAI 官方返回结构化对象，
    但少数第三方代理（DeepSeek/百炼/各种 wrapper）会直接返回 str 或 dict，
    这里统一防御处理。"""
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        try:
            return resp["choices"][0]["message"]["content"] or ""
        except Exception:
            return json.dumps(resp, ensure_ascii=False)[:500]
    try:
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return str(resp)[:500]


def categorize_paper(client, paper):
    valid_names = [c["name"] for c in SUBCATEGORIES]
    kwargs = dict(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_CAT},
            {"role": "user", "content": build_categorize_prompt(paper)},
        ],
        max_tokens=200,        # 限输出长度，防止 reasoning 模型疯狂思考
        temperature=0,         # 分类任务希望稳定
    )
    # 先尝试 JSON 模式；不支持就降级
    try:
        resp = client.chat.completions.create(
            **kwargs, response_format={"type": "json_object"}
        )
    except Exception:
        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception as e:
            return paper["id"], SUBCATEGORIES[-1]["name"], f"api error: {e}"

    text = _extract_text(resp)
    name, raw = _parse_category(text, valid_names)
    if name is None:
        return paper["id"], SUBCATEGORIES[-1]["name"], f"unparsed: {raw[:120]}"
    return paper["id"], name, None


# ============ 8. 主流程 ============
def save(papers, total_accepted):
    out = {
        "meta": {
            "source": f"OpenReview {VENUE_ID}",
            "total": len(papers),
            "total_accepted": total_accepted,
            "description": DESCRIPTION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "filter_keywords": INCLUDE_KEYWORDS,
            "subcategories": [c["name"] for c in SUBCATEGORIES],
            "fields": {
                "id": "论文唯一标识",
                "url": "OpenReview 论文链接",
                "title": "英文标题",
                "category": "中文子领域分类",
                "primary_area": "Primary Area (中文)",
                "primary_area_en": "Primary Area (英文原文)",
                "keywords": "关键词列表",
                "tldr": "TL;DR 一句话摘要",
                "abstract": "完整 Abstract（英文原文）",
            },
        },
        "papers": papers,
    }
    Path(OUTPUT_JSON).write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    if API_KEY == "YOUR_API_KEY_HERE":
        raise SystemExit("❌ 请先在同目录创建 .env 写入 OPENAI_API_KEY，或 export OPENAI_API_KEY")
    print(f"使用 LLM: {MODEL} @ {BASE_URL}  (key: {API_KEY[:8]}...)")


    # ---- 1. 拉所有接收论文 ----
    notes = fetch_all_iclr_papers()
    all_papers = [normalize_paper(n) for n in notes]
    for p in all_papers:
        p["primary_area"] = PRIMARY_AREA_ZH.get(p["primary_area_en"], p["primary_area_en"])

    # ---- 2. 关键词筛选 ----
    print(f"\n[2/3] 用 {len(INCLUDE_KEYWORDS)} 个关键词筛选感兴趣的论文...")
    matched = [p for p in all_papers if matches_filter(p)]
    print(f"  命中 {len(matched)} 篇 / 总 {len(all_papers)} 篇接收论文。")

    if not matched:
        print("⚠️  没有命中任何论文，请检查 INCLUDE_KEYWORDS 是否合理。")
        return

    # ---- 3. 续跑 ----
    done = {}
    if RESUME and Path(OUTPUT_JSON).exists():
        try:
            existing = json.loads(Path(OUTPUT_JSON).read_text(encoding="utf-8"))
            done = {p["id"]: p for p in existing.get("papers", []) if p.get("category")}
            if done:
                print(f"\n[3/3] 已恢复 {len(done)} 篇已分类的论文。")
        except Exception:
            pass
    if not done:
        print("\n[3/3] 调用 LLM 给每篇命中的论文分配子领域...")

    # 关键改动：RECATEGORIZE_OTHERS=True 时，把已分到"其他"的论文从 done 里踢出来重跑
    if RECATEGORIZE_OTHERS:
        other_name = SUBCATEGORIES[-1]["name"]
        retry_ids = [pid for pid, p in done.items() if p.get("category") == other_name]
        for pid in retry_ids:
            done.pop(pid, None)
        if retry_ids:
            print(f"  RECATEGORIZE_OTHERS=True：将重新分类 {len(retry_ids)} 篇『{other_name}』论文。")

    todo = [p for p in matched if p["id"] not in done]
    results = list(done.values())

    if todo:
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        pbar = tqdm(total=len(todo), desc="分类中")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(categorize_paper, client, p): p for p in todo}
            for fut in as_completed(futures):
                pid, cat, err = fut.result()
                paper = futures[fut]
                rec = {**paper, "category": cat}
                if err:
                    rec["category_error"] = err  # 写进 JSON 便于排查
                    tqdm.write(f"[警告] {pid}: {err[:120]}")
                results.append(rec)
                pbar.update(1)
                if len(results) % 30 == 0:
                    save(results, len(all_papers))
        pbar.close()
    else:
        print("  无新论文需要分类。")

    # ---- 4. 按子领域顺序排序后落盘 ----
    cat_order = {c["name"]: i for i, c in enumerate(SUBCATEGORIES)}
    results.sort(key=lambda p: (cat_order.get(p.get("category"), 999), p["title"]))

    save(results, len(all_papers))
    print(f"\n✅ 完成！共 {len(results)} 篇 → {OUTPUT_JSON}")

    # 简单统计
    cnt = Counter(p["category"] for p in results)
    print("\n子领域分布：")
    for c in SUBCATEGORIES:
        if cnt[c["name"]]:
            print(f"  {c['name']}: {cnt[c['name']]}")
    print(f"\n下一步可执行：python translate_papers.py  →  生成中文六维度分析")


if __name__ == "__main__":
    main()
