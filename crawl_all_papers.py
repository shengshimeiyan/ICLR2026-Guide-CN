# -*- coding: utf-8 -*-
"""
ACL 2026 全量论文爬取 + 研究方向分类
===================================

流水线：
  1. 优先从 ACL Anthology 拉取 ACL 2026 公开论文
  2. 统一成静态网页需要的 JSON schema
  3. 调 LLM 按 NLP/CL 研究方向分类
  4. 输出 ACL2026_all_papers.json

使用：
  pip install openai tqdm requests beautifulsoup4
  在 .env 里填好 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
  python crawl_all_papers.py

支持断点续跑：中断后重跑会跳过已分类的论文。
"""

import json
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin


def _load_dotenv():
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        key = k.strip()
        if key not in os.environ:
            os.environ[key] = v.strip().strip("'\"")


_load_dotenv()

from openai import OpenAI
from tqdm import tqdm


# ============ 1. 基本配置 ============
CONFERENCE_ID = "ACL2026"
OUTPUT_JSON = os.environ.get("OUTPUT_JSON", "ACL2026_all_papers.json")
DETAIL_CACHE_JSON = os.environ.get("DETAIL_CACHE_JSON", "ACL2026_paper_details_cache.json")
DESCRIPTION = "ACL 2026 全部论文（中文导读 · 按研究方向组织）"
SOURCE_NAME = "ACL Anthology"

ACL_ANTHOLOGY_BASE_URL = "https://aclanthology.org"
ACL_ANTHOLOGY_EVENT_URL = os.environ.get(
    "ACL_ANTHOLOGY_EVENT_URL",
    "https://aclanthology.org/events/acl-2026/",
)

API_KEY = os.environ.get("OPENAI_API_KEY", "YOUR_API_KEY_HERE")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "8"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "5"))
LIMIT_PAPERS = int(os.environ.get("LIMIT_PAPERS", "0") or "0")
API_MAX_RETRIES = int(os.environ.get("API_MAX_RETRIES", "5"))
API_RETRY_SLEEP = float(os.environ.get("API_RETRY_SLEEP", "8"))
DETAIL_MAX_WORKERS = int(os.environ.get("DETAIL_MAX_WORKERS", "8"))
RESUME = True


# ============ 2. ACL 研究方向 ============
RESEARCH_DIRECTIONS = [
    {"name": "大语言模型与基础模型", "hint": "large language models, foundation models, pretraining, instruction tuning, alignment"},
    {"name": "机器翻译与多语言", "hint": "machine translation, multilingual NLP, cross-lingual transfer, low-resource languages"},
    {"name": "信息抽取与知识", "hint": "information extraction, relation extraction, entity linking, knowledge graphs"},
    {"name": "问答、检索与 RAG", "hint": "question answering, retrieval, search, RAG, open-domain QA"},
    {"name": "对话系统与交互", "hint": "dialogue systems, conversational agents, human-computer interaction"},
    {"name": "语义、句法与语言学", "hint": "semantics, syntax, morphology, linguistic analysis"},
    {"name": "文本生成与摘要", "hint": "text generation, summarization, controllable generation"},
    {"name": "评测、基准与数据集", "hint": "evaluation, benchmarks, datasets, metrics"},
    {"name": "安全、伦理、公平与隐私", "hint": "safety, ethics, fairness, bias, privacy, misuse"},
    {"name": "多模态与具身语言", "hint": "multimodal NLP, vision-language, speech-language, embodied language"},
    {"name": "语音与音频语言处理", "hint": "speech recognition, speech translation, spoken language, audio-language"},
    {"name": "计算社会科学与人文", "hint": "computational social science, digital humanities, political text analysis"},
    {"name": "NLP 应用与系统", "hint": "applications, deployed systems, clinical NLP, education, legal NLP"},
    {"name": "可解释性与模型分析", "hint": "interpretability, probing, model analysis, mechanistic analysis"},
    {"name": "其他", "hint": "other computational linguistics and NLP topics"},
]


# ============ 3. ACL Anthology 爬取 ============
def _require_crawler_deps():
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise SystemExit("❌ 未安装爬取依赖：pip install requests beautifulsoup4") from e
    return requests, BeautifulSoup


def _text(node):
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def _clean_title(title):
    title = re.sub(r"\b([A-Z])\s+([a-z])", r"\1\2", title or "")
    title = re.sub(r"\s+([:;,.!?])", r"\1", title)
    return " ".join(title.split())


