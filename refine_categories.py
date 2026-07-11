# -*- coding: utf-8 -*-
"""
Refine ACL 2026 paper categories into finer subcategories.

This script preserves each paper's primary_area and only rewrites category.
It is designed to run a small test first:

  set LIMIT_PAPERS=100
  set STRATIFIED_SAMPLE=1
  set OUTPUT_JSON=ACL2026_refined_categories_test100.json
  python refine_categories.py
"""

import json
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI
from tqdm import tqdm


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
OUTPUT_JSON = os.environ.get("OUTPUT_JSON", "ACL2026_refined_categories.json")
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


SUBCATEGORY_TAXONOMY = {
    "大语言模型与基础模型": [
        "预训练与模型架构",
        "指令微调与对齐",
        "推理、规划与思维链",
        "Agent 与工具使用",
        "长上下文与记忆",
        "知识编辑与模型更新",
        "高效训练与推理",
        "数据合成与自训练",
        "领域基础模型",
        "能力边界与理论分析",
        "代码、数学与形式化推理",
        "其他基础模型",
    ],
    "机器翻译与多语言": [
        "机器翻译",
        "口语翻译与同声传译",
        "多语言表示与迁移",
        "低资源与濒危语言",
        "跨语言评测与基准",
        "多语言数据构建",
        "代码转换与术语翻译",
        "其他多语言研究",
    ],
    "信息抽取与知识": [
        "命名实体与实体链接",
        "关系抽取与事件抽取",
        "知识图谱与知识表示",
        "文档级信息抽取",
        "开放信息抽取",
        "结构化预测与解析",
        "知识密集型推理",
        "其他信息抽取",
    ],
    "问答、检索与 RAG": [
        "检索增强生成",
        "多跳问答",
        "开放域问答",
        "表格与结构化问答",
        "检索模型与排序",
        "事实性与证据归因",
        "长文档问答",
        "跨语言检索与问答",
        "报告生成与知识整合",
        "其他问答检索",
    ],
    "对话系统与交互": [
        "任务型对话",
        "开放域聊天",
        "对话评测与用户研究",
        "多轮上下文与记忆",
        "个性化与情感交互",
        "人机协作与工作流",
        "文化与社会交互",
        "语音对话系统",
        "其他对话交互",
    ],
    "语义、句法与语言学": [
        "语义表示与词义",
        "句法、形态与语法",
        "语用、篇章与指代",
        "语言学理论与认知建模",
        "语言标注与资源",
        "计算社会语言学",
        "跨语言语言学分析",
        "幽默、隐喻与修辞",
        "其他语言学研究",
    ],
    "文本生成与摘要": [
        "摘要生成",
        "可控文本生成",
        "长文档生成",
        "数据到文本与报告生成",
        "创意写作与风格迁移",
        "生成质量评估",
        "事实一致性与幻觉",
        "其他文本生成",
    ],
    "评测、基准与数据集": [
        "综合评测与排行榜",
        "任务基准与共享任务",
        "数据集构建",
        "评测方法与元评测",
        "LLM-as-a-Judge",
        "鲁棒性与泛化评测",
        "代码、数学与推理评测",
        "领域评测",
        "其他评测资源",
    ],
    "安全、伦理、公平与隐私": [
        "偏见、公平与刻板印象",
        "隐私保护与数据合规",
        "越狱、红队与攻击",
        "内容安全与有害生成",
        "水印、溯源与生成检测",
        "不确定性、可靠性与校准",
        "AI 治理与社会影响",
        "事实性、误导与媒体偏见",
        "其他可信 NLP",
    ],
    "多模态与具身语言": [
        "视觉语言模型",
        "图像与视频理解",
        "多模态生成",
        "多模态检索与 RAG",
        "文档、图表与表格理解",
        "语音-视觉-语言",
        "具身智能与 VLA",
        "多模态评测",
        "其他多模态研究",
    ],
    "语音与音频语言处理": [
        "自动语音识别",
        "语音翻译",
        "语音生成与合成",
        "口语理解与对话",
        "低资源与多语种语音",
        "音频语言模型",
        "语音评测与错误分析",
        "其他语音音频",
    ],
    "计算社会科学与人文": [
        "社交媒体与公共健康",
        "数字人文与文化分析",
        "政治文本与媒体研究",
        "心理、临床与社会行为",
        "语言文档与濒危语言",
        "跨文化 NLP",
        "教育与学习分析",
        "其他社会人文",
    ],
    "NLP 应用与系统": [
        "医疗、生物与临床 NLP",
        "教育应用",
        "法律、金融与商业应用",
        "代码与软件工程",
        "工业系统与部署",
        "系统演示与工具平台",
        "表格、数据库与数据处理",
        "科学发现与化学分子",
        "工作流自动化与 Agent 应用",
        "其他应用系统",
    ],
    "可解释性与模型分析": [
        "机制可解释性",
        "探针与表示分析",
        "注意力与内部行为分析",
        "因果分析与归因",
        "模型能力边界",
        "训练动态与数据影响",
        "神经语言学与认知对齐",
        "其他模型分析",
    ],
    "其他": [
        "自动推理与定理证明",
        "强化学习与决策",
        "优化、编译与系统",
        "科学计算与建模",
        "跨领域机器学习",
        "其他",
    ],
}


