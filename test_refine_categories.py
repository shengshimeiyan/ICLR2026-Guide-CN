import unittest

from refine_categories import (
    SUBCATEGORY_TAXONOMY,
    is_valid_refined_record,
    parse_subcategory,
    refine_record,
    select_shard,
)


class RefineCategoriesTest(unittest.TestCase):
    def test_taxonomy_covers_existing_primary_areas(self):
        expected = {
            "大语言模型与基础模型",
            "机器翻译与多语言",
            "信息抽取与知识",
            "问答、检索与 RAG",
            "对话系统与交互",
            "语义、句法与语言学",
            "文本生成与摘要",
            "评测、基准与数据集",
            "安全、伦理、公平与隐私",
            "多模态与具身语言",
            "语音与音频语言处理",
            "计算社会科学与人文",
            "NLP 应用与系统",
            "可解释性与模型分析",
            "其他",
        }
        self.assertEqual(expected, set(SUBCATEGORY_TAXONOMY))
        self.assertTrue(all(len(v) >= 4 for v in SUBCATEGORY_TAXONOMY.values()))

    def test_parse_subcategory_accepts_only_valid_label(self):
        valid = SUBCATEGORY_TAXONOMY["大语言模型与基础模型"][0]
        text = '{"category": "' + valid + '"}'
        self.assertEqual(valid, parse_subcategory(text, "大语言模型与基础模型"))
        fallback = parse_subcategory('{"category": "不存在"}', "大语言模型与基础模型")
        self.assertIn(fallback, SUBCATEGORY_TAXONOMY["大语言模型与基础模型"])

    def test_refine_record_preserves_primary_area(self):
        paper = {
            "id": "p1",
            "title": "A Tool-Using LLM Agent",
            "primary_area": "大语言模型与基础模型",
            "category": "大语言模型与基础模型",
        }
        refined = refine_record(paper, "Agent 与工具使用")
        self.assertEqual("大语言模型与基础模型", refined["primary_area"])
        self.assertEqual("Agent 与工具使用", refined["category"])
        self.assertTrue(is_valid_refined_record(refined))

    def test_invalid_resume_record_is_not_valid(self):
        paper = {
            "id": "p1",
            "primary_area": "大语言模型与基础模型",
            "category": "不存在",
            "category_refined_by": "test-model",
        }
        self.assertFalse(is_valid_refined_record(paper))

    def test_select_shard_partitions_by_original_order(self):
        papers = [{"id": f"p{i}"} for i in range(10)]

        shard0 = select_shard(papers, shard_index=0, shard_total=3)
        shard1 = select_shard(papers, shard_index=1, shard_total=3)
        shard2 = select_shard(papers, shard_index=2, shard_total=3)

        self.assertEqual(["p0", "p3", "p6", "p9"], [p["id"] for p in shard0])
        self.assertEqual(["p1", "p4", "p7"], [p["id"] for p in shard1])
        self.assertEqual(["p2", "p5", "p8"], [p["id"] for p in shard2])
        self.assertEqual(
            sorted(p["id"] for shard in (shard0, shard1, shard2) for p in shard),
            [f"p{i}" for i in range(10)],
        )

    def test_select_shard_rejects_invalid_config(self):
        with self.assertRaises(ValueError):
            select_shard([{"id": "p1"}], shard_index=2, shard_total=2)


if __name__ == "__main__":
    unittest.main()