def _extract_track_from_heading(heading):
    label = _text(heading)
    if not label:
        return "Unknown Track"
    label = re.sub(r"\s+", " ", label)
    label = re.sub(r"^(pdf|bib)\s*\(full\)\s*", "", label, flags=re.I)
    label = re.sub(r"^(pdf|bib)\s*\(full\)\s*", "", label, flags=re.I)
    label = re.sub(r"\s*\(\d+\s+papers?\)\s*$", "", label, flags=re.I)
    return label.strip() or "Unknown Track"


def _parse_paper_id_from_url(url):
    clean = url.rstrip("/")
    if not clean:
        return ""
    return clean.rsplit("/", 1)[-1]


def _parse_authors(paper_node):
    authors = []
    for author in paper_node.select(".author, .authors a, a[href*='/people/']"):
        name = _text(author)
        if name and name not in authors:
            authors.append(name)
    return authors


def _parse_abstract(paper_node):
    abstract = paper_node.select_one(".acl-abstract, .abstract")
    return _text(abstract)


def _parse_title_link(paper_node):
    selectors = [
        "span.d-block strong a[href]",
        "strong a[href]",
    ]
    for selector in selectors:
        link = paper_node.select_one(selector)
        if link and _text(link):
            href = link.get("href", "")
            paper_id = _parse_paper_id_from_url(href)
            if not _is_real_paper_id(paper_id):
                continue
            return _clean_title(_text(link)), urljoin(ACL_ANTHOLOGY_BASE_URL, href)
    return "", ""


def _parse_pdf_url(paper_node, paper_url):
    pdf_link = paper_node.select_one("a[href$='.pdf'], a[href*='.pdf']")
    if pdf_link:
        return urljoin(ACL_ANTHOLOGY_BASE_URL, pdf_link.get("href", ""))
    return f"{paper_url}.pdf" if paper_url else ""