SYSTEM_PROMPT = (
    "你是一位熟悉 ACL 投稿方向、ACL workshop/track 和 ICLR 风格细粒度分类的 NLP 研究员。"
    "给定论文的一级研究方向，你只需要从该一级方向下的候选二级类中选出最合适的一类。"
    "严格输出 JSON，不要解释，不要 Markdown，不要思考过程。"
)


def valid_subcategories(primary_area):
    return SUBCATEGORY_TAXONOMY.get(primary_area) or SUBCATEGORY_TAXONOMY["其他"]


def build_prompt(paper):
    primary = paper.get("primary_area") or "其他"
    options = valid_subcategories(primary)
    option_text = "\n".join(f"- {name}" for name in options)
    abstract = (paper.get("abstract") or "")[:1800]
    keywords = "、".join(paper.get("keywords", []) or []) or "(无)"
    return f"""请为这篇 ACL 2026 论文选择一个细粒度二级分类。

一级研究方向：{primary}

候选二级分类（只能选一个，名字必须一字不差）：
{option_text}

参考信号：
- ACL Anthology track/workshop 能作为重要提示，但最终以论文研究焦点为准。
- 如果论文属于 shared task/benchmark/evaluation，优先考虑评测或对应任务细类。
- 如果论文是某领域应用，优先考虑对应应用或领域基础模型细类。
- 不要为了平均分布而硬分；选择最准确的小类。

论文信息：
ID: {paper["id"]}
标题: {paper.get("title", "")}
Track: {paper.get("track", "")}
关键词: {keywords}
Abstract:
{abstract}

只输出严格 JSON：
{{"category": "候选二级分类名"}}"""


def build_batch_prompt(papers):
    blocks = []
    for p in papers:
        primary = p.get("primary_area") or "其他"
        options = "；".join(valid_subcategories(primary))
        abstract = (p.get("abstract") or "")[:1400]
        blocks.append(
            f"""ID: {p["id"]}
一级研究方向: {primary}
候选二级分类: {options}
标题: {p.get("title", "")}
Track: {p.get("track", "")}
Abstract: {abstract}"""
        )
    joined = "\n\n---\n\n".join(blocks)
    return f"""请为下面 {len(papers)} 篇 ACL 2026 论文分别选择细粒度二级分类。

规则：
1. 每篇只能从该论文给出的“候选二级分类”中选择一个。
2. category 名称必须一字不差。
3. 必须返回所有输入 ID，不能遗漏。
4. 只输出 JSON。

论文列表：
{joined}

输出格式：
{{"items": [{{"id": "论文ID", "category": "二级分类名"}}]}}"""


def parse_subcategory(text, primary_area):
    valid = valid_subcategories(primary_area)
    raw = (text or "").strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            candidate = str(obj.get("category") or obj.get("primary_area") or "").strip()
            if candidate in valid:
                return candidate
    except Exception:
        pass
    match = re.search(r'"(?:category|primary_area)"\s*:\s*"([^"]+)"', raw)
    if match and match.group(1) in valid:
        return match.group(1)
    cleaned = re.sub(r"[\"'`*【】「」\s]", "", raw)
    for name in valid:
        if cleaned == re.sub(r"\s", "", name):
            return name
    hits = [name for name in valid if name in raw]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        return max(hits, key=len)
    return "其他" if "其他" in valid else valid[-1]


def refine_record(paper, category, error=None):
    record = dict(paper)
    record["category"] = category
    record["category_refined_at"] = datetime.now(timezone.utc).isoformat()
    record["category_refined_by"] = MODEL
    if error:
        record["category_refine_error"] = error
    else:
        record.pop("category_refine_error", None)
    return record


def is_valid_refined_record(record):
    primary = record.get("primary_area") or "其他"
    category = record.get("category")
    return (
        bool(record.get("id"))
        and bool(record.get("category_refined_by"))
        and not record.get("category_refine_error")
        and category in valid_subcategories(primary)
    )


