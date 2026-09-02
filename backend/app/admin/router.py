"""管理后台路由 —— 爬虫和AI生题的管理接口。

/admin/crawler/*  爬虫管理
/admin/ai/*       AI生题管理
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.common.auth import require_admin
from app.db.database import get_db
from app.db.models import CrawlSourceItem, Policy, Question

router = APIRouter(
    prefix="/admin",
    tags=["管理后台"],
    dependencies=[Depends(require_admin)],
)


# ============ 爬虫管理 ============

@router.get("/crawler/sources", summary="爬虫数据源列表")
def crawler_sources():
    """列出所有可用的爬虫数据源及调度信息。"""
    from crawlers.scheduler import get_scheduler_info

    sources = [
        {"name": "gov_policy", "label": "政府政策站(发改委/能源局)",
         "desc": "国家政策法规，合规权威源", "schedule": "每日8:00"},
        {"name": "zhihu_bilibili", "label": "知乎/B站公开图文",
         "desc": "真题回忆、考点解读", "schedule": "每日20:00"},
        {"name": "standard_pdf", "label": "国家职业标准PDF",
         "desc": "解析权重表，更新考点占比", "schedule": "每周一6:00"},
        {"name": "nea_statistics", "label": "国家能源局公开统计",
         "desc": "用电量、交易电量、装机利用小时、绿证和新能源项目", "schedule": "每日12:20"},
        {"name": "nbs_energy", "label": "国家统计局能源生产",
         "desc": "真实煤油气电月度产量及同比", "schedule": "每日12:40检查增量"},
        {"name": "gzpec_market", "label": "广州电力交易中心公开行情",
         "desc": "南方区域现货及绿证周行情", "schedule": "每日13:00检查增量"},
        {"name": "carbon_market", "label": "全国碳市场日行情",
         "desc": "上海环境能源交易所CEA开高低收及成交量额", "schedule": "每日18:20"},
        {"name": "qweather", "label": "和风天气",
         "desc": "国内气象实况与逐小时预报（需本地凭证）", "schedule": "配置后每小时"},
    ]
    sched = get_scheduler_info()
    return {"sources": sources, "scheduler": sched}


@router.get("/crawler/items", summary="增量采集原文账本")
def crawler_items(
    crawler_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """查看原文唯一标识、处理状态和血缘；不返回任何授权凭证。"""
    limit = max(1, min(limit, 500))
    query = db.query(CrawlSourceItem)
    if crawler_name:
        query = query.filter(CrawlSourceItem.crawler_name == crawler_name)
    if status:
        query = query.filter(CrawlSourceItem.status == status)
    unknown_publish_date = case(
        (
            (CrawlSourceItem.published_at.is_(None))
            | (CrawlSourceItem.published_at == ""),
            1,
        ),
        else_=0,
    )
    rows = query.order_by(
        unknown_publish_date.asc(),
        CrawlSourceItem.published_at.desc(),
        CrawlSourceItem.last_seen_at.desc(),
        CrawlSourceItem.id.desc(),
    ).limit(limit).all()
    summary_rows = db.query(
        CrawlSourceItem.crawler_name,
        CrawlSourceItem.status,
        func.count(CrawlSourceItem.id),
    ).group_by(
        CrawlSourceItem.crawler_name,
        CrawlSourceItem.status,
    ).all()
    summary: dict[str, dict[str, int]] = {}
    for source, item_status, count in summary_rows:
        summary.setdefault(source, {})[item_status] = count
    return {
        "summary": summary,
        "items": [
            {
                "crawler_name": row.crawler_name,
                "source_item_id": row.source_item_id,
                "source_url": row.source_url,
                "title": row.title,
                "published_at": row.published_at,
                "status": row.status,
                "content_sha256": row.content_sha256,
                "parser_version": row.parser_version,
                "data_count": row.data_count,
                "first_seen_at": row.first_seen_at.isoformat() if row.first_seen_at else None,
                "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                "last_attempt_at": row.last_attempt_at.isoformat() if row.last_attempt_at else None,
                "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
                "error_message": row.error_message,
            }
            for row in rows
        ],
    }


@router.post("/crawler/run/{source}", summary="手动运行单个爬虫")
def run_crawler(source: str):
    """手动触发某个爬虫立即执行。"""
    from crawlers.scheduler import run_single_crawler
    try:
        stats = run_single_crawler(source)
        return {"ok": True, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/crawler/run-all", summary="手动运行所有爬虫")
def run_all_crawlers_api():
    """手动触发所有爬虫。"""
    from crawlers.scheduler import run_all_crawlers
    result = run_all_crawlers()
    return {"ok": True, **result}


# ============ AI生题管理 ============

class GenFromPolicyReq(BaseModel):
    policy_id: int
    count: int = 5


class GenFromKpReq(BaseModel):
    knowledge_point_code: str
    count: int = 5


@router.post("/ai/generate-from-policy", summary="基于政策AI生题")
def ai_gen_from_policy(
    req: GenFromPolicyReq,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """选择一条政策，用LLM生成相关题目。"""
    from app.ai.question_generator import generate_from_policy
    questions = generate_from_policy(
        db, req.policy_id, req.count, llm_user_id=current_user.id
    )
    return {"ok": True, "generated": len(questions), "questions": questions}


@router.post("/ai/generate-from-knowledge", summary="基于知识点AI生题")
def ai_gen_from_kp(
    req: GenFromKpReq,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """选择一个知识点，用LLM生成题目。"""
    from app.ai.question_generator import generate_from_knowledge
    questions = generate_from_knowledge(
        db, req.knowledge_point_code, req.count, llm_user_id=current_user.id
    )
    return {"ok": True, "generated": len(questions), "questions": questions}


# ============ 题库统计 ============

@router.get("/stats", summary="题库与政策统计")
def stats(db: Session = Depends(get_db)):
    """题库来源构成、政策数量等统计。"""
    total_q = db.execute(select(func.count()).select_from(select(Question).subquery())).scalar() or 0
    ai_q = db.execute(
        select(func.count()).select_from(
            select(Question).where(Question.is_ai_generated.is_(True)).subquery()
        )
    ).scalar() or 0
    real_q = db.execute(
        select(func.count()).select_from(
            select(Question).where(Question.is_real_exam.is_(True)).subquery()
        )
    ).scalar() or 0
    crawler_q = db.execute(
        select(func.count()).select_from(
            select(Question).where(Question.source_type == "crawler").subquery()
        )
    ).scalar() or 0
    total_p = db.execute(select(func.count()).select_from(select(Policy).subquery())).scalar() or 0

    return {
        "questions": {
            "total": total_q,
            "ai_generated": ai_q,
            "real_exam": real_q,
            "crawler": crawler_q,
            "manual": total_q - ai_q - crawler_q,
        },
        "policies": {"total": total_p},
    }