def fetch_paper_detail(paper):
    requests, BeautifulSoup = _require_crawler_deps()
    try:
        resp = requests.get(
            paper["url"],
            timeout=30,
            headers={"User-Agent": "ACL2026-Guide-CN/1.0"},
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        abstract = _text(soup.select_one("div.acl-abstract"))
        title_node = soup.select_one("h2")
        title = _clean_title(_text(title_node)) if title_node else paper.get("title", "")
        return {
            **paper,
            "title": title or paper.get("title", ""),
            "abstract": abstract or paper.get("abstract", ""),
        }
    except Exception as e:
        return {**paper, "detail_error": str(e)}


def _load_detail_cache():
    path = Path(DETAIL_CACHE_JSON)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {p["id"]: p for p in data.get("papers", []) if p.get("id")}
    except Exception:
        return {}


def _save_detail_cache(cache):
    papers = sorted(cache.values(), key=lambda p: p.get("id", ""))
    out = {
        "meta": {
            "source": SOURCE_NAME,
            "conference": "ACL 2026",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total": len(papers),
            "description": "ACL Anthology paper detail cache with abstracts",
        },
        "papers": papers,
    }
    Path(DETAIL_CACHE_JSON).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def enrich_missing_details(papers):
    cache = _load_detail_cache()
    if cache:
        papers = [{**p, **cache[p["id"]]} if p["id"] in cache and cache[p["id"]].get("abstract") else p for p in papers]

    missing = [p for p in papers if not p.get("abstract")]
    if not missing:
        return papers
    print(f"[1.5/3] 从单篇 ACL Anthology 页面补充 abstract：{len(missing)} 篇...")
    by_id = {p["id"]: p for p in papers}
    with ThreadPoolExecutor(max_workers=DETAIL_MAX_WORKERS) as ex:
        futures = {ex.submit(fetch_paper_detail, p): p for p in missing}
        for fut in tqdm(as_completed(futures), total=len(futures), desc="补摘要中"):
            updated = fut.result()
            by_id[updated["id"]] = updated
            cache[updated["id"]] = updated
            if len(cache) % 100 == 0:
                _save_detail_cache(cache)
    enriched = [by_id[p["id"]] for p in papers]
    n_with_abs = sum(1 for p in enriched if p.get("abstract"))
    print(f"  已获得 abstract：{n_with_abs}/{len(enriched)} 篇。")
    _save_detail_cache(cache)
    return enriched


def _iter_paper_nodes(soup):
    nodes = soup.select("div.d-sm-flex.align-items-stretch.mb-3, .paper, div.acl-paper")
    if nodes:
        return nodes
    # ACL Anthology event pages usually expose one paper per list item.
    return [li for li in soup.select("li") if _parse_title_link(li)[0]]


def _is_real_paper_id(paper_id):
    if not paper_id:
        return False
    if paper_id.endswith(".bib"):
        return False
    if not paper_id.startswith("2026."):
        return False
    # ACL Anthology uses *.0 for proceedings/front matter pages, not papers.
    if paper_id.rsplit(".", 1)[-1] == "0":
        return False
    return bool(re.match(r"^2026\.[a-z0-9-]+\.\d+$", paper_id))


def fetch_all_acl_papers():
    requests, BeautifulSoup = _require_crawler_deps()
    print(f"[1/3] 从 {SOURCE_NAME} 拉取 ACL 2026 公开论文...")
    print(f"  URL: {ACL_ANTHOLOGY_EVENT_URL}")

    resp = requests.get(
        ACL_ANTHOLOGY_EVENT_URL,
        timeout=30,
        headers={"User-Agent": "ACL2026-Guide-CN/1.0"},
    )
    if resp.status_code == 404:
        raise SystemExit(
            "❌ ACL Anthology 还没有公开 ACL 2026 event 页面。"
            "请稍后重试，或用 ACL_ANTHOLOGY_EVENT_URL 指向已发布的 ACL 2026 页面。"
        )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    papers = []
    current_track = "Unknown Track"

    paper_node_ids = {id(node) for node in _iter_paper_nodes(soup)}
    for node in soup.find_all(["h2", "h3", "h4", "div", "li"]):
        if node.name in {"h2", "h3", "h4"}:
            current_track = _extract_track_from_heading(node)
            continue
        if id(node) not in paper_node_ids:
            continue
        title, url = _parse_title_link(node)
        if not title or not url:
            continue
        paper_id = _parse_paper_id_from_url(url)
        if not _is_real_paper_id(paper_id):
            continue
        papers.append(
            normalize_acl_paper(
                {
                    "id": paper_id,
                    "url": url,
                    "title": title,
                    "authors": _parse_authors(node),
                    "track": current_track,
                    "abstract": _parse_abstract(node),
                    "pdf_url": _parse_pdf_url(node, url),
                }
            )
        )

    # De-duplicate because broad selectors can see the same anchor more than once.
    unique = {}
    for paper in papers:
        unique.setdefault(paper["id"], paper)
    papers = list(unique.values())

    if not papers:
        raise SystemExit(
            "❌ 没有从 ACL Anthology 页面解析到 ACL 2026 论文。"
            "可能是 ACL 2026 尚未发布，或页面结构变化；可设置 ACL_ANTHOLOGY_EVENT_URL 指向具体 proceedings 页面后重试。"
        )

    print(f"  共解析到 {len(papers)} 篇论文。")
    return papers


def normalize_acl_paper(raw):
    return {
        "id": raw.get("id", "").strip(),
        "url": raw.get("url", "").strip(),
        "pdf_url": raw.get("pdf_url", "").strip(),
        "title": raw.get("title", "").strip(),
        "authors": raw.get("authors", []) or [],
        "track": raw.get("track", "") or "Unknown Track",
        "primary_area": raw.get("primary_area"),
        "category": raw.get("category"),
        "keywords": raw.get("keywords", []) or [],
        "tldr": raw.get("tldr", "") or "",
        "abstract": raw.get("abstract", "") or "",
    }


# ============ 4. LLM 研究方向分类 ============
SYSTEM_PROMPT_CAT = (
    "你是一位精通 NLP 和计算语言学的研究员。给定一篇或多篇 ACL 2026 论文，"
    "你需要为每篇论文从候选研究方向中选出最匹配的一个。严格只输出用户要求的 JSON，"
    "不要写任何解释、Markdown、思考过程。"
)


def build_categorize_prompt(paper):
    direction_list = "\n".join(f"- {c['name']}：{c['hint']}" for c in RESEARCH_DIRECTIONS)
    authors = "、".join(paper.get("authors", []) or [])
    return f"""请把下面这篇 ACL 2026 论文归入一个 NLP/计算语言学研究方向。

候选研究方向：
{direction_list}

规则：
1. 只能从上面列表里选，名字一字不差。
2. 不到万不得已不要选 "其他"。
3. 同时涉及多个方向时，选择论文研究焦点最集中的那个。

【论文标题】{paper['title']}
【作者】{authors or '(无)'}
【来源 Track】{paper.get('track') or 'Unknown Track'}
【关键词】{"、".join(paper.get("keywords", []) or []) or "(无)"}
【Abstract】
{paper.get('abstract') or '(无)'}

只输出 JSON：{{"primary_area": "<中文名>"}}"""


def build_categorize_batch_prompt(papers):
    direction_list = "\n".join(f"- {c['name']}：{c['hint']}" for c in RESEARCH_DIRECTIONS)
    paper_blocks = []
    for p in papers:
        authors = "、".join(p.get("authors", []) or [])
        abstract = (p.get("abstract") or "(无)")[:1600]
        paper_blocks.append(
            f"""ID: {p['id']}
标题: {p['title']}
作者: {authors or '(无)'}
来源 Track: {p.get('track') or 'Unknown Track'}
Abstract: {abstract}"""
        )
    joined = "\n\n---\n\n".join(paper_blocks)
    return f"""请把下面 {len(papers)} 篇 ACL 2026 论文分别归入一个 NLP/计算语言学研究方向。

候选研究方向：
{direction_list}

规则：
1. 每篇论文只能从上面列表里选一个研究方向，名字一字不差。
2. 不到万不得已不要选 "其他"。
3. 同时涉及多个方向时，选择论文研究焦点最集中的那个。
4. 必须返回所有输入 ID，不能遗漏。

论文列表：
{joined}

只输出严格 JSON，结构如下：
{{
  "items": [
    {{"id": "论文ID", "primary_area": "中文研究方向"}}
  ]
}}"""


def _extract_text(resp):
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


def _parse_direction(text, valid_names):
    raw = (text or "").strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            cand = str(obj.get("primary_area") or obj.get("category") or "").strip()
            if cand in valid_names:
                return cand
    except Exception:
        pass
    m = re.search(r'"(?:primary_area|category)"\s*:\s*"([^"]+)"', raw)
    if m and m.group(1) in valid_names:
        return m.group(1)
    cleaned = re.sub(r"[\"'`*【】「」\s]", "", raw)
    for name in valid_names:
        if cleaned == re.sub(r"\s", "", name):
            return name
    hits = [n for n in valid_names if n != "其他" and n in raw]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        return max(hits, key=len)
    return "其他" if "其他" in valid_names else valid_names[-1]


def _chat_completion_with_retries(client, **kwargs):
    extra_body = dict(kwargs.get("extra_body") or {})
    extra_body.setdefault("enable_thinking", False)
    kwargs["extra_body"] = extra_body
    last_error = None
    for attempt in range(API_MAX_RETRIES):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            last_error = e
            msg = str(e)
            retryable = (
                "429" in msg
                or "rate" in msg.lower()
                or "速率限制" in msg
                or "connection error" in msg.lower()
                or "timeout" in msg.lower()
                or "temporarily unavailable" in msg.lower()
            )
            if not retryable or attempt == API_MAX_RETRIES - 1:
                raise
            sleep_s = API_RETRY_SLEEP * (attempt + 1)
            tqdm.write(f"[重试] {msg[:120]}；等待 {sleep_s:.0f}s 后重试...")
            time.sleep(sleep_s)
    raise last_error


def categorize_paper(client, paper):
    valid_names = [c["name"] for c in RESEARCH_DIRECTIONS]
    fallback = "其他"
    kwargs = dict(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_CAT},
            {"role": "user", "content": build_categorize_prompt(paper)},
        ],
        max_tokens=200,
        temperature=0,
    )
    try:
        resp = _chat_completion_with_retries(client, **kwargs, response_format={"type": "json_object"})
    except Exception:
        try:
            resp = _chat_completion_with_retries(client, **kwargs)
        except Exception as e:
            return paper["id"], fallback, f"api error: {e}"

    text = _extract_text(resp)
    name = _parse_direction(text, valid_names)
    return paper["id"], name, None


