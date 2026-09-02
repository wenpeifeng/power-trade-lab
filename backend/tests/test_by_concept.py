"""D2：按概念标题召回相关原文（/knowledge/by-concept）。

钉住「概念级原文溯源」闭环：前端 KnowledgeBook 在进阶/专家级为每个概念展示
2-3 篇真实文档。本测试验证后端按概念标题做 ILIKE 召回、kp 加权排序、空结果
隐藏、source_url 补字段。
"""
from app.db.models import KnowledgeDoc, KnowledgePoint


def _seed_doc(db, title, *, kp_id=None, content="", ai_summary="", source_url=None,
              publish_date="2026-07-01", doc_type="regulation", source="发改委",
              review_status="approved"):
    doc = KnowledgeDoc(
        title=title, doc_type=doc_type, source=source, source_url=source_url,
        content=content, ai_summary=ai_summary, knowledge_point_id=kp_id,
        publish_date=publish_date, review_status=review_status,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _kp(db, code="mid_long_term", name="中长期市场"):
    kp = KnowledgePoint(code=code, name=name)
    db.add(kp)
    db.commit()
    db.refresh(kp)
    return kp


def test_by_concept_returns_doc_whose_title_contains_concept(client, db_session):
    """title=双边协商 命中标题含「双边协商」的文档。"""
    _seed_doc(db_session, "某省双边协商交易实施细则", ai_summary="规范双边协商流程")
    _seed_doc(db_session, "无关行业新闻", ai_summary="新能源装机增长")

    res = client.get("/api/knowledge/by-concept", params={"title": "双边协商", "limit": 3})
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 1
    items = body["items"]
    assert "双边协商" in items[0]["title"]
    # source_url 字段补齐（_doc_brief 不含）
    assert "source_url" in items[0]


def test_by_concept_kp_boosts_matching_doc(client, db_session):
    """给出 kp 时，命中该 knowledge_point_id 的文档排到前面。"""
    kp = _kp(db_session)
    # 命中 KP 但日期更早 —— 应排第一（加权优先于日期）
    a = _seed_doc(db_session, "双边协商合同备案要点", kp_id=kp.id, publish_date="2026-01-01")
    # 无 KP 但日期更新 —— 排第二
    b = _seed_doc(db_session, "双边协商价不公开的原因", kp_id=None, publish_date="2026-07-01")

    res = client.get("/api/knowledge/by-concept", params={"title": "双边协商", "kp": "mid_long_term"})
    assert res.status_code == 200
    items = res.json()["items"]
    assert items[0]["id"] == a.id
    assert items[1]["id"] == b.id


def test_by_concept_filters_only_approved(client, db_session):
    """pending 文档不可见（与 /knowledge/docs 同可信层）。"""
    _seed_doc(db_session, "双边协商待审稿", review_status="pending")
    res = client.get("/api/knowledge/by-concept", params={"title": "双边协商"})
    assert res.status_code == 200
    assert res.json()["count"] == 0


def test_by_concept_empty_when_no_match(client, db_session):
    """无命中时返回空列表（前端据此隐藏整个区块）。"""
    _seed_doc(db_session, "完全无关的标题")
    res = client.get("/api/knowledge/by-concept", params={"title": "双边协商"})
    assert res.status_code == 200
    assert res.json()["count"] == 0
    assert res.json()["items"] == []


def test_by_concept_kp_code_unresolvable_does_not_crash(client, db_session):
    """kp 给了但 DB 无该 code —— 不崩，仍按标题召回（无加权）。"""
    _seed_doc(db_session, "双边协商案例")
    res = client.get("/api/knowledge/by-concept", params={"title": "双边协商", "kp": "ghost_code"})
    assert res.status_code == 200
    assert res.json()["count"] == 1


def test_by_concept_respects_limit(client, db_session):
    """limit 截断。"""
    for i in range(5):
        _seed_doc(db_session, f"双边协商案例第{i}篇", publish_date=f"2026-0{i+1}-01")
    res = client.get("/api/knowledge/by-concept", params={"title": "双边协商", "limit": 2})
    assert res.json()["count"] == 2
