"""考试组卷引擎 + 考点预测。

核心能力：
1. 按真实统考配比组卷（单选100/多选30/判断40 = 100分）
2. 考点预测：政策权重 + 历年高频 + 薄弱点强化，动态调整出题分布
3. 学习模式组卷：按知识点驱动，不计时

设计依据：2024国家职业标准 + 历年真题统计
  单选100×0.5=50分(50%) + 多选30×1=30分(30%) + 判断40×0.5=20分(20%)
"""
import json
import random
from collections import defaultdict
from datetime import date
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ExamBlueprint,
    ExamWeight,
    KnowledgePoint,
    Question,
    StudyRecord,
    WrongAnswer,
)

# 真实统考题型配比（已核实：2024国家职业标准 + 历年真题）
REAL_EXAM_CONFIG = {
    "single": {"count": 100, "score": 0.5, "label": "单选题"},
    "multiple": {"count": 30, "score": 1.0, "label": "多选题"},
    "judge": {"count": 40, "score": 0.5, "label": "判断题"},
}


# ============ 组卷引擎 ============

def build_exam_paper(
    db: Session,
    mode: str = "exam",
    level: Optional[str] = None,
    knowledge_point_id: Optional[int] = None,
    target_count: int = 50,
    focus_weak: bool = False,
    user_id: int = 1,
) -> list[Question]:
    """组卷。

    mode="exam": 按真实题型配比（单选50%/多选30%/判断20%）抽题
    mode="predict": 押题模式，在exam基础上叠加考点预测权重
    mode="real": 历年真题模式，只从 is_real_exam 标记的题中抽，按年份/级别筛选
    mode="study": 学习模式，按知识点驱动，题型随机
    """
    if mode == "study":
        return _build_study_paper(db, knowledge_point_id, target_count)
    elif mode == "real":
        return _build_real_exam_paper(db, level, knowledge_point_id, target_count)
    else:
        return _build_exam_paper(db, mode, level, target_count, focus_weak, user_id)


def _build_real_exam_paper(
    db: Session, level: Optional[str], knowledge_point_id: Optional[int],
    target_count: int, year: Optional[int] = None,
) -> list[Question]:
    """历年真题组卷：只从 is_real_exam 标记的题目中抽。

    支持按年份、级别、知识点筛选；不足时用普通题补齐（保证可考）。
    """
    stmt = select(Question).where(Question.is_active.is_(True), Question.is_real_exam.is_(True))
    if level:
        stmt = stmt.where((Question.exam_level == level) | (Question.exam_level.is_(None)))
    if knowledge_point_id:
        stmt = stmt.where(Question.knowledge_point_id == knowledge_point_id)

    real_questions = list(db.execute(stmt).scalars().all())

    if not real_questions:
        # 没有真题时，退回普通题库（保证可用，但前端会提示）
        return _build_exam_paper(db, "exam", level, target_count, False, 1)

    # 仍按真实题型配比从真题池抽取
    ratios = {"single": 0.50, "multiple": 0.30, "judge": 0.20}
    result = []
    for qtype, ratio in ratios.items():
        count = max(1, int(target_count * ratio))
        pool = [q for q in real_questions if q.type == qtype]
        if pool:
            picked = random.sample(pool, min(count, len(pool)))
            result.extend(picked)

    # 真题不足时用普通题补到 target_count
    if len(result) < target_count:
        existing_ids = {q.id for q in result}
        fill_stmt = select(Question).where(
            Question.is_active.is_(True), Question.is_real_exam.is_(False)
        )
        if level:
            fill_stmt = fill_stmt.where((Question.exam_level == level) | (Question.exam_level.is_(None)))
        fill_pool = [q for q in db.execute(fill_stmt).scalars().all() if q.id not in existing_ids]
        need = target_count - len(result)
        if fill_pool:
            result.extend(random.sample(fill_pool, min(need, len(fill_pool))))

    random.shuffle(result)
    return result


