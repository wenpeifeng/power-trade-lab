"""知识库质量评估框架。

验证知识库的4个关键维度：
1. 索引完整性：有正文的文档都应该有分块向量
2. 分块质量：无超短块(<20字)、无超长块(>800字)
3. 去重正确性：dedup_key 无冲突
4. 分类覆盖率：文档有category_code的比例

用法：
    from app.knowledge.eval_kb import run_kb_eval
    report = run_kb_eval(db)
"""
import json
import logging
from collections import Counter

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger("kb_eval")


def run_kb_eval(db: Session) -> dict:
    """运行知识库完整质量评估。"""
    from app.db.models import KnowledgeDoc, DocChunk

    results = []
    passed = 0
    failed = 0

    # ============ 1. 索引完整性 ============
    total_docs = db.query(func.count(KnowledgeDoc.id)).scalar() or 0
    docs_with_content = db.query(func.count(KnowledgeDoc.id)).filter(
        func.length(KnowledgeDoc.content) > 20
    ).scalar() or 0
    docs_with_chunks = db.query(func.count(func.distinct(DocChunk.doc_id))).scalar() or 0

    # 有内容的文档应该大部分有分块（允许少量失败）
    coverage = docs_with_chunks / max(docs_with_content, 1)
    coverage_ok = coverage >= 0.8
    results.append({
        "name": "向量索引完整性",
        "passed": coverage_ok,
        "detail": f"有内容文档{docs_with_content}篇, 已索引{docs_with_chunks}篇, 覆盖率={coverage:.1%}",
    })
    if coverage_ok:
        passed += 1
    else:
        failed += 1

    # ============ 2. 分块质量 ============
    chunks = db.query(DocChunk).all()
    chunk_lens = [len(c.text or "") for c in chunks]
    if chunk_lens:
        too_short = sum(1 for l in chunk_lens if l < 20)
        too_long = sum(1 for l in chunk_lens if l > 800)
        avg_len = sum(chunk_lens) / len(chunk_lens)
        quality_ok = too_short == 0  # 不允许超短块
        results.append({
            "name": "分块质量(无噪声块)",
            "passed": quality_ok,
            "detail": f"共{len(chunks)}块, 平均{avg_len:.0f}字, 超短(<20字)={too_short}, 超长(>800字)={too_long}",
        })
        if quality_ok: passed += 1
        else: failed += 1
    else:
        results.append({"name": "分块质量", "passed": False, "detail": "无分块数据"})
        failed += 1

    # ============ 3. 去重正确性 ============
    total_keys = db.query(func.count(KnowledgeDoc.id)).scalar() or 0
    unique_keys = db.query(func.count(func.distinct(KnowledgeDoc.dedup_key))).scalar() or 0
    dedup_ok = total_keys == unique_keys
    results.append({
        "name": "去重正确性(dedup_key唯一)",
        "passed": dedup_ok,
        "detail": f"总文档{total_keys}, 唯一key{unique_keys}",
    })
    if dedup_ok: passed += 1
    else: failed += 1

    # ============ 4. 分类覆盖率 ============
    docs_with_cat = db.query(func.count(KnowledgeDoc.id)).filter(
        KnowledgeDoc.category_code.isnot(None)
    ).scalar() or 0
    cat_coverage = docs_with_cat / max(total_docs, 1)
    cat_ok = cat_coverage >= 0.7
    results.append({
        "name": "分类覆盖率",
        "passed": cat_ok,
        "detail": f"{docs_with_cat}/{total_docs} = {cat_coverage:.1%}",
    })
    if cat_ok: passed += 1
    else: failed += 1

    # ============ 5. 向量维度一致性 ============
    dim_set = set()
    for c in chunks[:50]:  # 抽样50个
        try:
            emb = json.loads(c.embedding)
            dim_set.add(len(emb))
        except Exception:
            pass
    dim_ok = len(dim_set) == 1  # 所有向量维度应该一致
    results.append({
        "name": "向量维度一致性",
        "passed": dim_ok,
        "detail": f"维度集合={dim_set} (应只有1个值)",
    })
    if dim_ok: passed += 1
    else: failed += 1

    total = len(results)
    return {
        "module": "知识库",
        "total_cases": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total, 3) if total else 0,
        "doc_count": total_docs,
        "chunk_count": len(chunks),
        "details": results,
    }
