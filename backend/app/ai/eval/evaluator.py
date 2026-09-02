"""RAG 检索质量评估引擎。

评估流程：
1. 用测试集的每个 query 调用 retrieve()
2. 对比返回结果 vs 期望文档（ground truth）
3. 计算 Recall@K / MRR / Precision@K
4. 按查询类型分维度统计
5. 输出可对比的评估报告

用法：
    from app.ai.eval.evaluator import run_evaluation
    report = run_evaluation(mode='hybrid', top_k=5)
"""
import json
import logging
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("rag_eval")


def run_evaluation(
    db: Session,
    mode: str = "hybrid",
    top_k: int = 5,
) -> dict:
    """对指定检索模式运行完整评估。

    返回评估报告 dict。
    """
    from app.knowledge.embedding import retrieve
    from app.ai.eval.testset import get_test_set

    test_cases = get_test_set()
    results = []

    for tc in test_cases:
        # 调检索
        try:
            hits = retrieve(db, tc.query, top_k=top_k, mode=mode)
        except Exception as e:
            logger.warning(f"查询失败 '{tc.query}': {e}")
            hits = []

        retrieved_ids = [h.get("doc_id") for h in hits if h.get("doc_id")]
        expected_set = set(tc.expected_doc_ids)

        # 计算指标
        hit_ranks = []  # 命中的排名
        for rank, doc_id in enumerate(retrieved_ids, 1):
            if doc_id in expected_set:
                hit_ranks.append(rank)

        recall_at_k = 1.0 if hit_ranks else 0.0  # Recall@K: 是否至少命中1个
        mrr = 1.0 / hit_ranks[0] if hit_ranks else 0.0  # MRR
        precision_at_k = len(hit_ranks) / min(len(retrieved_ids), top_k) if retrieved_ids else 0.0

        results.append({
            "query": tc.query,
            "query_type": tc.query_type,
            "difficulty": tc.difficulty,
            "expected_ids": tc.expected_doc_ids,
            "retrieved_ids": retrieved_ids,
            "hit_ranks": hit_ranks,
            "recall_at_k": recall_at_k,
            "mrr": mrr,
            "precision_at_k": round(precision_at_k, 3),
            "note": tc.note,
        })

    # 汇总
    n = len(results)
    avg_recall = sum(r["recall_at_k"] for r in results) / n
    avg_mrr = sum(r["mrr"] for r in results) / n
    avg_precision = sum(r["precision_at_k"] for r in results) / n

    # 按查询类型分维度
    by_type = _group_stats(results, "query_type")
    by_difficulty = _group_stats(results, "difficulty")

    return {
        "mode": mode,
        "top_k": top_k,
        "total_queries": n,
        "metrics": {
            "recall_at_k": round(avg_recall, 3),
            "mrr": round(avg_mrr, 3),
            "precision_at_k": round(avg_precision, 3),
        },
        "by_type": by_type,
        "by_difficulty": by_difficulty,
        "details": results,
    }


def _group_stats(results: list, key: str) -> dict:
    """按指定维度分组统计。"""
    groups = defaultdict(list)
    for r in results:
        groups[r[key]].append(r)

    stats = {}
    for gname, items in groups.items():
        n = len(items)
        stats[gname] = {
            "count": n,
            "recall_at_k": round(sum(r["recall_at_k"] for r in items) / n, 3),
            "mrr": round(sum(r["mrr"] for r in items) / n, 3),
            "precision_at_k": round(sum(r["precision_at_k"] for r in items) / n, 3),
        }
    return stats


def compare_modes(db: Session, top_k: int = 5) -> dict:
    """对比三种检索模式的评估结果。"""
    modes = ["dense", "sparse", "hybrid"]
    comparison = {}
    for mode in modes:
        logger.info(f"评估模式: {mode}")
        comparison[mode] = run_evaluation(db, mode=mode, top_k=top_k)

    # 汇总对比表
    summary = {
        mode: {
            "recall": comparison[mode]["metrics"]["recall_at_k"],
            "mrr": comparison[mode]["metrics"]["mrr"],
            "precision": comparison[mode]["metrics"]["precision_at_k"],
        }
        for mode in modes
    }

    # 找出每种查询类型的最优模式
    type_winners = {}
    all_types = set()
    for mode in modes:
        all_types.update(comparison[mode]["by_type"].keys())
    for qt in all_types:
        best_mode = None
        best_score = -1
        for mode in modes:
            if qt in comparison[mode]["by_type"]:
                score = comparison[mode]["by_type"][qt]["recall_at_k"]
                if score > best_score:
                    best_score = score
                    best_mode = mode
        type_winners[qt] = {"best_mode": best_mode, "recall": best_score}

    return {
        "summary": summary,
        "type_winners": type_winners,
        "details": comparison,
    }
