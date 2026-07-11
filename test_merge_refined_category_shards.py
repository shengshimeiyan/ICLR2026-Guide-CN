import json
import tempfile
import unittest
from pathlib import Path

from merge_refined_category_shards import merge_refined_shards


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class MergeRefinedCategoryShardsTest(unittest.TestCase):
    def test_merge_preserves_original_order_and_validates_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "ACL2026_all_papers.json"
            shard0 = root / "ACL2026_refined_categories_shard_0.json"
            shard1 = root / "ACL2026_refined_categories_shard_1.json"
            output = root / "ACL2026_refined_categories_full.json"
            report = root / "ACL2026_refined_categories_full_report.md"

            base_papers = [
                {"id": "p0", "primary_area": "大语言模型与基础模型", "category": "大语言模型与基础模型"},
                {"id": "p1", "primary_area": "大语言模型与基础模型", "category": "大语言模型与基础模型"},
                {"id": "p2", "primary_area": "大语言模型与基础模型", "category": "大语言模型与基础模型"},
            ]
            write_json(source, {"meta": {"total": 3}, "papers": base_papers})
            write_json(
                shard0,
                {
                    "meta": {"category_shard_index": 0, "category_shard_total": 2},
                    "papers": [
                        {**base_papers[0], "category": "Agent 与工具使用", "category_refined_by": "test"},
                        {**base_papers[2], "category": "推理、规划与思维链", "category_refined_by": "test"},
                    ],
                },
            )
            write_json(
                shard1,
                {
                    "meta": {"category_shard_index": 1, "category_shard_total": 2},
                    "papers": [
                        {**base_papers[1], "category": "指令微调与对齐", "category_refined_by": "test"},
                    ],
                },
            )

            summary = merge_refined_shards(source, str(root / "ACL2026_refined_categories_shard_*.json"), output, report)

            self.assertEqual(3, summary["records"])
            self.assertEqual([], summary["missing"])
            self.assertEqual([], summary["invalid"])
            merged = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(["p0", "p1", "p2"], [p["id"] for p in merged["papers"]])
            self.assertEqual("指令微调与对齐", merged["papers"][1]["category"])
            self.assertTrue(report.exists())

    def test_merge_reports_missing_and_invalid_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "ACL2026_all_papers.json"
            shard0 = root / "ACL2026_refined_categories_shard_0.json"
            output = root / "full.json"
            report = root / "report.md"
            base_papers = [
                {"id": "p0", "primary_area": "大语言模型与基础模型", "category": "大语言模型与基础模型"},
                {"id": "p1", "primary_area": "大语言模型与基础模型", "category": "大语言模型与基础模型"},
            ]
            write_json(source, {"meta": {}, "papers": base_papers})
            write_json(
                shard0,
                {
                    "meta": {},
                    "papers": [
                        {**base_papers[0], "category": "不存在", "category_refined_by": "test"},
                    ],
                },
            )

            summary = merge_refined_shards(source, str(root / "ACL2026_refined_categories_shard_*.json"), output, report)

            self.assertEqual(["p1"], summary["missing"])
            self.assertEqual(["p0"], summary["invalid"])
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