def categorize_paper_batch(client, papers):
    if len(papers) == 1:
        return [categorize_paper(client, papers[0])]

    valid_names = [c["name"] for c in RESEARCH_DIRECTIONS]
    fallback = "其他"
    kwargs = dict(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_CAT},
            {"role": "user", "content": build_categorize_batch_prompt(papers)},
        ],
        max_tokens=1200,
        temperature=0,
    )
    try:
        resp = _chat_completion_with_retries(client, **kwargs, response_format={"type": "json_object"})
    except Exception:
        try:
            resp = _chat_completion_with_retries(client, **kwargs)
        except Exception as e:
            return [(p["id"], fallback, f"api error: {e}") for p in papers]

    text = _extract_text(resp)
    try:
        obj = json.loads(text)
        raw_items = obj.get("items", []) if isinstance(obj, dict) else []
    except Exception:
        raw_items = []

    parsed = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id", "")).strip()
        area = str(item.get("primary_area") or item.get("category") or "").strip()
        if pid and area in valid_names:
            parsed[pid] = area

    if not parsed:
        # Some OpenAI-compatible providers are stricter with batched JSON output.
        # Preserve quality by falling back to the proven single-paper prompt.
        return [categorize_paper(client, paper) for paper in papers]

    results = []
    for paper in papers:
        if paper["id"] in parsed:
            results.append((paper["id"], parsed[paper["id"]], None))
        else:
            results.append(categorize_paper(client, paper))
    return results


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


