"""电力交易 RAG 检索评估测试集。

设计原则：
- 每个问题有明确的"期望文档"（ground truth），基于知识库实际内容
- 覆盖多种查询类型：精确词、语义近似、省份特定、政策文号、宽泛概念
- 每个问题标注难度和查询类型，便于分维度分析

评估指标：
- Recall@K：前K个结果中是否命中期望文档（召回率）
- MRR：第一个命中结果的倒数排名（排序质量）
- Precision@K：前K个结果中有多少是相关的
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TestCase:
    """单个测试用例。"""
    query: str                    # 查询问题
    expected_doc_ids: list[int]   # 期望命中的文档ID（ground truth）
    query_type: str               # exact/semantic/province/policy_number/broad
    difficulty: str               # easy/medium/hard
    note: str = ""                # 说明


# ============ 测试集（基于知识库实际文档）============
# 文档ID对照：
#   1=全国统一电力市场实施意见  2=浙江月度交易公告  3=山西现货运行分析
#   4=辅助服务市场基本规则      5=绿色电力交易通报   7=山西现货出清结果
#   8=143号文现货试点          9=SD003网损标准     10=山西中长期细则
#   11=统一市场发展规划         12=国家顶层设计      15=分布式能源
#   20=浙江规则                21=安徽规则         22=山东规则
#   31=福建规则                39=电力行业法律法规梳理

TEST_SET = [
    # ---- 精确词查询（应靠BM25强项）----
    TestCase(
        query="143号文",
        expected_doc_ids=[8, 12],
        query_type="policy_number", difficulty="easy",
        note="文号精确匹配，BM25应明显优于dense"
    ),
    TestCase(
        query="SD003标准",
        expected_doc_ids=[9],
        query_type="policy_number", difficulty="easy",
        note="标准代号精确匹配"
    ),
    TestCase(
        query="华北区域电力市场运营规则",
        expected_doc_ids=[6, 12],
        query_type="exact", difficulty="easy",
        note="文档标题关键词精确匹配"
    ),

    # ---- 省份特定查询 ----
    TestCase(
        query="浙江电力现货市场结算规则",
        expected_doc_ids=[2, 20],
        query_type="province", difficulty="medium",
        note="省份+特定主题，需理解'结算规则'语义"
    ),
    TestCase(
        query="山东电力市场",
        expected_doc_ids=[22, 10],
        query_type="province", difficulty="easy",
        note="省份关键词，应命中山东规则文档"
    ),
    TestCase(
        query="安徽省电力交易",
        expected_doc_ids=[21],
        query_type="province", difficulty="easy",
    ),
    TestCase(
        query="福建电力市场规则",
        expected_doc_ids=[31],
        query_type="province", difficulty="medium",
    ),

    # ---- 语义近似查询（应靠dense强项）----
    TestCase(
        query="电价怎么计算",
        expected_doc_ids=[9, 11, 39],
        query_type="semantic", difficulty="hard",
        note="无精确词，需语义理解匹配到结算/电价相关文档"
    ),
    TestCase(
        query="绿电交易怎么参与",
        expected_doc_ids=[5, 11, 39],
        query_type="semantic", difficulty="medium",
        note="口语化提问，需语义匹配绿色电力交易"
    ),
    TestCase(
        query="新能源发电并网",
        expected_doc_ids=[14, 15, 11],
        query_type="semantic", difficulty="hard",
        note="宽泛概念，需匹配综合能源/分布式相关文档"
    ),
    TestCase(
        query="电力市场建设试点",
        expected_doc_ids=[8, 12, 11],
        query_type="semantic", difficulty="medium",
        note="需语义匹配到现货市场建设相关政策"
    ),

    # ---- 宽泛/概念性查询 ----
    TestCase(
        query="什么是节点边际电价",
        expected_doc_ids=[8, 7, 3],
        query_type="broad", difficulty="hard",
        note="概念性查询，LMP相关文档"
    ),
    TestCase(
        query="电力辅助服务",
        expected_doc_ids=[4, 11, 39],
        query_type="broad", difficulty="medium",
        note="辅助服务市场概念"
    ),
    TestCase(
        query="全国统一电力市场",
        expected_doc_ids=[1, 11, 12],
        query_type="broad", difficulty="easy",
    ),
    TestCase(
        query="分布式光伏参与市场",
        expected_doc_ids=[15, 39],
        query_type="semantic", difficulty="hard",
        note="需理解'分布式光伏'匹配到分布式能源文档"
    ),
    TestCase(
        query="中长期交易",
        expected_doc_ids=[10, 2, 11],
        query_type="broad", difficulty="easy",
    ),
    TestCase(
        query="电力现货市场出清",
        expected_doc_ids=[7, 3, 8],
        query_type="exact", difficulty="medium",
        note="出清相关，应命中山西出清结果"
    ),
    TestCase(
        query="偏差考核结算",
        expected_doc_ids=[10, 11, 39],
        query_type="semantic", difficulty="hard",
    ),
    TestCase(
        query="储能参与电力市场",
        expected_doc_ids=[14, 15, 11],
        query_type="semantic", difficulty="hard",
    ),
    TestCase(
        query="售电公司",
        expected_doc_ids=[15, 11, 39],
        query_type="broad", difficulty="medium",
    ),
]


def get_test_set() -> list[TestCase]:
    """获取完整测试集。"""
    return TEST_SET


def get_test_summary() -> dict:
    """测试集统计。"""
    from collections import Counter
    types = Counter(tc.query_type for tc in TEST_SET)
    diffs = Counter(tc.difficulty for tc in TEST_SET)
    return {
        "total": len(TEST_SET),
        "by_type": dict(types),
        "by_difficulty": dict(diffs),
    }
