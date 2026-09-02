"""L10 —— knowledge_docs 回填 knowledge_point_id 的脚本与映射测试。"""
from app.db.models import KnowledgeDoc, KnowledgePoint
from scripts.backfill_doc_kp import (
    CATEGORY_TO_KP,
    keyword_fallback_kp,
    map_category_to_kp,
    backfill,
)


# ---- 映射断言：核心分流 ----
def test_category_to_kp_key_codes():
    assert map_category_to_kp("311") == "mid_long_term"
    assert map_category_to_kp("312") == "spot"
    assert map_category_to_kp("32") == "ancillary"
    assert map_category_to_kp("351") == "green"
    assert map_category_to_kp("5") == "settlement"
    assert map_category_to_kp("51") == "settlement"
    assert map_category_to_kp("7") == "wholesale"
    assert map_category_to_kp("71") == "wholesale"
    assert map_category_to_kp("36") == "ancillary"
    assert map_category_to_kp("37") == "mid_long_term"
    assert map_category_to_kp("313") == "spot"  # 平衡市场 → 现货
    assert map_category_to_kp("33") == "settlement"
    assert map_category_to_kp("64") == "retail"


def test_category_to_kp_longest_prefix_and_null():
    # 最长前缀：'312' 命中 '312' 而非 '3' 兜底
    assert map_category_to_kp("312") == "spot"
    # 未知子节按前缀回退：'08' 命中 '0'
    assert map_category_to_kp("08") == "industry"
    # 未定义的纯未知码无前缀命中 → None
    assert map_category_to_kp(None) is None
    assert map_category_to_kp("") is None


def test_category_to_kp_table_has_no_none_values():
    # 防止误把 None 写进映射表导致选择 None KP
    assert all(isinstance(v, str) and v for v in CATEGORY_TO_KP.values())


def test_keyword_fallback():
    assert keyword_fallback_kp("现货市场", "日前出清 LMP") == "spot"
    assert keyword_fallback_kp("绿电交易", "") == "green"
    assert keyword_fallback_kp("售电公司零售", "") == "retail"
    assert keyword_fallback_kp("", "无任何关键词命中 xyz") is None


def _seed_kps(db_session):
    kps = {}
    for name, code in [
        ("行业认知", "industry"), ("批发市场", "wholesale"),
        ("零售市场", "retail"), ("中长期交易", "mid_long_term"),
        ("现货市场", "spot"), ("辅助服务", "ancillary"),
        ("绿电绿证", "green"), ("结算与信用", "settlement"),
    ]:
        kp = KnowledgePoint(name=name, code=code, level=1)
        db_session.add(kp)
    db_session.commit()
    for kp in db_session.query(KnowledgePoint).all():
        kps[kp.code] = kp.id
    return kps


def test_backfill_fills_null_doc(db_session):
    """在种子测试库上跑回填：NULL 文档应被填上 knowledge_point_id。"""
    kps = _seed_kps(db_session)
    # 一篇 NULL category 的 doc，靠 classifier/关键词回退
    doc_null_cat = KnowledgeDoc(
        title="关于完善现货市场日前出清机制的通知",
        content="现货市场日前出清 LMP 节点电价机制",
        doc_type="national_policy",
        source="test",
        category_code=None,
        review_status="approved",
        knowledge_point_id=None,
    )
    # 一篇有 category_code 的 doc
    doc_with_cat = KnowledgeDoc(
        title="中长期交易规则",
        content="中长期市场年度月度双边协商",
        doc_type="regulation",
        source="test",
        category_code="311",
        review_status="approved",
        knowledge_point_id=None,
    )
    # 一篇已链接的 approved doc —— 必须不被触碰
    linked_doc = KnowledgeDoc(
        title="已链接文档",
        content="...",
        doc_type="industry_news",
        source="test",
        review_status="approved",
        knowledge_point_id=kps["industry"],
    )
    # 一篇 pending 文档 —— 必须不被处理
    pending_doc = KnowledgeDoc(
        title="待审文档",
        content="现货",
        doc_type="industry_news",
        source="test",
        review_status="pending",
        knowledge_point_id=None,
    )
    db_session.add_all([doc_null_cat, doc_with_cat, linked_doc, pending_doc])
    db_session.commit()

    stats = backfill(db_session, apply=True)
    assert stats["mode"] == "applied"
    # total=4 approved=3 (pending 不计)
    assert stats["total_approved"] == 3
    assert stats["was_linked"] == 1
    assert stats["was_orphan"] == 2
    assert stats["filled"] == 2
    assert stats["now_linked"] == 3
    assert stats["still_orphan"] == 0

    db_session.refresh(doc_null_cat)
    db_session.refresh(doc_with_cat)
    db_session.refresh(linked_doc)
    db_session.refresh(pending_doc)

    assert doc_null_cat.knowledge_point_id == kps["spot"]
    assert doc_with_cat.knowledge_point_id == kps["mid_long_term"]
    # 已有值不被覆盖
    assert linked_doc.knowledge_point_id == kps["industry"]
    # pending 不处理
    assert pending_doc.knowledge_point_id is None


def test_backfill_idempotent(db_session):
    """二次运行：已填的不再动，剩余 NULL 继续尝试。"""
    _seed_kps(db_session)
    doc = KnowledgeDoc(
        title="辅助服务调频市场",
        content="调频备用 AGC",
        doc_type="regulation",
        source="test",
        category_code="32",
        review_status="approved",
        knowledge_point_id=None,
    )
    db_session.add(doc)
    db_session.commit()

    first = backfill(db_session, apply=True)
    assert first["filled"] == 1
    db_session.refresh(doc)
    assert doc.knowledge_point_id is not None

    # 二次：已无 orphan，filled=0
    second = backfill(db_session, apply=True)
    assert second["filled"] == 0
    assert second["was_orphan"] == 0
    assert second["still_orphan"] == 0
