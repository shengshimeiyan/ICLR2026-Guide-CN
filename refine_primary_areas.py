# -*- coding: utf-8 -*-
"""Refine ACL 2026 primary areas and subcategories together.

This script reassigns both ``primary_area`` and ``category`` so papers that
use LLMs as tools can move back to their real task/application area.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI
from tqdm import tqdm

from refine_categories import (
    SUBCATEGORY_TAXONOMY,
    build_notifyx_payload as _category_notify_payload,
    chunks,
    get_reached_milestones,
    select_shard,
    stratified_sample,
    valid_subcategories,
)


def _load_dotenv():
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in os.environ:
            os.environ[key] = value.strip().strip("'\"")


_load_dotenv()


INPUT_JSON = os.environ.get("INPUT_JSON", "ACL2026_all_papers.json")
OUTPUT_JSON = os.environ.get("OUTPUT_JSON", "ACL2026_refined_primary_areas.json")
LIMIT_PAPERS = int(os.environ.get("LIMIT_PAPERS", "0") or "0")
STRATIFIED_SAMPLE = os.environ.get("STRATIFIED_SAMPLE", "0") == "1"
SHARD_INDEX = int(os.environ.get("SHARD_INDEX", "0") or "0")
SHARD_TOTAL = int(os.environ.get("SHARD_TOTAL", "1") or "1")

API_KEY = os.environ.get("OPENAI_API_KEY", "YOUR_API_KEY_HERE")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "1"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "5"))
API_TIMEOUT = float(os.environ.get("API_TIMEOUT", "90"))
API_MAX_RETRIES = int(os.environ.get("API_MAX_RETRIES", "6"))
API_RETRY_SLEEP = float(os.environ.get("API_RETRY_SLEEP", "10"))
NOTIFYX_API_KEY = os.environ.get("NOTIFYX_API_KEY", "")
NOTIFYX_TEAM = os.environ.get("NOTIFYX_TEAM", "")
NOTIFYX_ENDPOINT = os.environ.get("NOTIFYX_ENDPOINT", "https://www.notifyx.cn/api/v1/send")


PRIMARY_AREA_POLICY = [
    "优先判断论文的主要研究问题和贡献，而不是使用了什么模型。",
    "如果 LLM 只是方法或工具，归入对应任务、应用、评测、安全、检索、多模态、语音或对话大类。",
    "只有主要贡献是基础模型本身的预训练、架构、对齐、推理机制、Agent、长上下文、效率或能力分析时，才归入大语言模型与基础模型。",
    "benchmark、dataset、evaluation 或 shared task 论文优先考虑评测、基准与数据集，除非评测对象强绑定某个领域。",
    "其他只作为最后兜底，不要为了平均分布而硬分。",
]


SYSTEM_PROMPT = (
    "你是一位熟悉 ACL 投稿方向、ACL workshop/track 和 ICLR 风格分类体系的 NLP 研究员。"
    "你要同时选择一级研究方向 primary_area 和该一级下的二级 category。"
    "严格输出 JSON，不要解释，不要 Markdown，不要思考过程。"
)


def primary_areas():
    return list(SUBCATEGORY_TAXONOMY)


def taxonomy_text():
    blocks = []
    for primary, categories in SUBCATEGORY_TAXONOMY.items():
        blocks.append(f"- {primary}: {'；'.join(categories)}")
    return "\n".join(blocks)


def build_prompt(paper):
    abstract = (paper.get("abstract") or "")[:1800]
    keywords = "、".join(paper.get("keywords", []) or []) or "(无)"
    policy = "\n".join(f"- {rule}" for rule in PRIMARY_AREA_POLICY)
    return f"""请为这篇 ACL 2026 论文重新选择一级研究方向和二级分类。

分类体系（先选 primary_area，再从该 primary_area 后面的候选里选 category）：
{taxonomy_text()}

判定规则：
{policy}

