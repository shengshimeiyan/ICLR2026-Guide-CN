import importlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from build_html_full import normalize_search_text


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class BuildHtmlFullTest(unittest.TestCase):
    def test_search_normalizes_hyphen_spacing(self):
        self.assertIn(
            "llm-based",
            normalize_search_text("Building Multi-turn Intent Classification with LLM -based Labeling"),
        )
        self.assertEqual(
            normalize_search_text("LLM-based"),
            normalize_search_text("LLM -based"),
        )

    def test_build_uses_configured_paths_and_renders_page_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_json = root / "refined.json"
            cn_json = root / "cn.json"
            output_html = root / "index.html"
            papers = [
                {
                    "id": "p1",
                    "title": "LLM Agents for Clinical QA",
                    "url": "https://example.com/p1",
                    "authors": ["Alice"],
                    "track": "Main Conference",
                    "primary_area": "NLP 应用与系统",
                    "category": "医疗、生物与临床 NLP",
                    "abstract": "A clinical QA paper.",
                    "keywords": [],
                    "tldr": "",
                },
                {
                    "id": "p2",
                    "title": "Building Multi-turn Intent Classification with LLM -based Labeling",
                    "url": "https://example.com/p2",
                    "authors": ["Bob"],
                    "track": "Findings",
                    "primary_area": "评测、基准与数据集",
                    "category": "任务基准与共享任务",
                    "abstract": "A benchmark paper.",
                    "keywords": [],
                    "tldr": "",
                },
            ]
            write_json(input_json, {"meta": {"primary_area_refined": True}, "papers": papers})
            write_json(
                cn_json,
                {
                    "papers": [
                        {
                            "id": "p1",
                            "中文分析": {
                                "研究动机": "动机",
                                "解决问题": "问题",
                                "现象分析": "现象",
                                "主要方法": "方法",
                                "数据集与实验": "实验",
                                "主要贡献": "贡献",
                            },
                        }
                    ]
                },
            )

            env = {
                "INPUT_JSON": str(input_json),
                "CN_OVERLAY_JSON": str(cn_json),
                "OUTPUT_HTML": str(output_html),
            }
            with patch.dict(os.environ, env, clear=False):
                import build_html_full

                importlib.reload(build_html_full)
                build_html_full.build()

            html = output_html.read_text(encoding="utf-8")
            self.assertIn("NLP 应用与系统", html)
            self.assertIn("大类分布", html)
            self.assertIn("area-bar", html)
            self.assertIn("Track 筛选", html)
            self.assertIn("Main", html)
            self.assertIn("一级分类优化说明", html)
            self.assertIn("如果 LLM 只是方法或工具", html)
            self.assertIn("const PAPERS =", html)
            self.assertIn("llm-based", html)
            self.assertIn("renderMore", html)
            self.assertIn("id=\"load-more\"", html)
            self.assertIn("只看有中文分析", html)
            self.assertIn("只看 Main/Findings", html)
            self.assertIn("清除筛选", html)
            self.assertIn("result-count", html)
            html_without_scripts = re.sub(r"<script.*?</script>", "", html, flags=re.S)
            self.assertNotIn("<article", html_without_scripts)


if __name__ == "__main__":
    unittest.main()
