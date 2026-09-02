"""知识点前置网络 L7 —— 验证种子边存在与新端点返回前置知识点。"""
from fastapi.testclient import TestClient

from app.db.models import KnowledgePoint, KnowledgePointPrerequisite
from scripts.seed_kp_prerequisites import EDGES

_KPS = [
    ("行业认知", "industry", "电力行业整体认知"),
    ("批发市场", "wholesale", "批发交易"),
    ("零售市场", "retail", "零售交易"),
    ("中长期交易", "mid_long_term", "中长期"),
    ("现货市场", "spot", "现货"),
    ("辅助服务", "ancillary", "调频备用"),
    ("绿电绿证", "green", "绿电"),
    ("结算与信用", "settlement", "结算"),
]


def _seed_kps(db_session):
    kps = {}
    for name, code, desc in _KPS:
        kp = KnowledgePoint(name=name, code=code, level=1, description=desc)
        db_session.add(kp)
        db_session.flush()
        kps[code] = kp
    db_session.commit()
    return kps


def test_seed_edges_set_matches_spec():
    # EDGES 集合对齐 L7 规范：10 条边，含 spot←mid_long_term, spot←industry 等
    assert len(EDGES) == 10
    assert ("spot", "mid_long_term") in EDGES
    assert ("spot", "industry") in EDGES
    assert ("mid_long_term", "industry") in EDGES
    assert ("ancillary", "spot") in EDGES
    assert ("retail", "wholesale") in EDGES
    assert ("settlement", "spot") in EDGES
    assert ("wholesale", "industry") in EDGES


def test_seeded_edges_exist(db_session):
    kps = _seed_kps(db_session)
    db_session.query(KnowledgePointPrerequisite).delete()
    db_session.commit()
    for kp_code, prereq_code in EDGES:
        db_session.add(KnowledgePointPrerequisite(
            kp_id=kps[kp_code].id, prereq_kp_id=kps[prereq_code].id
        ))
    db_session.commit()

    # spot 的前置应包含 mid_long_term + industry
    spot = kps["spot"]
    prereq_codes = {
        db_session.get(KnowledgePoint, row.prereq_kp_id).code
        for row in db_session.query(KnowledgePointPrerequisite).filter(
            KnowledgePointPrerequisite.kp_id == spot.id
        )
    }
    assert {"mid_long_term", "industry"}.issubset(prereq_codes)

    # 总边数 = EDGES 长度
    total = db_session.query(KnowledgePointPrerequisite).count()
    assert total == len(EDGES)


def test_prerequisites_endpoint_spot(client, db_session):
    kps = _seed_kps(db_session)
    for kp_code, prereq_code in EDGES:
        db_session.add(KnowledgePointPrerequisite(
            kp_id=kps[kp_code].id, prereq_kp_id=kps[prereq_code].id
        ))
    db_session.commit()

    resp = client.get("/api/knowledge/prerequisites/spot")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kp"]["code"] == "spot"
    prereq_codes = {p["code"] for p in body["prerequisites"]}
    assert {"mid_long_term", "industry"}.issubset(prereq_codes)
    assert len(body["prerequisites"]) >= 2
    # 描述字段存在
    assert all("description" in p for p in body["prerequisites"])


def test_prerequisites_endpoint_not_found(client):
    resp = client.get("/api/knowledge/prerequisites/no_such_kp")
    assert resp.status_code == 404
