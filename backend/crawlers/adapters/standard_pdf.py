"""国家职业标准PDF解析器 —— 提取各模块权重表。

数据源：《国家职业标准-电力交易员》(2024版)
URL: http://114.255.111.133/xxgk2020/fdzdgknr/rcrs_4225/jnrc/202402/W020240227573393376261.pdf

这是考点占比的 ground truth，解析后写入 ExamWeight 表，
直接驱动考点预测和组卷配比。
"""
import io
import logging
from typing import Optional

import httpx

from app.config import settings
from crawlers.base import BaseCrawler

logger = logging.getLogger("crawler.standard")

STANDARD_PDF_URL = (
    "http://114.255.111.133/xxgk2020/fdzdgknr/rcrs_4225/jnrc/202402/"
    "W020240227573393376261.pdf"
)


class StandardPdfCrawler(BaseCrawler):
    """国家职业标准PDF解析器。

    下载PDF → pdfplumber提取表格 → 解析权重表 → 更新ExamWeight。
    """
    name = "standard_pdf"
    rate_limit = 2.0

    def __init__(self, db=None, pdf_url: str = STANDARD_PDF_URL):
        super().__init__(db)
        self.pdf_url = pdf_url
        self.client = httpx.Client(
            timeout=60,
            headers={"User-Agent": settings.CRAWLER_USER_AGENT},
            follow_redirects=True,
        )

    def fetch_items(self) -> tuple[list, list]:
        """下载并解析标准PDF，提取权重表。"""
        try:
            pdf_bytes = self._download_pdf()
            weights = self._parse_weights(pdf_bytes)
            self._update_exam_weights(weights)
            return [], []
        except Exception as e:
            logger.error(f"标准PDF解析失败: {e}")
            raise

    def _download_pdf(self) -> bytes:
        """下载PDF。"""
        self._throttle()
        logger.info(f"下载标准PDF: {self.pdf_url}")
        resp = self.client.get(self.pdf_url)
        resp.raise_for_status()
        return resp.content

    def _parse_weights(self, pdf_bytes: bytes) -> list[dict]:
        """用pdfplumber解析权重表。

        返回: [{module_name, level, weight_pct}, ...]
        """
        try:
            import pdfplumber
        except ImportError:
            logger.warning("pdfplumber未安装，跳过PDF解析")
            return []

        weights = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            # 找含"权重"或"权重表"的页面
            for page in pdf.pages:
                text = page.extract_text() or ""
                if "权重" not in text and "比重" not in text:
                    continue
                # 提取表格
                tables = page.extract_tables()
                for table in tables:
                    parsed = self._parse_weight_table(table, text)
                    weights.extend(parsed)
                if weights:
                    break  # 找到权重表即可

        logger.info(f"从标准PDF解析出 {len(weights)} 条权重")
        return weights

    def _parse_weight_table(self, table: list, page_text: str) -> list[dict]:
        """解析单个权重表。

        国家职业标准权重表格式（典型）：
        | 职业功能 | 工作内容 | 四级(%) | 三级(%) | 二级(%) | 一级(%) |
        | 市场交易 | ...      | 20      | 25      | ...     | ...     |
        """
        weights = []
        if not table or len(table) < 2:
            return weights

        header = table[0]
        # 找"四级/三级"列索引
        level_cols = {}
        for i, h in enumerate(header):
            if not h:
                continue
            h_clean = h.replace(" ", "").replace("\n", "")
            if "四级" in h_clean or "中级" in h_clean:
                level_cols["four"] = i
            elif "三级" in h_clean or "高级" in h_clean:
                level_cols["three"] = i

        if not level_cols:
            return weights

        for row in table[1:]:
            if not row or not row[0]:
                continue
            module_name = row[0].replace("\n", "").strip()
            if not module_name or len(module_name) > 30:
                continue
            for level, col in level_cols.items():
                if col < len(row) and row[col]:
                    try:
                        pct = float(row[col].replace("%", "").strip())
                        if 0 < pct <= 100:
                            weights.append({
                                "module_name": module_name,
                                "level": level,
                                "weight_pct": pct,
                            })
                    except (ValueError, IndexError):
                        pass
        return weights

    def _update_exam_weights(self, weights: list[dict]):
        """把解析出的权重写入 ExamWeight 表（更新现有种子数据）。"""
        from app.db.models import ExamWeight, ExamBlueprint

        updated = 0
        bp_cache = {}
        for w in weights:
            lvl = w["level"]
            ew = self.db.query(ExamWeight).filter(
                ExamWeight.module_name == w["module_name"],
                ExamWeight.level == lvl,
            ).first()
            if ew:
                ew.weight_pct = w["weight_pct"]
                updated += 1
            else:
                # 新增需关联蓝图（blueprint_id 非空约束）；无对应蓝图则跳过孤儿权重
                if lvl not in bp_cache:
                    bp = self.db.query(ExamBlueprint).filter(ExamBlueprint.level == lvl).first()
                    bp_cache[lvl] = bp.id if bp else None
                if bp_cache[lvl] is None:
                    continue
                self.db.add(ExamWeight(
                    blueprint_id=bp_cache[lvl],
                    module_name=w["module_name"], level=lvl,
                    weight_pct=w["weight_pct"], prediction_boost=0.0,
                ))
                updated += 1
        self.db.commit()
        logger.info(f"权重表更新: {updated} 条")

    def close(self):
        self.client.close()
