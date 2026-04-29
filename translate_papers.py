# -*- coding: utf-8 -*-
"""
ICLR 2026 VLM/MLLM 论文批量中文化分析脚本
通过 OpenAI 兼容 API 对每篇论文 abstract 进行高质量六维度中文分析

使用步骤：
1. pip install openai tqdm
2. 在下方填入你自己的 API_KEY / BASE_URL / MODEL
   - 官方 OpenAI:  base_url="https://api.openai.com/v1"
   - 第三方代理:    填你自己的 base_url
3. python translate_papers.py
"""

import json
import os
from pathlib import Path

# ---- 自动加载同目录下的 .env 文件（不依赖 python-dotenv） ----
# 注意：.env 中的值会**覆盖** shell 里 export 的同名变量。
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
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============ 配置 ============
INPUT_JSON = "ICLR2026_VLM_MLLM_papers.json"
OUTPUT_JSON = "ICLR2026_VLM_MLLM_papers_CN.json"

# 推荐通过环境变量传入，避免泄露
API_KEY = os.environ.get("OPENAI_API_KEY", "YOUR_API_KEY_HERE")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-2025-08-07")

MAX_WORKERS = 5                # 并发数（注意 API rate limit）
RESUME = True                  # 中断后继续

# ============ Prompt ============
SYSTEM_PROMPT = """你是一位精通中英文的人工智能研究员，擅长用简练流畅的中文总结英文学术论文。
请严格输出 JSON 格式，不添加任何解释性文字。"""

USER_PROMPT_TEMPLATE = """请阅读下面这篇 ICLR 2026 的论文摘要，并用中文按六个维度进行精炼分析。

【论文标题】
{title}

【关键词】
{keywords}

【TL;DR】
{tldr}

【Abstract】
{abstract}

请用中文输出严格的 JSON，结构如下（每个字段 1-3 句话，专业精炼）：
{{
  "研究动机": "...",
  "解决问题": "...",
  "现象分析": "...",
  "主要方法": "...",
  "数据集与实验": "...",
  "主要贡献": "..."
}}"""

# ============ 主函数 ============
def analyze_paper(client, paper):
    prompt = USER_PROMPT_TEMPLATE.format(
        title=paper["title"],
        keywords="、".join(paper.get("keywords", [])),
        tldr=paper.get("tldr", "") or "(无)",
        abstract=paper.get("abstract", "")
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        text = resp.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json\n").rstrip()
        return paper["id"], json.loads(text), None
    except Exception as e:
        return paper["id"], None, str(e)

def main():
    if API_KEY == "YOUR_API_KEY_HERE":
        raise SystemExit("❌ 请先在同目录 .env 写 OPENAI_API_KEY，或 export OPENAI_API_KEY")
    print(f"使用 LLM: {MODEL} @ {BASE_URL}  (key: {API_KEY[:8]}...)")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    data = json.loads(Path(INPUT_JSON).read_text(encoding="utf-8"))
    papers = data["papers"]

    done = {}
    if RESUME and Path(OUTPUT_JSON).exists():
        existing = json.loads(Path(OUTPUT_JSON).read_text(encoding="utf-8"))
        done = {p["id"]: p for p in existing.get("papers", [])
                if p.get("中文分析") is not None}
        print(f"已恢复 {len(done)} 篇已完成的论文")

    todo = [p for p in papers if p["id"] not in done]
    print(f"待处理: {len(todo)} / 总计: {len(papers)}")

    results = list(done.values())
    pbar = tqdm(total=len(todo), desc="翻译中")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(analyze_paper, client, p): p for p in todo}
        for fut in as_completed(futures):
            pid, analysis, err = fut.result()
            paper = futures[fut]
            if analysis:
                results.append({**paper, "中文分析": analysis})
            else:
                print(f"\n[失败] {pid}: {err}")
                results.append({**paper, "中文分析": None, "error": err})
            pbar.update(1)
            if len(results) % 20 == 0:
                Path(OUTPUT_JSON).write_text(
                    json.dumps({**data, "papers": results}, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
    pbar.close()

    Path(OUTPUT_JSON).write_text(
        json.dumps({**data, "papers": results}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n✅ 完成！结果保存至 {OUTPUT_JSON}")

if __name__ == "__main__":
    main()