def load_existing_refined():
    path = Path(OUTPUT_JSON)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data.get("papers", [])
    except Exception:
        return {}
    return {record["id"]: record for record in records if is_valid_refined_record(record)}


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
    primary = paper.get("primary_area") or "其他"
    kwargs = dict(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(paper)},
        ],
        temperature=0,
        max_tokens=120,
    )
    try:
        try:
            resp = _chat_completion_with_retries(client, **kwargs, response_format={"type": "json_object"})
        except Exception:
            resp = _chat_completion_with_retries(client, **kwargs)
        return paper["id"], parse_subcategory(_extract_text(resp), primary), None
    except Exception as e:
        return paper["id"], parse_subcategory("", primary), f"api error: {e}"


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
        max_tokens=900,
    )
    try:
        try:
            resp = _chat_completion_with_retries(client, **kwargs, response_format={"type": "json_object"})
        except Exception:
            resp = _chat_completion_with_retries(client, **kwargs)
        text = _extract_text(resp)
        obj = json.loads(text)
        items = obj.get("items", []) if isinstance(obj, dict) else []
    except Exception:
        return [refine_one(client, paper) for paper in papers]

    parsed = {}
    by_id = {p["id"]: p for p in papers}
    for item in items:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or "").strip()
        if pid in by_id:
            parsed[pid] = parse_subcategory(str(item.get("category") or ""), by_id[pid].get("primary_area"))

    results = []
    for paper in papers:
        if paper["id"] in parsed:
            results.append((paper["id"], parsed[paper["id"]], None))
        else:
            results.append(refine_one(client, paper))
    return results


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def stratified_sample(papers, limit):
    if not limit or len(papers) <= limit:
        return papers
    groups = defaultdict(list)
    for paper in papers:
        groups[paper.get("primary_area") or "其他"].append(paper)
    ordered_areas = [area for area, _ in Counter(p.get("primary_area") or "其他" for p in papers).most_common()]
    selected = []
    idx = 0
    while len(selected) < limit:
        progressed = False
        for area in ordered_areas:
            if idx < len(groups[area]):
                selected.append(groups[area][idx])
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break
        idx += 1
    return selected


def select_shard(papers, shard_index=0, shard_total=1):
    if shard_total < 1:
        raise ValueError("SHARD_TOTAL must be >= 1")
    if shard_index < 0 or shard_index >= shard_total:
        raise ValueError("SHARD_INDEX must satisfy 0 <= SHARD_INDEX < SHARD_TOTAL")
    if shard_total == 1:
        return list(papers)
    return [paper for idx, paper in enumerate(papers) if idx % shard_total == shard_index]


def save(records, meta, partial=False):
    output = {
        "meta": {
            **meta,
            "category_refined": True,
            "category_refine_partial": partial,
            "category_model": MODEL,
            "category_taxonomy": "fixed ACL/ICLR-inspired secondary taxonomy",
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

    print(f"Using LLM: {MODEL} @ {BASE_URL} (key: {API_KEY[:8]}...)")
    print(f"To refine: {len(papers)} papers, batch={BATCH_SIZE}, workers={MAX_WORKERS}")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=API_TIMEOUT)
    by_id = {p["id"]: p for p in papers}
    refined = load_existing_refined()
    if refined:
        print(f"Resume: loaded {len(refined)} valid refined records.")
    pending = [p for p in papers if p["id"] not in refined]
    if not pending:
        results = [refined[p["id"]] for p in papers]
        save(results, data.get("meta", {}), partial=False)
        print(f"[OK] Nothing pending. Output: {OUTPUT_JSON}")
        return

    results = []
    n_fail = 0
    batches = list(chunks(pending, BATCH_SIZE))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(refine_batch, client, batch): batch for batch in batches}
        with tqdm(total=len(pending), desc="refining") as pbar:
            for future in as_completed(futures):
                for pid, category, error in future.result():
                    record = refine_record(by_id[pid], category, error)
                    refined[pid] = record
                    if error:
                        n_fail += 1
                        tqdm.write(f"[failed] {pid}: {error[:120]}")
                    pbar.update(1)
                checkpoint = [refined[p["id"]] for p in papers if p["id"] in refined]
                save(checkpoint, data.get("meta", {}), partial=len(checkpoint) < len(papers))

    for paper in papers:
        results.append(refined.get(paper["id"], paper))
    save(results, data.get("meta", {}), partial=False)

    print(f"[OK] Output: {OUTPUT_JSON}")
    print(f"Success: {len(results) - n_fail} Failed: {n_fail}")
    print("Category distribution:")
    for category, count in Counter(p.get("category") for p in results).most_common(40):
        print(f"{count:5d}  {category}")


if __name__ == "__main__":
    main()