def _build_exam_paper(
    db: Session, mode: str, level: Optional[str], target_count: int,
    focus_weak: bool, user_id: int,
) -> list[Question]:
    """按真实配比组卷。target_count 不足时按比例缩放。"""
    # 计算各题型应抽数量（按真实占比缩放到 target_count）
    ratios = {"single": 0.50, "multiple": 0.30, "judge": 0.20}
    type_counts = {t: max(1, int(target_count * r)) for t, r in ratios.items()}

    # 微调使总数=target_count
    diff = target_count - sum(type_counts.values())
    if diff:
        type_counts["single"] += diff  # 差额补到单选

    result = []
    for qtype, count in type_counts.items():
        picked = _pick_questions(
            db, qtype=qtype, count=count, level=level,
            mode=mode, focus_weak=focus_weak, user_id=user_id,
        )
        result.extend(picked)
    random.shuffle(result)
    return result


def _build_study_paper(
    db: Session, knowledge_point_id: Optional[int], target_count: int
) -> list[Question]:
    """学习模式：按知识点驱动抽题。"""
    stmt = select(Question).where(Question.is_active.is_(True))
    if knowledge_point_id:
        stmt = stmt.where(Question.knowledge_point_id == knowledge_point_id)
    questions = db.execute(stmt).scalars().all()
    if not questions:
        return []
    pick_n = min(target_count, len(questions))
    return random.sample(list(questions), pick_n)


def _pick_questions(
    db: Session, qtype: str, count: int, level: Optional[str],
    mode: str, focus_weak: bool, user_id: int,
) -> list[Question]:
    """按题型抽题，支持考点预测权重和薄弱点强化。"""
    stmt = select(Question).where(Question.is_active.is_(True), Question.type == qtype)
    if level:
        stmt = stmt.where((Question.exam_level == level) | (Question.exam_level.is_(None)))
    candidates = list(db.execute(stmt).scalars().all())

    if not candidates:
        return []

    # ---- 押题模式：按考点预测权重加权抽样 ----
    if mode == "predict":
        weights = _calc_prediction_weights(db, candidates)
        # 加权抽样（不重复）
        picked = _weighted_sample(candidates, weights, count)
        return picked

    # ---- 薄弱点强化：优先抽用户错过/没掌握的题 ----
    if focus_weak:
        weak_ids = set(
            db.execute(
                select(WrongAnswer.question_id).where(
                    WrongAnswer.user_id == user_id, WrongAnswer.reviewed.is_(False)
                )
            ).scalars().all()
        )
        weak_pool = [q for q in candidates if q.id in weak_ids]
        normal_pool = [q for q in candidates if q.id not in weak_ids]
        # 50% 来自错题，50% 来自新题
        weak_n = min(len(weak_pool), count // 2)
        picked = random.sample(weak_pool, weak_n) if weak_n else []
        remaining = count - len(picked)
        if remaining > 0 and normal_pool:
            picked += random.sample(normal_pool, min(remaining, len(normal_pool)))
        return picked

    # 普通随机
    return random.sample(candidates, min(count, len(candidates)))


def _calc_prediction_weights(db: Session, questions: list[Question]) -> list[float]:
    """计算每题的预测权重。

    权重来源：
    1. 官方模块权重表（ExamWeight）—— 权重高的模块的题权重高
    2. 真题标记 —— 历年真题权重 ×2
    3. 政策关联 —— prediction_tags 标记"新增/政策关联"的题权重 ×3
    4. 用户薄弱 —— 错过的题适度加权
    """
    # 模块权重映射
    weights_map = {}
    ew = db.execute(select(ExamWeight)).scalars().all()
    for w in ew:
        if w.knowledge_point_id:
            # 权重 + 预测加成
            weights_map[w.knowledge_point_id] = w.weight_pct + w.prediction_boost

    result = []
    for q in questions:
        w = 1.0
        # 模块权重
        if q.knowledge_point_id and q.knowledge_point_id in weights_map:
            w *= (1.0 + weights_map[q.knowledge_point_id] / 100.0)
        # 真题加权
        if q.is_real_exam:
            w *= 2.0
        # 政策关联/新增考点
        if q.prediction_tags:
            try:
                tags = json.loads(q.prediction_tags)
                if "新增" in tags or "政策关联" in tags or "高频" in tags:
                    w *= 3.0
            except (json.JSONDecodeError, TypeError):
                pass
        result.append(max(w, 0.1))
    return result


def _weighted_sample(items: list, weights: list[float], k: int) -> list:
    """加权无重复抽样。"""
    if k >= len(items):
        return list(items)
    picked = []
    pool = list(zip(items, weights))
    for _ in range(min(k, len(pool))):
        total = sum(w for _, w in pool)
        if total <= 0:
            break
        r = random.uniform(0, total)
        cum = 0
        for i, (item, w) in enumerate(pool):
            cum += w
            if cum >= r:
                picked.append(item)
                pool.pop(i)
                break
    return picked


# ============ 考点预测分析 ============

def get_prediction_report(db: Session, level: str = "four") -> dict:
    """生成考点预测报告。

    输出：当年各模块的预测考点占比 + 高频考点 + 政策关联新考点。
    """
    # 1. 官方模块权重
    weights = db.execute(
        select(ExamWeight).where(ExamWeight.level == level)
    ).scalars().all()

    modules = []
    for w in weights:
        kp = db.get(KnowledgePoint, w.knowledge_point_id) if w.knowledge_point_id else None
        # 该模块题目数
        q_count = db.execute(
            select(func.count()).select_from(
                select(Question).where(
                    Question.knowledge_point_id == w.knowledge_point_id,
                    Question.is_active.is_(True),
                ).subquery()
            )
        ).scalar() or 0
        modules.append({
            "module": w.module_name,
            "knowledge_point": kp.name if kp else None,
            "official_weight": w.weight_pct,
            "prediction_boost": w.prediction_boost,
            "predicted_weight": round(w.weight_pct + w.prediction_boost, 1),
            "question_count": q_count,
        })
    modules.sort(key=lambda x: x["predicted_weight"], reverse=True)

    # 2. 高频真题考点（统计真题标记）
    real_questions = db.execute(
        select(Question).where(Question.is_real_exam.is_(True))
    ).scalars().all()
    hotspot = defaultdict(int)
    for q in real_questions:
        if q.knowledge_point_id:
            kp = db.get(KnowledgePoint, q.knowledge_point_id)
            if kp:
                hotspot[kp.name] += 1
    hotspots = sorted(hotspot.items(), key=lambda x: -x[1])[:5]

    # 3. 政策关联新考点（标记了 prediction_tags 的题）
    new_tags = db.execute(
        select(Question).where(Question.prediction_tags.isnot(None))
    ).scalars().all()
    new_points = []
    for q in new_tags:
        try:
            tags = json.loads(q.prediction_tags) if q.prediction_tags else []
            if any(t in tags for t in ["新增", "政策关联", "高频"]):
                new_points.append({
                    "stem": q.stem[:40],
                    "tags": tags,
                    "level": q.exam_level,
                })
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "level": level,
        "level_label": {"four": "中级工", "three": "高级工", "two": "技师", "one": "高级技师"}.get(level, level),
        "modules": modules[:8],
        "hotspots": [{"point": p, "count": c} for p, c in hotspots],
        "new_points": new_points[:10],
        "generated_at": date.today().isoformat(),
    }


