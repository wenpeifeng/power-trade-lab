"""统一回归测试运行器 —— 一键运行所有模块的评估。

四大模块：
1. RAG检索（已有 app/ai/eval/）
2. 交易撮合（app/trade/eval_matching）
3. 考试系统（app/exam/eval_exam）
4. 知识库（app/knowledge/eval_kb）

用法：
    from app.eval.regression import run_all_evals
    report = run_all_evals(db)

规范：任何关键改动前，先跑此回归，对比基线，确保无回归。
"""
import json
import logging
import time
from datetime import datetime

from sqlalchemy.orm import Session

logger = logging.getLogger("regression")


def run_all_evals(db: Session, rag_top_k: int = 5) -> dict:
    """运行所有模块的评估，返回统一报告。

    这是回归测试入口——任何关键改动前后都应运行此函数对比。
    """
    start = time.time()
    report = {
        "run_at": datetime.now().isoformat(),
        "modules": {},
    }

    # ① RAG 检索评估
    try:
        from app.ai.eval.evaluator import run_evaluation
        rag = run_evaluation(db, mode="hybrid", top_k=rag_top_k)
        report["modules"]["rag"] = {
            "name": "RAG检索",
            "pass_rate": rag["metrics"]["recall_at_k"],
            "metrics": rag["metrics"],
            "by_type": rag["by_type"],
            "status": "pass" if rag["metrics"]["recall_at_k"] >= 0.9 else "warn",
        }
    except Exception as e:
        report["modules"]["rag"] = {"name": "RAG检索", "status": "error", "error": str(e)[:200]}

    # ② 交易撮合评估
    try:
        from app.trade.eval_matching import run_trade_eval
        trade = run_trade_eval(db)
        report["modules"]["trade"] = {
            "name": "交易撮合",
            "pass_rate": trade["pass_rate"],
            "passed": trade["passed"],
            "failed": trade["failed"],
            "status": "pass" if trade["pass_rate"] >= 0.9 else "warn",
        }
    except Exception as e:
        report["modules"]["trade"] = {"name": "交易撮合", "status": "error", "error": str(e)[:200]}

    # ③ 考试系统评估
    try:
        from app.exam.eval_exam import run_exam_eval
        exam = run_exam_eval(db)
        report["modules"]["exam"] = {
            "name": "考试系统",
            "pass_rate": exam["pass_rate"],
            "passed": exam["passed"],
            "failed": exam["failed"],
            "status": "pass" if exam["pass_rate"] >= 0.8 else "warn",
        }
    except Exception as e:
        report["modules"]["exam"] = {"name": "考试系统", "status": "error", "error": str(e)[:200]}

    # ④ 知识库评估
    try:
        from app.knowledge.eval_kb import run_kb_eval
        kb = run_kb_eval(db)
        report["modules"]["knowledge"] = {
            "name": "知识库",
            "pass_rate": kb["pass_rate"],
            "passed": kb["passed"],
            "failed": kb["failed"],
            "doc_count": kb.get("doc_count"),
            "chunk_count": kb.get("chunk_count"),
            "status": "pass" if kb["pass_rate"] >= 0.8 else "warn",
        }
    except Exception as e:
        report["modules"]["knowledge"] = {"name": "知识库", "status": "error", "error": str(e)[:200]}

    # 汇总
    durations = time.time() - start
    report["duration_sec"] = round(durations, 1)

    # 总体健康分
    pass_rates = []
    for m in report["modules"].values():
        if m.get("pass_rate") is not None:
            pass_rates.append(m["pass_rate"])
    report["overall_score"] = round(sum(pass_rates) / len(pass_rates), 3) if pass_rates else 0
    report["overall_status"] = (
        "healthy" if report["overall_score"] >= 0.9 else
        "acceptable" if report["overall_score"] >= 0.7 else "needs_attention"
    )

    return report
