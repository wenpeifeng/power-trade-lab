"""Item 1 回归：wrong_answers (user_id, question_id) 唯一约束 + 并发兜底。

覆盖三件事：
1. 唯一约束真实落地——直接重复 INSERT 同一 user+question 必然 IntegrityError。
2. 正常路径——通过 API 二次答错同一题走 UPDATE，最终恰好一行、无 500。
3. 并发滑路径——模拟 query-before-insert 与 commit 之间的竞争窗口：
   预先 commit 一行，再让请求 session 的首次 WrongAnswer 查询返回 None
   （强迫走 INSERT 分支），commit 撞唯一约束 → 走 except IntegrityError
   回退 UPDATE，仍恰好一行、无 500。

conftest 的隔离库经 Base.metadata.create_all 建表，WrongAnswer 模型上的
__table_args__ UniqueConstraint 会随建表自动落地，故测试库即带约束。
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.auth import hash_password
from app.db.database import get_db
from app.db.models import Question, User, WrongAnswer
from app.main import app
from tests.conftest import _TestingSessionLocal, _test_engine  # noqa: E402

# 复用 conftest 的隔离测试引擎与 sessionmaker


def _seed_kp_and_question(db) -> tuple[int, Question]:
    """建一个知识点 + 一道单选题，返回 (user_id_for_asserts, question)。

    user 由 auth_client_normal 夹具创建（id 由 db 自增），这里只建题。
    """
    from app.db.models import KnowledgePoint

    kp = KnowledgePoint(name="现货", code="spot", level=1)
    db.add(kp)
    db.commit()
    db.refresh(kp)
    options = json.dumps(
        [
            {"key": "A", "text": "对", "is_correct": True},
            {"key": "B", "text": "错", "is_correct": False},
        ],
        ensure_ascii=False,
    )
    q = Question(
        type="single",
        stem="现货出清价由谁决定？",
        options=options,
        answer="A",
        analysis="解析",
        difficulty=2,
        knowledge_point_id=kp.id,
        is_active=True,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


def _current_user_id(db) -> int:
    """conftest 的 auth_client_normal 夹具会创建名为 guard_normal 的用户；
    这里在测试库中查其 id。"""
    u = db.query(User).filter_by(username="guard_normal").first()
    assert u is not None, "auth_client_normal 夹具应已创建 guard_normal 用户"
    return u.id


# ============ 1. 唯一约束真实落地 ============

def test_unique_constraint_blocks_duplicate(db_session, auth_client_normal):
    """直接对同一 user+question 重复 INSERT WrongAnswer 必然 IntegrityError。"""
    q = _seed_kp_and_question(db_session)
    uid = _current_user_id(db_session)

    db_session.add(
        WrongAnswer(user_id=uid, question_id=q.id, user_answer="B", reviewed=False)
    )
    db_session.commit()

    db_session.add(
        WrongAnswer(user_id=uid, question_id=q.id, user_answer="C", reviewed=False)
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 约束在库层面也可见
    from sqlalchemy import inspect

    inspector = inspect(_test_engine)
    indexes = inspector.get_indexes("wrong_answers")
    uniques = inspector.get_unique_constraints("wrong_answers")
    assert any(
        set(u["column_names"]) == {"user_id", "question_id"} for u in uniques
    ), f"应存在 (user_id, question_id) 唯一约束，实际: {uniques}"
    # 任何形式的唯一索引也接受（表级 CONSTRAINT 落地为自动唯一索引）
    has_unique = any(
        ix.get("unique") for ix in indexes
    ) or any(set(u["column_names"]) == {"user_id", "question_id"} for u in uniques)
    assert has_unique


# ============ 2. 正常路径：二次答错走 UPDATE，恰好一行 ============

def test_second_wrong_answer_updates_not_duplicates(auth_client_normal, db_session):
    """POST /api/learn/answer 二次答错 → 仍是 1 行，user_answer 刷新，无 500。"""
    q = _seed_kp_and_question(db_session)

    for ans in ("B", "C"):
        r = auth_client_normal.post(
            "/api/learn/answer",
            json={"question_id": q.id, "user_answer": ans},
        )
        assert r.status_code == 200, r.text
        assert r.json()["correct"] is False

    db_session.commit()
    wrongs = db_session.query(WrongAnswer).filter_by(question_id=q.id).all()
    assert len(wrongs) == 1
    assert wrongs[0].user_answer == "C"
    assert wrongs[0].reviewed is False


# ============ 3. 并发滑：IntegrityError 回退 UPDATE，无 500 ============

class _RaceSession(Session):
    """模拟 query-before-insert 与 commit 间的竞争窗口。

    首次对 wrong_answers 的 SELECT 返回空（假装没看到已存在的行），强迫
    submit_answer 走 INSERT 分支；commit 撞唯一约束抛 IntegrityError；
    except 块重新查询（这次返回真实行）并 UPDATE。
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._intercept_next_wrong_select = True

    @staticmethod
    def _is_wrong_answer_select(statement) -> bool:
        try:
            sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        except Exception:
            return False
        return "wrong_answers" in sql

    def execute(self, statement, *a, **kw):
        if (
            self._intercept_next_wrong_select
            and self._is_wrong_answer_select(statement)
        ):
            self._intercept_next_wrong_select = False
            # 返回一个空结果，使 .scalars().first() → None
            class _Empty:
                def scalars(self):
                    return self

                def first(self):
                    return None

                def all(self):
                    return []

            return _Empty()
        return super().execute(statement, *a, **kw)


def test_race_window_integrity_fallback_updates_existing(auth_client_normal, db_session):
    """预先 commit 一行错题，再用 _RaceSession 让请求首次查询漏看 → INSERT 撞约束
    → except IntegrityError 回退 UPDATE。最终恰好一行、user_answer 为最新、无 500。"""
    q = _seed_kp_and_question(db_session)
    uid = _current_user_id(db_session)

    # 预先 commit 一行（模拟另一并发请求先插入）
    db_session.add(
        WrongAnswer(user_id=uid, question_id=q.id, user_answer="X", reviewed=False)
    )
    db_session.commit()

    race_session = _RaceSession(bind=_test_engine)

    def _override():
        try:
            yield race_session
        finally:
            race_session.close()

    app.dependency_overrides[get_db] = _override
    try:
        r = auth_client_normal.post(
            "/api/learn/answer",
            json={"question_id": q.id, "user_answer": "Z"},
        )
    finally:
        # 恢复 conftest 的默认 override
        from tests.conftest import _override_get_db

        app.dependency_overrides[get_db] = _override_get_db

    assert r.status_code == 200, r.text
    assert r.json()["correct"] is False  # user_answer Z != 正确答案 A

    db_session.commit()  # 让外层 session 看到 race_session 提交的变更
    wrongs = db_session.query(WrongAnswer).filter_by(question_id=q.id).all()
    assert len(wrongs) == 1, "回退 UPDATE 后应仍恰好一行"
    assert wrongs[0].user_answer == "Z"  # 已 UPDATE 为最新作答
    assert wrongs[0].reviewed is False