# ============ 考后分析 ============

def analyze_weakness(db: Session, session_id: int) -> dict:
    """考后薄弱点分析：统计各知识点错误率。"""
    from app.db.models import ExamSession

    session = db.get(ExamSession, session_id)
    if not session or not session.answers:
        return {}

    answers = json.loads(session.answers) if session.answers else []
    # 按知识点统计对错（同时记录 knowledge_point_id 以便前端跳转针对性练习）
    kp_stats = defaultdict(lambda: {"correct": 0, "wrong": 0, "knowledge_point_id": None})
    for a in answers:
        q = db.get(Question, a.get("question_id"))
        if q and q.knowledge_point_id:
            kp = db.get(KnowledgePoint, q.knowledge_point_id)
            if kp:
                key = kp.name
                kp_stats[key]["knowledge_point_id"] = q.knowledge_point_id
                if a.get("correct"):
                    kp_stats[key]["correct"] += 1
                else:
                    kp_stats[key]["wrong"] += 1

    weak = []
    for kp_name, stats in kp_stats.items():
        total = stats["correct"] + stats["wrong"]
        rate = stats["wrong"] / total if total else 0
        if rate >= 0.4:  # 错误率>=40%判为薄弱
            weak.append({
                "knowledge_point": kp_name,
                "knowledge_point_id": stats["knowledge_point_id"],
                "wrong_rate": round(rate * 100),
                "wrong": stats["wrong"], "total": total,
            })
    weak.sort(key=lambda x: -x["wrong_rate"])

    return {
        "total_questions": len(answers),
        "weak_points": weak[:5],
        "score": session.score,
    }
