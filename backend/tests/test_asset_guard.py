"""数据资产中心权限边界：读放开给登录用户，写/审核保留 admin。"""
import pytest

BASE = "/api/asset"


def test_stats_requires_login(client, db_session):
    r = client.get(f"{BASE}/stats")
    assert r.status_code in (401, 403)


def test_stats_ok_for_normal_user(auth_client_normal):
    r = auth_client_normal.get(f"{BASE}/stats")
    assert r.status_code == 200


def test_timeline_ok_for_normal_user(auth_client_normal):
    r = auth_client_normal.get(f"{BASE}/timeline")
    assert r.status_code == 200


def test_review_forbidden_for_normal_user(auth_client_normal):
    r = auth_client_normal.post(f"{BASE}/review", json={"doc_id": 1, "action": "approve"})
    assert r.status_code == 403


def test_crawler_run_forbidden_for_normal_user(auth_client_normal):
    r = auth_client_normal.post(f"{BASE}/crawler/run", json={"crawler_type": "policy"})
    assert r.status_code == 403


def test_review_ok_for_admin(auth_client_admin):
    r = auth_client_admin.post(f"{BASE}/review", json={"doc_id": 1, "action": "approve"})
    assert r.status_code in (200, 400, 404)  # 非 403 即通过权限
