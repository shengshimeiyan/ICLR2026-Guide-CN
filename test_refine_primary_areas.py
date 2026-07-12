import unittest

from refine_categories import SUBCATEGORY_TAXONOMY
from refine_primary_areas import (
    PRIMARY_AREA_POLICY,
    build_batch_prompt,
    build_prompt,
    is_valid_refined_record,
    parse_area_category,
    refine_record,
)


class RefinePrimaryAreasTest(unittest.TestCase):
    def test_policy_mentions_llm_tool_use_disambiguation(self):
        policy_text = "\n".join(PRIMARY_AREA_POLICY)

        self.assertIn("LLM", policy_text)
        self.assertIn("工具", policy_text)
        self.assertIn("任务", policy_text)

    def test_prompt_exposes_all_primary_areas_and_task_first_policy(self):
        paper = {
            "id": "p1",
            "title": "Using LLMs for Medical Question Answering",
            "track": "Main Conference",
            "abstract": "We use a large language model to answer clinical questions with retrieved evidence.",
            "keywords": [],
        }

        prompt = build_prompt(paper)

        for primary in SUBCATEGORY_TAXONOMY:
            self.assertIn(primary, prompt)
        self.assertIn("如果 LLM 只是方法或工具", prompt)
        self.assertIn("primary_area", prompt)
        self.assertIn("category", prompt)

    def test_parse_area_category_requires_valid_pair(self):
        text = '{"primary_area": "问答、检索与 RAG", "category": "检索增强生成"}'

        primary, category = parse_area_category(text)

        self.assertEqual("问答、检索与 RAG", primary)
        self.assertEqual("检索增强生成", category)

    def test_parse_area_category_rejects_category_from_wrong_primary(self):
        text = '{"primary_area": "问答、检索与 RAG", "category": "越狱、红队与攻击"}'

        primary, category = parse_area_category(text)

        self.assertEqual("问答、检索与 RAG", primary)
        self.assertIn(category, SUBCATEGORY_TAXONOMY[primary])
        self.assertNotEqual("越狱、红队与攻击", category)

    def test_refine_record_updates_primary_and_category_together(self):
        paper = {
            "id": "p1",
            "primary_area": "大语言模型与基础模型",
            "category": "推理、规划与思维链",
        }

        refined = refine_record(paper, "问答、检索与 RAG", "检索增强生成")

        self.assertEqual("问答、检索与 RAG", refined["primary_area"])
        self.assertEqual("检索增强生成", refined["category"])
        self.assertTrue(is_valid_refined_record(refined))
        self.assertNotIn("category_refine_error", refined)

    def test_batch_prompt_requires_all_ids_and_valid_pairs(self):
        prompt = build_batch_prompt(
            [
                {"id": "p1", "title": "A", "track": "T", "abstract": "A"},
                {"id": "p2", "title": "B", "track": "T", "abstract": "B"},
            ]
        )

        self.assertIn("p1", prompt)
        self.assertIn("p2", prompt)
        self.assertIn("必须返回所有输入 ID", prompt)
        self.assertIn("category 必须属于所选 primary_area", prompt)


if __name__ == "__main__":
    unittest.main()