特别注意：
- 如果 LLM 只是方法或工具，请按论文真正的任务/应用/评测对象分类。
- category 必须属于所选 primary_area 的候选二级分类，名字必须一字不差。

论文信息：
ID: {paper["id"]}
标题: {paper.get("title", "")}
Track: {paper.get("track", "")}
原一级分类: {paper.get("primary_area", "")}
原二级分类: {paper.get("category", "")}
关键词: {keywords}
Abstract:
{abstract}

只输出严格 JSON：
{{"primary_area": "一级研究方向名", "category": "二级分类名"}}"""


def build_batch_prompt(papers):
    policy = "\n".join(f"{idx + 1}. {rule}" for idx, rule in enumerate(PRIMARY_AREA_POLICY))
    blocks = []
    for paper in papers:
        abstract = (paper.get("abstract") or "")[:1400]
        blocks.append(
            f"""ID: {paper["id"]}
标题: {paper.get("title", "")}
Track: {paper.get("track", "")}
原一级分类: {paper.get("primary_area", "")}
原二级分类: {paper.get("category", "")}
Abstract: {abstract}"""
        )
    joined = "\n\n---\n\n".join(blocks)
    return f"""请为下面 {len(papers)} 篇 ACL 2026 论文重新选择一级研究方向和二级分类。

分类体系：
{taxonomy_text()}

判定规则：
{policy}

要求：
1. 必须返回所有输入 ID，不能遗漏。
2. primary_area 必须来自分类体系中的一级研究方向。
3. category 必须属于所选 primary_area 的候选二级分类，名称必须一字不差。
4. 如果 LLM 只是方法或工具，按任务/应用/评测对象分类，不要自动归入大语言模型与基础模型。
5. 只输出 JSON。

论文列表：
{joined}

