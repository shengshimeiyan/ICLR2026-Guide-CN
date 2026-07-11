# -*- coding: utf-8 -*-
"""Merge GitHub Actions refined-category shard outputs."""

import glob
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from refine_categories import is_valid_refined_record, stratified_sample


INPUT_JSON = os.environ.get("INPUT_JSON", "ACL2026_all_papers.json")
SHARD_GLOB = os.environ.get("SHARD_GLOB", "ACL2026_refined_categories_shard_*.json")
OUTPUT_JSON = os.environ.get("OUTPUT_JSON", "ACL2026_refined_categories_full.json")
REPORT_MD = os.environ.get("REPORT_MD", "ACL2026_refined_categories_full_report.md")
LIMIT_PAPERS = int(os.environ.get("LIMIT_PAPERS", "0") or "0")
STRATIFIED_SAMPLE = os.environ.get("STRATIFIED_SAMPLE", "0") == "1"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_report(path, summary, category_counts, primary_counts):
    lines = [
        "# ACL2026 Refined Category Merge Report",
        "",
        f"records: {summary['records']}",
        f"shard_files: {summary['shard_files']}",
        f"missing: {len(summary['missing'])}",
        f"invalid: {len(summary['invalid'])}",
        f"duplicate_ids: {len(summary['duplicate_ids'])}",
        "",
        "## Top Categories",
    ]
    lines.extend(f"- {category}: {count}" for category, count in category_counts.most_common(80))
    lines.extend(["", "## Primary Areas"])
    lines.extend(f"- {primary}: {count}" for primary, count in primary_counts.most_common())
    if summary["missing"]:
        lines.extend(["", "## Missing IDs"])
        lines.extend(f"- {pid}" for pid in summary["missing"][:200])
    if summary["invalid"]:
        lines.extend(["", "## Invalid IDs"])
        lines.extend(f"- {pid}" for pid in summary["invalid"][:200])
    if summary["duplicate_ids"]:
        lines.extend(["", "## Duplicate IDs"])
        lines.extend(f"- {pid}" for pid in summary["duplicate_ids"][:200])
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def select_merge_papers(papers, limit_papers=0, stratified=False):
    if not limit_papers:
        return list(papers)
    return stratified_sample(papers, limit_papers) if stratified else list(papers[:limit_papers])


def merge_refined_shards(source_json, shard_glob, output_json, report_md, limit_papers=0, stratified=False):
    source_path = Path(source_json)
    source = load_json(source_path)
    base_papers = select_merge_papers(source["papers"], limit_papers=limit_papers, stratified=stratified)
    base_by_id = {paper["id"]: paper for paper in base_papers}

    refined_by_id = {}
    duplicate_ids = []
    shard_paths = sorted(glob.glob(str(shard_glob)))
    for shard_path in shard_paths:
        shard = load_json(shard_path)
        for paper in shard.get("papers", []):
            pid = paper.get("id")
            if not pid or pid not in base_by_id:
                continue
            if pid in refined_by_id:
                duplicate_ids.append(pid)
            refined_by_id[pid] = paper

    missing = [paper["id"] for paper in base_papers if paper["id"] not in refined_by_id]
    invalid = [
        paper["id"]
        for paper in base_papers
        if paper["id"] in refined_by_id and not is_valid_refined_record(refined_by_id[paper["id"]])
    ]

    merged = [refined_by_id.get(paper["id"], paper) for paper in base_papers]
    summary = {
        "records": len(merged),
        "shard_files": len(shard_paths),
        "missing": missing,
        "invalid": invalid,
        "duplicate_ids": sorted(set(duplicate_ids)),
    }

    category_counts = Counter(paper.get("category") for paper in merged)
    primary_counts = Counter(paper.get("primary_area") for paper in merged)
    write_report(report_md, summary, category_counts, primary_counts)

    if missing or invalid or duplicate_ids:
        return summary

    output = {
        "meta": {
            **source.get("meta", {}),
            "category_refined": True,
            "category_refine_partial": False,
            "category_merge_source": "GitHub Actions shards",
            "category_merge_shard_files": len(shard_paths),
            "category_merge_limit_papers": limit_papers,
            "category_merge_stratified_sample": stratified,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "papers": merged,
    }
    Path(output_json).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main():
    summary = merge_refined_shards(
        INPUT_JSON,
        SHARD_GLOB,
        OUTPUT_JSON,
        REPORT_MD,
        limit_papers=LIMIT_PAPERS,
        stratified=STRATIFIED_SAMPLE,
    )
    print(f"records={summary['records']}")
    print(f"shard_files={summary['shard_files']}")
    print(f"missing={len(summary['missing'])}")
    print(f"invalid={len(summary['invalid'])}")
    print(f"duplicate_ids={len(summary['duplicate_ids'])}")
    print(f"report={REPORT_MD}")
    if summary["missing"] or summary["invalid"] or summary["duplicate_ids"]:
        sys.exit(1)
    print(f"output={OUTPUT_JSON}")


if __name__ == "__main__":
    main()