# ============ 5. 主流程 ============
def save(papers, total_accepted):
    papers = [p for p in papers if _is_real_paper_id(p.get("id", "")) and p.get("abstract")]
    out = {
        "meta": {
            "source": SOURCE_NAME,
            "conference": "ACL 2026",
            "total": len(papers),
            "total_accepted": total_accepted,
            "description": DESCRIPTION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "taxonomy": "two-level: primary_area/category assigned by LLM from title and abstract",
            "fields": {
                "id": "论文唯一标识",
                "url": "ACL Anthology 论文链接",
                "pdf_url": "PDF 链接",
                "title": "英文标题",
                "authors": "作者列表",
                "track": "ACL Anthology 来源/Track",
                "primary_area": "LLM 打的一级研究方向（中文）",
                "category": "LLM 打的二级小类（第一版与 primary_area 相同）",
                "keywords": "关键词列表",
                "tldr": "TL;DR",
                "abstract": "完整 Abstract",
            },
        },
        "papers": papers,
    }
    Path(OUTPUT_JSON).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    if API_KEY == "YOUR_API_KEY_HERE":
        raise SystemExit("❌ 请先在 .env 写 OPENAI_API_KEY")
    print(f"使用 LLM: {MODEL} @ {BASE_URL}  (key: {API_KEY[:8]}...)")

    all_papers = fetch_all_acl_papers()
    if LIMIT_PAPERS > 0:
        print(f"  测试模式：仅处理前 {LIMIT_PAPERS} 篇论文。")
        all_papers = all_papers[:LIMIT_PAPERS]
    all_papers = enrich_missing_details(all_papers)

    done = {}
    if RESUME and Path(OUTPUT_JSON).exists():
        try:
            existing = json.loads(Path(OUTPUT_JSON).read_text(encoding="utf-8"))
            done = {
                p["id"]: p
                for p in existing.get("papers", [])
                if (
                    _is_real_paper_id(p.get("id", ""))
                    and p.get("primary_area")
                    and p.get("category")
                    and p.get("abstract")
                    and not p.get("category_error")
                )
            }
            if done:
                print(f"\n[2/3] 已恢复 {len(done)} 篇已分类的论文。")
        except Exception:
            pass

    todo = [p for p in all_papers if p["id"] not in done]
    results = list(done.values())

    if todo:
        print(f"\n[2/3] 调用 LLM 给 {len(todo)} 篇论文分配研究方向...")
        print(f"  批量大小: {BATCH_SIZE}，并发: {MAX_WORKERS}")
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        pbar = tqdm(total=len(todo), desc="分类中")
        batches = list(_chunks(todo, BATCH_SIZE))
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(categorize_paper_batch, client, batch): batch for batch in batches}
            for fut in as_completed(futures):
                batch = futures[fut]
                by_id = {p["id"]: p for p in batch}
                for pid, primary_area, err in fut.result():
                    paper = by_id[pid]
                    rec = {**paper, "primary_area": primary_area, "category": primary_area}
                    if err:
                        rec["category_error"] = err
                        tqdm.write(f"[警告] {pid}: {err[:120]}")
                    results.append(rec)
                    pbar.update(1)
                if len(results) % 100 == 0:
                    save(results, len(all_papers))
        pbar.close()
    else:
        print("\n[2/3] 无新论文需要分类。")

    direction_order = {d["name"]: i for i, d in enumerate(RESEARCH_DIRECTIONS)}
    results.sort(key=lambda p: (direction_order.get(p.get("primary_area", ""), 999), p.get("track", ""), p["title"]))
    save(results, len(all_papers))

    print(f"\n[3/3] ✅ 完成！共 {len(results)} 篇 → {OUTPUT_JSON}")
    print("\n研究方向分布:")
    for area, count in Counter(p.get("primary_area", "其他") for p in results).most_common():
        print(f"  {count:5d}  {area}")


if __name__ == "__main__":
    main()
