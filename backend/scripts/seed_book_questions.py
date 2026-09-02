#!/usr/bin/env python3
"""幂等灌入教材章节 quiz_json 到共享 questions 表（source_type='book'）。

把 learning_book_chapters.quiz_json（每章 3 题左右）解析灌入真实题库，使其：
- 进入共享组卷池（/learn/quiz 自动可选）
- 答错时进错题本（learn/router 的 submit_answer 流程写入）

幂等：按 stem_hash 判重，已存在则跳过；不修改既有行。
分类映射：classifier.auto_classify(title+stem) → category_code →
CATEGORY_TO_KP 映射 → knowledge_point_id；无法解析则留 NULL（宁缺毋错）。

调用：python -m scripts.seed_book_questions
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select, func  # noqa: E402

from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import KnowledgePoint, LearningBookChapter, Question  # noqa: E402
from app.knowledge.classifier import auto_classify  # noqa: E402

logger = logging.getLogger("seed_book_questions")

# category_code(分类树) → knowledge_point code 映射。
# 保守策略：能合理归类的才映射，否则留 NULL（better null than wrong）。
# 分类编码沿用 app/knowledge/classifier.py 的 CATEGORY_KEYWORDS。
CATEGORY_TO_KP: dict[str, str] = {
    # 总览 → 行业认知
    "01": "industry", "02": "industry", "03": "industry", "04": "industry",
    # 政策法规 → 行业认知（无专门法律 KP）
    "11": "industry", "12": "industry",
    "131": "industry", "132": "industry",
    "133": "green",      # 新能源/消纳/可再生能源 → 绿电
    "134": "green", "135": "industry",
    "14": "industry", "15": "industry", "16": "industry",
    # 市场主体
    "21": "wholesale",  # 发电企业
    "22": "wholesale",  # 电网企业
    "23": "retail",     # 售电公司
    "24": "retail",     # 电力用户
    "25": "retail",     # 新型主体
    "26": "industry",   # 运营机构
    # 交易品种
    "311": "mid_long_term",
    "312": "spot", "313": "spot",
    "32": "ancillary",
    "33": "wholesale",  # 容量市场
    "34": "wholesale",  # 输电权
    "35": "green",
    "36": "retail",     # 需求响应
    "37": "wholesale",  # 发电权
    "38": "wholesale",  # 期货
    # 产业链 → 行业认知
    "41": "industry", "42": "industry", "43": "industry",
    "44": "industry", "45": "industry", "46": "industry",
    # 结算
    "55": "settlement",
    # 新兴（保守）
    "61": "ancillary",  # 储能
    "62": "retail",     # 虚拟电厂/负荷聚合
    "64": "retail",     # 分布式交易
    "65": "green",      # 碳市场
    "67": "green",      # 氢能
}


def _stem_hash(stem: str) -> str:
    return hashlib.sha256(stem.strip().encode("utf-8")).hexdigest()


def _normalize_judge_answer(answer: str | None, options: list[dict]) -> str:
    """判断题答案归一化：书里多见 answer='A'/'B' 直接返回；
    若出现 '对'/'错'/'正确'/'错误' 这种非字母答案，映射到对应 option 的 key。
    """
    if not answer:
        return answer or ""
    a = answer.strip()
    # 已是 ASCII 字母键（A/B/...）直接返回（注意中文 isalpha() 亦为 True，须判 isascii）
    if a and a[0].isascii() and a[0].isalpha():
        return a
    # 对/错 → 找到 text 含该字的 option key
    mapping = {"对": ["对", "正确"], "错": ["错", "错误"], "正确": ["正确", "对"], "错误": ["错误", "错"]}
    targets = mapping.get(a)
    if targets:
        for opt in options:
            text = opt.get("text", "") or ""
            if any(t in text for t in targets):
                return opt.get("key", "")
    return a


def _build_options(item: dict, normalized_answer: str) -> str:
    """构造 options JSON：[{key, text, is_correct}]，is_correct = key 在 answer 中。"""
    options = item.get("options") or []
    out = []
    for opt in options:
        key = opt.get("key", "")
        out.append(
            {
                "key": key,
                "text": opt.get("text", ""),
                "is_correct": bool(key) and key in normalized_answer,
            }
        )
    return json.dumps(out, ensure_ascii=False)


def _resolve_kp_id(category_code: str | None, kp_by_code: dict[str, int]) -> int | None:
    """分类编码 → 知识点 id：先精确，再逐级缩短前缀，找不到返回 None。"""
    if not category_code:
        return None
    code = category_code
    while code:
        kp_code = CATEGORY_TO_KP.get(code)
        if kp_code:
            kp_id = kp_by_code.get(kp_code)
            if kp_id:
                return kp_id
        # 缩短前缀继续试（如 312 → 31 → 3）
        code = code[:-1]
    return None


def seed_book_questions(db) -> dict:
    """核心灌入逻辑（接收外部 session，便于测试与复用）。

    返回 {seeded, skipped, kp_breakdown, parse_errors}。
    """
    # 预取全部知识点 code→id
    kp_by_code = {
        kp.code: kp.id
        for kp in db.execute(select(KnowledgePoint)).scalars().all()
        if kp.code
    }

    chapters = db.execute(select(LearningBookChapter)).scalars().all()
    seeded = 0
    skipped = 0
    parse_errors = 0
    kp_breakdown: dict[str, int] = {}  # kp_code 或 "(null)" → 计数

    for ch in chapters:
        raw = ch.quiz_json
        if not raw or not raw.strip() or raw.strip() in ("[]", "null"):
            continue
        try:
            quiz = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            parse_errors += 1
            logger.warning("chapter %s quiz_json 解析失败，跳过", ch.id)
            continue
        if not isinstance(quiz, list):
            parse_errors += 1
            logger.warning("chapter %s quiz_json 非数组，跳过", ch.id)
            continue

        title = ch.title or ""
        for item in quiz:
            if not isinstance(item, dict):
                continue
            stem = (item.get("stem") or "").strip()
            if not stem:
                continue
            qtype = item.get("type")
            if qtype not in ("single", "multiple", "judge"):
                logger.warning("chapter %s 未知题型 %r，跳过", ch.id, qtype)
                continue

            sh = _stem_hash(stem)
            exists = db.execute(
                select(Question).where(Question.stem_hash == sh)
            ).scalars().first()
            if exists:
                skipped += 1
                continue

            raw_answer = item.get("answer") or ""
            normalized_answer = (
                _normalize_judge_answer(raw_answer, item.get("options") or [])
                if qtype == "judge"
                else raw_answer
            )
            options_json = _build_options(item, normalized_answer)

            # 分类推断 KP
            classification = auto_classify(title + " " + stem, stem)
            cat_code = classification.get("category_code") if classification else None
            kp_id = _resolve_kp_id(cat_code, kp_by_code)

            db.add(
                Question(
                    type=qtype,
                    stem=stem,
                    options=options_json,
                    answer=normalized_answer,
                    analysis=item.get("analysis"),
                    knowledge_point_id=kp_id,
                    source=f"book:{ch.book_id}:{ch.id}",
                    source_type="book",
                    is_ai_generated=True,
                    is_active=True,
                    difficulty=2,
                    stem_hash=sh,
                )
            )
            seeded += 1
            # 统计 KP 分布（反查 kp_code）
            kp_code_label = "(null)"
            if kp_id:
                for code, kid in kp_by_code.items():
                    if kid == kp_id:
                        kp_code_label = code
                        break
            kp_breakdown[kp_code_label] = kp_breakdown.get(kp_code_label, 0) + 1

    db.commit()
    return {
        "seeded": seeded,
        "skipped": skipped,
        "kp_breakdown": kp_breakdown,
        "parse_errors": parse_errors,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    init_db()
    db = SessionLocal()
    before = db.scalar(select(func.count(Question.id)))
    try:
        result = seed_book_questions(db)
    finally:
        db.close()

    print(f"questions before: {before}")
    print(f"seeded {result['seeded']} book questions, skipped {result['skipped']} (already present)")
    if result["parse_errors"]:
        print(f"WARNING: {result['parse_errors']} chapters had unparseable quiz_json (skipped)")
    print("breakdown by inferred KP:")
    for kp_code, cnt in sorted(result["kp_breakdown"].items(), key=lambda kv: -kv[1]):
        print(f"  {kp_code}: {cnt}")

    # 验证查询
    db = SessionLocal()
    try:
        total = db.scalar(select(func.count(Question.id)))
        print(f"\nquestions after: {total}")
        print("SELECT source_type, COUNT(*) FROM questions GROUP BY source_type:")
        for st, c in db.execute(
            select(Question.source_type, func.count(Question.id)).group_by(Question.source_type)
        ):
            print(f"  {st}: {c}")
        print("SELECT kp.code, COUNT(q.id) FROM knowledge_points kp LEFT JOIN questions q ...:")
        from app.db.models import KnowledgePoint
        rows = db.execute(
            select(KnowledgePoint.code, func.count(Question.id))
            .select_from(KnowledgePoint)
            .outerjoin(Question, Question.knowledge_point_id == KnowledgePoint.id)
            .group_by(KnowledgePoint.id)
        ).all()
        for code, c in rows:
            print(f"  {code}: {c}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
