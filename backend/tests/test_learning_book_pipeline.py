import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import httpx

from app.study import book_service
from app.study.book_service import (
    assess_markdown_quality,
    build_chapter_learning_assets,
    evaluate_power_relevance,
    extract_markdown_from_response,
    split_markdown_chapters,
)


class LearningBookPipelineTests(unittest.TestCase):
    def test_power_market_book_passes_industry_gate(self):
        score, reason, matched = evaluate_power_relevance(
            "电力市场交易基础",
            "本书介绍电力交易、日前市场、实时市场、节点电价、出清和偏差结算。",
        )
        self.assertGreaterEqual(score, 0.26)
        self.assertIn("电力交易", matched)
        self.assertIn("核心概念", reason)

    def test_unrelated_book_is_rejected(self):
        score, reason, matched = evaluate_power_relevance(
            "家庭烘焙入门",
            "介绍面粉、黄油、烤箱温度和面包发酵。",
        )
        self.assertLess(score, 0.26)
        self.assertEqual(matched, [])
        self.assertIn("未识别", reason)

    def test_markdown_is_split_with_page_provenance(self):
        markdown = """# 电力交易教材

<!-- page: 3 -->
# 第一章 市场主体
发电企业与售电公司参与电力交易。

<!-- page: 8 -->
# 第二章 日前市场
日前市场按时段申报并统一出清。
"""
        chapters = split_markdown_chapters(markdown, "电力交易教材")
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]["page_start"], 3)
        self.assertEqual(chapters[1]["page_end"], 8)

    def test_mineru_zip_response_extracts_markdown(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("book/auto/book.md", "# 第一章\n\n电力市场正文")
        response = httpx.Response(
            200,
            headers={"content-type": "application/zip"},
            content=buffer.getvalue(),
        )
        self.assertIn("电力市场正文", extract_markdown_from_response(response))

    def test_fallback_learning_assets_do_not_need_llm(self):
        summary, assets, quiz = build_chapter_learning_assets(
            "日前市场",
            (
                "日前市场是指市场主体在运行日前按时段申报电量和价格，"
                "之后由市场运营机构根据系统约束统一出清。"
                "日前市场形成的出清结果为实时运行提供计划基础。"
            ),
            ["日前市场", "申报", "出清"],
            use_llm=False,
        )
        self.assertIn("日前市场", summary)
        self.assertIn("日前市场", assets["concepts"])
        self.assertTrue(assets["takeaways"])
        self.assertTrue(assets["golden_sentences"])
        self.assertEqual(len(quiz), 3)
        self.assertTrue(all("复习动作" not in item["stem"] for item in quiz))
        self.assertTrue(all(item.get("answer") for item in quiz))
        self.assertTrue(all(item.get("analysis") for item in quiz))

    def test_large_pdfplumber_output_is_blocked_by_quality_gate(self):
        score, reason = assess_markdown_quality(
            "# 电力市场\n\n" + "电力现货市场字符流。" * 10_000,
            "pdfplumber-fulltext",
        )
        self.assertLess(score, 0.62)
        self.assertIn("大型 PDF", reason)

    def test_ocr_page_noise_is_not_used_as_chapter_heading(self):
        markdown = """# 电力交易教材

# 23 〕亭涉
页眉噪声。

# 第一章 日前市场
日前市场按时段申报。

# 第二章 实时市场
实时市场处理运行偏差。
"""
        chapters = split_markdown_chapters(markdown, "电力交易教材")
        self.assertEqual([item["title"] for item in chapters], [
            "第一章 日前市场", "第二章 实时市场",
        ])


class LearningBookUploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_large_upload_is_rejected_during_streaming_and_temp_file_is_removed(self):
        class ChunkedUpload:
            def __init__(self):
                self.chunks = [b"a" * 700_000, b"b" * 700_000]

            async def read(self, _size):
                return self.chunks.pop(0) if self.chunks else b""

        original_dir = book_service.settings.LEARNING_BOOK_DIR
        original_limit = book_service.MAX_FILE_SIZE
        with tempfile.TemporaryDirectory() as tmp:
            try:
                book_service.settings.LEARNING_BOOK_DIR = Path(tmp)
                book_service.MAX_FILE_SIZE = 1_000_000
                with self.assertRaisesRegex(ValueError, "不能超过 300MB"):
                    await book_service.save_book_upload_stream(
                        None,
                        user_id=1,
                        filename="电力市场.pdf",
                        upload=ChunkedUpload(),
                    )
                incoming = Path(tmp) / "_incoming"
                self.assertEqual(list(incoming.iterdir()), [])
            finally:
                book_service.settings.LEARNING_BOOK_DIR = original_dir
                book_service.MAX_FILE_SIZE = original_limit


if __name__ == "__main__":
    unittest.main()
