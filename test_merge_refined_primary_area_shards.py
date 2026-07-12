import json
import tempfile
import unittest
from pathlib import Path

from merge_refined_primary_area_shards import merge_refined_shards


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class MergeRefinedPrimaryAreaShardsTest(unittest.TestCase):
    def test_merge_preserves_order_and_accepts_valid_primary_category_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "ACL2026_all_papers.json"
            output = root / "full.json"
            report = root / "report.md"
            base_papers = [
                {"id": "p0", "primary_area": "大语言模型与基础模型", "category": "推理、规划与思维链"},
                {"id": "p1", "primary_area": "大语言模型与基础模型", "category": "Agent 与工具使用"},
            ]
            write_json(source, {"meta": {"total": 2}, "papers": base_papers})
            write_json(
                root / "ACL2026_refined_primary_areas_shard_0.json",
                {
                    "meta": {},
                    "papers": [
                        {**base_papers[0], "primary_area": "问答、检索与 RAG", "category": "检索增强生成", "category_refined_by": "test"},
                    ],
                },
            )
            write_json(
                root / "ACL2026_refined_primary_areas_shard_1.json",
                {
                    "meta": {},
                    "papers": [
                        {**base_papers[1], "primary_area": "对话系统与交互", "category": "人机协作与工作流", "category_refined_by": "test"},
                    ],
                },
            )

            summary = merge_refined_shards(
                source,
                str(root / "ACL2026_refined_primary_areas_shard_*.json"),
                output,
                report,
            )

            self.assertEqual(2, summary["records"])
            self.assertEqual([], summary["missing"])
            self.assertEqual([], summary["invalid"])
            self.assertEqual([], summary["error_ids"])
            merged = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(["p0", "p1"], [paper["id"] for paper in merged["papers"]])
            self.assertTrue(merged["meta"]["primary_area_refined"])

    def test_merge_rejects_records_with_refinement_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "ACL2026_all_papers.json"
            output = root / "full.json"
            report = root / "report.md"
            base_paper = {"id": "p0", "primary_area": "大语言模型与基础模型", "category": "Agent 与工具使用"}
            write_json(source, {"meta": {"total": 1}, "papers": [base_paper]})
            write_json(
                root / "ACL2026_refined_primary_areas_shard_0.json",
                {
                    "meta": {},
                    "papers": [
                        {
                            **base_paper,
                            "primary_area": "问答、检索与 RAG",
                            "category": "检索增强生成",
                            "category_refined_by": "test",
                            "category_refine_error": "api error: rate limit",
                        }
                    ],
                },
            )

            summary = merge_refined_shards(
                source,
                str(root / "ACL2026_refined_primary_areas_shard_*.json"),
                output,
                report,
            )

            self.assertEqual(["p0"], summary["error_ids"])
            self.assertEqual(["p0"], summary["invalid"])
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
