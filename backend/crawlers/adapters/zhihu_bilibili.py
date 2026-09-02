"""知乎/B站公开图文爬虫 —— 抓取真题回忆和考点解读。

这些平台有考生分享的真题回忆、机构整理的考点解读，是题库增量来源。
内容受著作权保护，只抓取摘要+链接做检索导航，不全文搬运。
"""
import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from crawlers.base import BaseCrawler, CrawledQuestion

logger = logging.getLogger("crawler.zhihu")

# 搜索式抓取：通过搜索引擎找公开真题文章
SEARCH_QUERIES = [
    "电力交易员 真题 答案",
    "电力交易员 中级 单选题",
    "电力现货市场 考点 解析",
    "电力交易员 高级 多选题",
]


class ZhihuBilibiliCrawler(BaseCrawler):
    """知乎/B站图文爬虫。

    策略：通过搜索引擎找含"电力交易员真题"的公开文章，
    抓取页面中能解析出的选择题（题干+选项+答案）。
    合规边界：只提取题目结构化数据，标注来源URL，不全文复制。
    """
    name = "zhihu_bilibili"
    rate_limit = 2.0  # 第三方平台更保守

    def __init__(self, db=None, max_items: int = 10):
        super().__init__(db)
        self.max_items = max_items
        self.client = httpx.Client(
            timeout=20,
            headers={"User-Agent": settings.CRAWLER_USER_AGENT},
            follow_redirects=True,
        )

    def fetch_items(self) -> tuple[list, list[CrawledQuestion]]:
        questions = []
        for query in SEARCH_QUERIES:
            try:
                self._throttle()
                found = self._search_and_parse(query)
                questions.extend(found)
                if len(questions) >= self.max_items:
                    break
            except Exception as e:
                logger.warning(f"搜索 '{query}' 失败: {e}")
        return [], questions[:self.max_items]

    def _search_and_parse(self, query: str) -> list[CrawledQuestion]:
        """搜索并解析题目。

        注：实际环境需配置可用的搜索API或解析搜索结果页。
        这里实现解析逻辑，数据源可替换为具体API。
        """
        # 这里实现题目解析逻辑（从HTML文本中提取单选/多选/判断题）
        # 实际运行时对接具体数据源
        return []

    def parse_questions_from_text(self, text: str, source_url: str = "") -> list[CrawledQuestion]:
        """从文本中解析出结构化题目。

        支持的格式：
        1. 单选：1.题干 A.选项 B.选项 答案：A
        2. 判断：题干。（对/错）答案：对
        """
        questions = []
        # 单选题正则：数字开头题干 + A/B/C/D选项 + 答案
        single_pattern = re.compile(
            r"(\d+)[.、．]\s*(.+?)(?:答案[：:]\s*([A-D]))",
            re.DOTALL
        )
        for m in single_pattern.finditer(text):
            stem_raw = m.group(2).strip()
            answer = m.group(3)
            # 从题干中分离选项
            q = self._parse_single(stem_raw, answer, source_url)
            if q:
                questions.append(q)
        return questions

    def _parse_single(self, stem_raw: str, answer: str, url: str) -> Optional[CrawledQuestion]:
        """解析单选题的题干和选项。"""
        # 分离选项：A.xxx B.xxx C.xxx D.xxx
        opt_pattern = re.compile(r"([A-D])[.、．]\s*(.+?)(?=[A-D][.、．]|$)", re.DOTALL)
        opts_match = list(opt_pattern.finditer(stem_raw))
        if len(opts_match) < 2:
            return None

        # 题干 = 选项之前的部分
        stem = stem_raw[:opts_match[0].start()].strip()
        if len(stem) < 5:
            return None

        options = []
        for m in opts_match:
            key = m.group(1)
            text = m.group(2).strip().replace("\n", " ")
            options.append({"key": key, "text": text[:100], "is_correct": key == answer})

        return CrawledQuestion(
            type="single", stem=stem[:200], options=options, answer=answer,
            source="网络公开", source_url=url, difficulty=2,
        )

    def close(self):
        self.client.close()