输出格式：
{{"items": [{{"id": "论文ID", "primary_area": "一级研究方向名", "category": "二级分类名"}}]}}"""


def _fallback_category(primary):
    valid = valid_subcategories(primary)
    return "其他" if "其他" in valid else valid[-1]


def _extract_json_dict(text):
    raw = (text or "").strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if match:
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict):
                return obj
        except Exception:
            return {}
    return {}


def _clean_label(value):
    return re.sub(r"[\"'`*【】「」\s]", "", str(value or ""))


def _parse_primary(value):
    candidate = str(value or "").strip()
    if candidate in SUBCATEGORY_TAXONOMY:
        return candidate
    cleaned = _clean_label(candidate)
    for primary in SUBCATEGORY_TAXONOMY:
        if cleaned == _clean_label(primary):
            return primary
    hits = [primary for primary in SUBCATEGORY_TAXONOMY if primary in candidate]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        return max(hits, key=len)
    return "其他"


def _parse_category(value, primary):
    valid = valid_subcategories(primary)
    candidate = str(value or "").strip()
    if candidate in valid:
        return candidate
    cleaned = _clean_label(candidate)
    for category in valid:
        if cleaned == _clean_label(category):
            return category
    hits = [category for category in valid if category in candidate]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        return max(hits, key=len)
    return _fallback_category(primary)


def parse_area_category(text):
    obj = _extract_json_dict(text)
    primary = _parse_primary(obj.get("primary_area") or obj.get("area") or obj.get("primary"))
    category = _parse_category(obj.get("category") or obj.get("subcategory"), primary)
    return primary, category


def refine_record(paper, primary_area, category, error=None):
    record = dict(paper)
    record["primary_area"] = primary_area
    record["category"] = category
    record["category_refined_at"] = datetime.now(timezone.utc).isoformat()
    record["category_refined_by"] = MODEL
    record["primary_area_refined"] = True
    if error:
        record["category_refine_error"] = error
    else:
        record.pop("category_refine_error", None)
        record.pop("category_error", None)
    return record


def is_valid_refined_record(record):
    primary = record.get("primary_area")
    category = record.get("category")
    return (
        bool(record.get("id"))
        and bool(record.get("category_refined_by"))
        and not record.get("category_refine_error")
        and primary in SUBCATEGORY_TAXONOMY
        and category in valid_subcategories(primary)
    )


def load_existing_refined():
    path = Path(OUTPUT_JSON)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {record["id"]: record for record in data.get("papers", []) if is_valid_refined_record(record)}


def _extract_text(resp):
    try:
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return str(resp)[:500]


def _chat_completion_with_retries(client, **kwargs):
    extra_body = dict(kwargs.get("extra_body") or {})
    extra_body.setdefault("enable_thinking", False)
    kwargs["extra_body"] = extra_body
    last_error = None
    for attempt in range(API_MAX_RETRIES):
        try:
            resp = client.chat.completions.create(**kwargs)
            if not _extract_text(resp):
                raise ValueError("empty message.content")
            return resp
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
                or "empty message.content" in msg
            )
            if not retryable or attempt == API_MAX_RETRIES - 1:
                raise
            sleep_s = API_RETRY_SLEEP * (attempt + 1)
            tqdm.write(f"[retry] {msg[:120]}; sleep {sleep_s:.0f}s before retry...")
            time.sleep(sleep_s)
    raise last_error


def refine_one(client, paper):
    kwargs = dict(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(paper)},
        ],
        temperature=0,
        max_tokens=160,
    )
    try:
        try:
            resp = _chat_completion_with_retries(client, **kwargs, response_format={"type": "json_object"})
        except Exception:
            resp = _chat_completion_with_retries(client, **kwargs)
        primary, category = parse_area_category(_extract_text(resp))
        return paper["id"], primary, category, None
    except Exception as e:
        primary = _parse_primary(paper.get("primary_area"))
        category = _parse_category(paper.get("category"), primary)
        return paper["id"], primary, category, f"api error: {e}"


def refine_batch(client, papers):
    if len(papers) == 1:
        return [refine_one(client, papers[0])]
    kwargs = dict(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_batch_prompt(papers)},
        ],
        temperature=0,
        max_tokens=max(900, 120 * len(papers)),
    )
    try:
        try:
            resp = _chat_completion_with_retries(client, **kwargs, response_format={"type": "json_object"})
        except Exception:
            resp = _chat_completion_with_retries(client, **kwargs)
        obj = json.loads(_extract_text(resp))
        items = obj.get("items", []) if isinstance(obj, dict) else []
    except Exception:
        return [refine_one(client, paper) for paper in papers]

    parsed = {}
    by_id = {paper["id"]: paper for paper in papers}
    for item in items:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or "").strip()
        if pid in by_id:
            primary = _parse_primary(item.get("primary_area") or item.get("area") or item.get("primary"))
            category = _parse_category(item.get("category") or item.get("subcategory"), primary)
            parsed[pid] = (primary, category)

    results = []
    for paper in papers:
        if paper["id"] in parsed:
            primary, category = parsed[paper["id"]]
            results.append((paper["id"], primary, category, None))
        else:
            results.append(refine_one(client, paper))
    return results


def build_notifyx_payload(percent, done, total, shard_index=0, shard_total=1, team=""):
    payload = _category_notify_payload(percent, done, total, shard_index, shard_total, team)
    payload["title"] = f"ACL 2026 大类优化进度 {percent}%"
    payload["content"] = payload["content"].replace("二级分类", "大类优化").replace("输出：", f"输出：{OUTPUT_JSON}\n原输出：")
    payload["description"] = f"ACL 2026 primary-area refinement {percent}% ({done}/{total})"
    return payload


def send_notifyx(payload, api_key=NOTIFYX_API_KEY, endpoint=NOTIFYX_ENDPOINT):
    if not api_key:
        return False
    url = f"{endpoint.rstrip('/')}/{api_key}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response.read()
        return True
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"[notifyx failed] {e}")
        return False


def notify_progress(done, total, sent):
    if not NOTIFYX_API_KEY or SHARD_TOTAL != 1:
        return
    for milestone in get_reached_milestones(done, total, sent):
        payload = build_notifyx_payload(milestone, done, total, SHARD_INDEX, SHARD_TOTAL, NOTIFYX_TEAM)
        if send_notifyx(payload):
            print(f"[notifyx] sent {milestone}% progress notification")
        sent.add(milestone)


def save(records, meta, partial=False):
    output = {
        "meta": {
            **meta,
            "primary_area_refined": True,
            "category_refined": True,
            "category_refine_partial": partial,
            "category_model": MODEL,
            "category_taxonomy": "fixed ACL/ICLR-inspired primary and secondary taxonomy",
            "category_shard_index": SHARD_INDEX,
            "category_shard_total": SHARD_TOTAL,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "papers": records,
    }
    Path(OUTPUT_JSON).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    if API_KEY == "YOUR_API_KEY_HERE":
        raise SystemExit("请先配置 OPENAI_API_KEY")
    data = json.loads(Path(INPUT_JSON).read_text(encoding="utf-8"))
    papers = data["papers"]
    if LIMIT_PAPERS:
        papers = stratified_sample(papers, LIMIT_PAPERS) if STRATIFIED_SAMPLE else papers[:LIMIT_PAPERS]
        print(f"Test mode: processing {len(papers)} papers.")
    papers = select_shard(papers, SHARD_INDEX, SHARD_TOTAL)
    if SHARD_TOTAL > 1:
        print(f"Shard: {SHARD_INDEX}/{SHARD_TOTAL}, papers in shard: {len(papers)}")
    if NOTIFYX_API_KEY and SHARD_TOTAL != 1:
        print("NotifyX progress notifications are disabled for parallel shards.")

    print(f"Using LLM: {MODEL} @ {BASE_URL} (key: {API_KEY[:8]}...)")
    print(f"To refine primary areas: {len(papers)} papers, batch={BATCH_SIZE}, workers={MAX_WORKERS}")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=API_TIMEOUT)
    by_id = {paper["id"]: paper for paper in papers}
    refined = load_existing_refined()
    if refined:
        print(f"Resume: loaded {len(refined)} valid refined records.")
    pending = [paper for paper in papers if paper["id"] not in refined]
    if not pending:
        results = [refined[paper["id"]] for paper in papers]
        save(results, data.get("meta", {}), partial=False)
        print(f"[OK] Nothing pending. Output: {OUTPUT_JSON}")
        return

    n_fail = 0
    batches = list(chunks(pending, BATCH_SIZE))
    progress_sent = set()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(refine_batch, client, batch): batch for batch in batches}
        with tqdm(total=len(pending), desc="refining-primary") as pbar:
            for future in as_completed(futures):
                for pid, primary, category, error in future.result():
                    record = refine_record(by_id[pid], primary, category, error)
                    refined[pid] = record
                    if error:
                        n_fail += 1
                        tqdm.write(f"[failed] {pid}: {error[:120]}")
                    pbar.update(1)
                checkpoint = [refined[paper["id"]] for paper in papers if paper["id"] in refined]
                save(checkpoint, data.get("meta", {}), partial=len(checkpoint) < len(papers))
                notify_progress(len(checkpoint), len(papers), progress_sent)

    results = [refined.get(paper["id"], paper) for paper in papers]
    save(results, data.get("meta", {}), partial=False)
    notify_progress(len(results), len(papers), progress_sent)

    print(f"[OK] Output: {OUTPUT_JSON}")
    print(f"Success: {len(results) - n_fail} Failed: {n_fail}")
    print("Primary area distribution:")
    for primary, count in Counter(paper.get("primary_area") for paper in results).most_common():
        print(f"{count:5d}  {primary}")


if __name__ == "__main__":
    main()
