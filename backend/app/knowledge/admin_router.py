"""数据资产中心管理路由 —— 多源接入的统一入口。

/asset/ingest/curl     粘贴curl→自动抓取沉淀
/asset/ingest/upload   上传文件→解析归档
/asset/ingest/manual   手动录入文章
/asset/ingest/feishu   从飞书知识库批量导入
/asset/crawler/run     按类型触发爬虫(policy/exam/trade_data/news)
/asset/timeline        按时间线浏览数据资产
/asset/stats           数据资产统计
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.auth import get_current_user, require_admin
from app.config import settings
from app.db.database import get_db
from app.db.models import KnowledgeDoc, PublicData
from app.common.input_security import (
    UnsafeInputError,
    read_upload_limited,
    safe_filename,
    validate_file_extension,
    validate_file_signature,
)
from app.knowledge.ingest import ingest_curl, ingest_manual, ingest_upload
from app.knowledge.ordering import DOC_TYPE_RANK, knowledge_doc_order_by

logger = logging.getLogger("asset")
router = APIRouter(
    prefix="/asset",
    tags=["数据资产中心"],
)


PUBLIC_DATA_TYPE_LABELS = {
    "clearing": "出清价格曲线",
    "load": "负荷曲线",
    "coal": "动力煤价格",
    "carbon": "全国碳市场价格",
    "weather_observation": "气象实况",
    "weather_forecast_hourly": "逐小时天气预报",
    "southern_spot_weekly": "南方现货周报",
    "green_certificate_weekly": "绿证交易周报",
    "national_market_transaction": "全国市场交易电量",
    "national_market_transaction_ytd": "全国市场累计交易",
    "national_power_consumption": "全国用电量",
    "national_power_statistics": "全国电力统计",
    "national_green_certificate": "全国绿证统计",
    "national_new_energy_projects": "新能源项目统计",
    "nbs_energy_production": "全国能源生产统计",
}

PUBLIC_DATA_TYPE_RANK = {
    "weather_observation": 9,
    "weather_forecast_hourly": 8,
    "clearing": 7,
    "load": 6,
    "carbon": 5,
    "coal": 4,
    "southern_spot_weekly": 3,
    "green_certificate_weekly": 3,
}


# ============ cURL 快速抓取（核心功能）============

class CurlReq(BaseModel):
    curl: str
    doc_type: str = "industry_news"
    province: Optional[str] = None
    tags: Optional[list[str]] = None


@router.post("/ingest/curl", summary="cURL快速抓取(粘贴curl→自动沉淀)")
def ingest_by_curl(
    req: CurlReq,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """粘贴一个curl命令，系统自动：解析→抓取→提取正文→AI总结→归档。

    支持 HTML页面(提取正文) 和 PDF/Word文件(下载为附件)。
    """
    if not req.curl or "http" not in req.curl:
        raise HTTPException(status_code=400, detail="请提供有效的curl命令(需含URL)")
    result = ingest_curl(
        db, req.curl, req.doc_type, req.province, req.tags, current_user.id
    )
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "抓取失败"))
    return result


# ============ 文件上传 ============

@router.post("/ingest/upload", summary="上传文件(解析→归档)")
async def ingest_by_upload(
    file: UploadFile = File(...),
    doc_type: str = Form("industry_news"),
    province: str = Form(None),
    title: str = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """上传PDF/Word/Excel，自动解析文本、AI总结、归档。"""
    try:
        result = await ingest_upload(
            db, file, doc_type, province, title, current_user.id
        )
    except UnsafeInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


# ============ 手动录入 ============

class ManualReq(BaseModel):
    title: str
    content: str
    doc_type: str = "industry_news"
    province: Optional[str] = None
    publish_date: Optional[str] = None
    source: str = "手动录入"
    tags: Optional[list[str]] = None


@router.post("/ingest/manual", summary="手动录入文章")
def ingest_by_manual(
    req: ManualReq,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """手动录入标题和正文，AI自动总结后归档。"""
    if not req.title or not req.content:
        raise HTTPException(status_code=400, detail="标题和内容不能为空")
    return ingest_manual(db, req.title, req.content, req.doc_type,
                         req.province, req.publish_date, req.source, req.tags,
                         current_user.id)


# ============ 飞书知识库导入 ============

class FeishuImportReq(BaseModel):
    wiki_token: str          # 飞书知识库节点token
    doc_type: str = "national_policy"
    province: Optional[str] = None


@router.post("/ingest/feishu", summary="从飞书知识库导入单篇文档")
def ingest_from_feishu(
    req: FeishuImportReq,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """从飞书知识库拉取一篇文档，导入到系统知识库。

    提供飞书wiki的node_token，系统读取文档内容和附件，归档到知识库。
    """
    import subprocess
    try:
        # 用lark-cli读取飞书文档
        result = subprocess.run(
            ["lark-cli", "docs", "+fetch", "--api-version", "v2",
             "--doc", req.wiki_token, "--as", "user"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"飞书读取失败: {result.stderr[:200]}")

        data = json.loads(result.stdout)
        content_xml = data.get("data", {}).get("document", {}).get("content", "")

        # 从XML提取纯文本
        import re
        text = re.sub(r"<[^>]+>", " ", content_xml)
        text = re.sub(r"\s+", " ", text).strip()
        title = text[:50] if text else "飞书导入文档"

        if len(text) < 10:
            text = "从飞书知识库导入，原文内容为空。"

        return ingest_manual(db, title, text[:5000], req.doc_type,
                             req.province, source="飞书知识库导入",
                             llm_user_id=current_user.id)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="飞书读取超时")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="飞书返回解析失败")


# ============ 通道6: Excel/CSV 批量导入 ============

@router.post("/ingest/spreadsheet", summary="Excel/CSV批量导入(结构化表格)")
async def ingest_by_spreadsheet(
    file: UploadFile = File(...),
    target: str = Form("doc", description="目标: doc文档/question题库/policy政策"),
    doc_type: str = Form("industry_news"),
    province: str = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """上传 Excel/CSV，自动识别列名，逐行解析入库。

    - target=doc: 每行→KnowledgeDoc（需 标题/正文 列）
    - target=question: 每行→Question（需 题干/选项/答案 列）
    - target=policy: 每行→KnowledgeDoc政策（需 标题/文号/日期/正文 列）

    列名中英文兼容，如「标题」=title、「题干」=stem。
    """
    from app.knowledge.ingest import ingest_spreadsheet
    try:
        filename = safe_filename(file.filename, "upload.xlsx")
        validate_file_extension(filename, {"csv", "xlsx"})
        content_bytes = await read_upload_limited(
            file, max(1, settings.ASSET_UPLOAD_MAX_MB) * 1024 * 1024
        )
        validate_file_signature(filename, content_bytes)
    except UnsafeInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = ingest_spreadsheet(db, content_bytes, filename,
                                target=target, doc_type=doc_type, province=province,
                                llm_user_id=current_user.id)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "导入失败"))
    return result


# ============ 通道7: API 数据源直连 ============

class ApiSourceReq(BaseModel):
    name: str
    url: str
    method: str = "GET"
    headers: Optional[dict] = None
    params: Optional[dict] = None
    data_type: str = "industry_news"  # clearing/coal/carbon/load/industry_news
    province: Optional[str] = None
    doc_type: str = "industry_news"
    extract: Optional[dict] = None  # {date:"data.date", price:"data.price"}


@router.post("/ingest/api", summary="API数据源直连(配置式拉取)")
def ingest_by_api(
    req: ApiSourceReq,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """配置一个API端点，直接拉取数据入库。

    结构化数值（clearing/coal/carbon/load）→ PublicData 表
    文档型数据 → KnowledgeDoc 表
    """
    from app.knowledge.ingest import ingest_api_source
    result = ingest_api_source(db, req.model_dump(), current_user.id)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result


# ============ 通道8: RSS 订阅监听 ============

class RssReq(BaseModel):
    feed_url: str
    doc_type: str = "industry_news"
    province: Optional[str] = None


@router.post("/ingest/rss", summary="RSS订阅监听(新文章自动入库)")
def ingest_by_rss(
    req: RssReq,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """输入RSS feed URL，拉取最新文章入库。

    适合电力行业媒体（北极星电力、能源杂志、中国电力网等）。
    新文章自动去重，已入库的不会重复。
    """
    from app.knowledge.ingest import ingest_rss
    result = ingest_rss(
        db, req.feed_url, req.doc_type, req.province, current_user.id
    )
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result


# ============ 通道9: 飞书 Base 表格同步 ============

class FeishuBaseReq(BaseModel):
    app_token: str
    table_id: str
    target: str = "question"  # question/doc/policy
    field_mapping: Optional[dict] = None


@router.post("/ingest/feishu-base", summary="飞书Base表格同步(结构化数据)")
def ingest_by_feishu_base(
    req: FeishuBaseReq,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """同步飞书多维表格(Base)数据。

    target=question: 题库表（题干/选项/答案列）→ Question
    target=doc: 文档表 → KnowledgeDoc
    """
    from app.knowledge.ingest import ingest_feishu_base
    result = ingest_feishu_base(
        db, req.app_token, req.table_id, req.target, req.field_mapping,
        current_user.id,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result


# ============ 爬虫按类型触发 ============

class CrawlerRunReq(BaseModel):
    crawler_type: str  # policy/exam/trade_data/official_stats/clearing/load/weather/commodity/news/all


# 爬虫运行状态（内存态，供前端轮询"运行中/结果"，实现异步不阻塞）
_crawler_state: dict = {}

CRAWLER_TYPE_MAPPING = {
    "policy": ["gov_policy", "standard_pdf"],
    "exam": ["zhihu_bilibili"],
    "trade_data": [
        "nea_statistics", "nbs_energy", "gzpec_market", "carbon_market",
        "clearing_price", "load_forecast", "coal_price",
    ],
    "official_stats": ["nea_statistics", "nbs_energy"],
    "clearing": ["clearing_price"],
    "load": ["load_forecast"],
    "weather": ["qweather"],
    "commodity": ["coal_price", "carbon_market"],
    "news": ["gov_policy"],
    "all": [
        "gov_policy", "zhihu_bilibili", "standard_pdf", "nea_statistics",
        "nbs_energy", "gzpec_market", "carbon_market", "clearing_price",
        "load_forecast", "coal_price", "qweather",
    ],
}


@router.post("/crawler/run", summary="按类型触发爬虫(异步)")
def run_crawler_by_type(req: CrawlerRunReq, current_user=Depends(require_admin)):
    """异步触发：后台线程执行，立即返回；前端轮询 /crawler/status 看进度+结果。"""
    import threading
    from datetime import datetime
    from crawlers.scheduler import run_single_crawler

    targets = CRAWLER_TYPE_MAPPING.get(req.crawler_type)
    if not targets:
        raise HTTPException(
            status_code=400,
            detail=(
                f"未知类型: {req.crawler_type}，可选: "
                "policy/exam/trade_data/clearing/load/weather/commodity/news/all"
            ),
        )
    ct = req.crawler_type
    if _crawler_state.get(ct, {}).get("running"):
        return {"crawler_type": ct, "status": "already_running"}

    started = datetime.now().isoformat()
    _crawler_state[ct] = {"running": True, "results": [],
                          "progress": {"done": 0, "total": len(targets), "current": targets[0]},
                          "started_at": started}

    def _bg():
        results = []
        for i, name in enumerate(targets):
            # 实时进度：正在跑第 i 个，已完成 i 个，附带已有结果
            _crawler_state[ct] = {"running": True, "results": list(results),
                                  "progress": {"done": i, "total": len(targets), "current": name},
                                  "started_at": started}
            try:
                results.append(run_single_crawler(name))
            except Exception as e:
                results.append({"source": name, "error": str(e)})
        _crawler_state[ct] = {"running": False, "results": results,
                              "progress": {"done": len(targets), "total": len(targets), "current": None},
                              "started_at": started, "finished_at": datetime.now().isoformat()}

    threading.Thread(target=_bg, daemon=True).start()
    return {"crawler_type": ct, "status": "started"}


@router.get("/crawler/status", summary="爬虫运行状态(供前端轮询)")
def crawler_status(crawler_type: Optional[str] = None, current_user=Depends(get_current_user)):
    """返回某类型(或全部)的运行状态与最近结果。"""
    if crawler_type:
        return _crawler_state.get(crawler_type, {"running": False, "results": None})
    return _crawler_state


# ============ 和风天气连接器 ============

@router.get("/connectors/qweather/status", summary="和风天气连接器状态")
def qweather_status(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """返回脱敏配置状态、数据量和最后同步时间。"""
    from app.db.models import PublicData
    from crawlers.adapters.qweather import connector_status

    status = connector_status()
    weather_types = ("weather_observation", "weather_forecast_hourly")
    count = db.query(PublicData).filter(PublicData.data_type.in_(weather_types)).count()
    latest = (
        db.query(PublicData)
        .filter(PublicData.data_type.in_(weather_types))
        .order_by(PublicData.fetched_at.desc())
        .first()
    )
    status["records"] = count
    status["last_sync_at"] = latest.fetched_at if latest else None
    status["last_quality_status"] = latest.quality_status if latest else None
    return status


@router.post("/connectors/qweather/test", summary="测试和风天气连接")
def qweather_test(current_user=Depends(require_admin)):
    from crawlers.adapters.qweather import QWeatherError, test_connection

    try:
        return test_connection()
    except QWeatherError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/connectors/qweather/locations", summary="搜索和风国内城市")
def qweather_locations(q: str, adm: Optional[str] = None, current_user=Depends(get_current_user)):
    from crawlers.adapters.qweather import QWeatherClient, QWeatherError

    if not q.strip():
        raise HTTPException(status_code=400, detail="请输入城市名称")
    try:
        return {"ok": True, "location": QWeatherClient().city_lookup(q.strip(), adm)}
    except QWeatherError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ============ 数据资产时间线浏览 ============

@router.get("/timeline", summary="数据资产时间线(按时间倒序)")
def timeline(doc_type: Optional[str] = None, province: Optional[str] = None,
             page: int = 1, page_size: int = 30, db: Session = Depends(get_db),
             current_user=Depends(get_current_user)):
    """统一浏览文档资产和 PublicData 时序资产，严格按业务日期倒序。

    ``doc_type=data:<public_data_type>`` 用于筛选结构化时序数据。文档使用
    官方发布日期，结构化数据使用数据所属日期；抓取时间只作为血缘信息展示，
    不会冒充业务发布日期。
    """
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    data_type_filter = doc_type[5:] if doc_type and doc_type.startswith("data:") else None
    merged_items: list[dict] = []

    # 文档型资产：政策、公告、行业资讯等。
    if not data_type_filter:
        doc_stmt = select(KnowledgeDoc)
        if doc_type:
            doc_stmt = doc_stmt.where(KnowledgeDoc.doc_type == doc_type)
        if province:
            doc_stmt = doc_stmt.where(KnowledgeDoc.province == province)
        docs = db.execute(doc_stmt).scalars().all()
        for doc in docs:
            item = _doc_brief(doc)
            item.update({
                "asset_kind": "document",
                "record_count": 1,
                "fetched_at": doc.created_at.isoformat() if doc.created_at else None,
            })
            merged_items.append(item)

    # 结构化时序资产按“类型 + 省份 + 数据日期 + 来源”聚合，避免逐小时天气
    # 一次铺满整个时间线。data_date 是业务日期，fetched_at 是采集时间。
    if not doc_type or data_type_filter:
        asset_date = func.substr(PublicData.data_date, 1, 10).label("asset_date")
        data_stmt = select(
            func.max(PublicData.id).label("id"),
            PublicData.data_type,
            PublicData.province,
            asset_date,
            PublicData.source,
            PublicData.source_url,
            PublicData.provenance_level,
            PublicData.quality_status,
            func.max(PublicData.fetched_at).label("fetched_at"),
            func.count(PublicData.id).label("record_count"),
        )
        if data_type_filter:
            data_stmt = data_stmt.where(PublicData.data_type == data_type_filter)
        if province:
            data_stmt = data_stmt.where(PublicData.province == province)
        data_stmt = data_stmt.group_by(
            PublicData.data_type,
            PublicData.province,
            asset_date,
            PublicData.source,
            PublicData.source_url,
            PublicData.provenance_level,
            PublicData.quality_status,
        )
        for row in db.execute(data_stmt).all():
            label = PUBLIC_DATA_TYPE_LABELS.get(row.data_type, row.data_type)
            scope = row.province or "全国"
            merged_items.append({
                "id": f"public-{row.id}",
                "title": f"{scope} · {label}",
                "doc_type": row.data_type,
                "data_type": row.data_type,
                "province": row.province,
                "ingest_type": "structured",
                "source": row.source,
                "source_url": row.source_url,
                "ai_summary": None,
                "publish_date": row.asset_date,
                "asset_kind": "structured_data",
                "record_count": row.record_count,
                "fetched_at": row.fetched_at,
                "provenance_level": row.provenance_level,
                "quality_status": row.quality_status,
            })

    def _sort_key(item: dict):
        business_date = item.get("publish_date") or ""
        if item.get("asset_kind") == "structured_data":
            rank = PUBLIC_DATA_TYPE_RANK.get(item.get("data_type"), 1)
        else:
            rank = DOC_TYPE_RANK.get(item.get("doc_type"), 0)
        return (bool(business_date), business_date, rank, str(item.get("id") or ""))

    merged_items.sort(key=_sort_key, reverse=True)
    total = len(merged_items)
    start = (page - 1) * page_size
    items = merged_items[start:start + page_size]

    # 按业务日期分组（时间线）
    from collections import OrderedDict
    timeline_groups = OrderedDict()
    for item in items:
        date_key = item.get("publish_date") or "未知日期"
        if date_key not in timeline_groups:
            timeline_groups[date_key] = []
        timeline_groups[date_key].append(item)

    return {
        "total": total, "page": page,
        "timeline": [{"date": k, "items": v} for k, v in timeline_groups.items()],
    }


# ============ 数据资产统计 ============

@router.get("/stats", summary="数据资产总览统计")
def asset_stats(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """数据资产的多维统计：来源构成/类型分布/省份覆盖/增长趋势。"""
    # 来源构成
    by_ingest = db.execute(
        select(KnowledgeDoc.ingest_type, func.count()).group_by(KnowledgeDoc.ingest_type)
    ).all()
    # 类型分布
    by_type = db.execute(
        select(KnowledgeDoc.doc_type, func.count()).group_by(KnowledgeDoc.doc_type)
    ).all()
    # 省份覆盖
    by_province = db.execute(
        select(KnowledgeDoc.province, func.count())
        .where(KnowledgeDoc.province.isnot(None)).group_by(KnowledgeDoc.province)
    ).all()
    # 总数
    total = db.execute(select(func.count()).select_from(select(KnowledgeDoc).subquery())).scalar() or 0

    return {
        "total": total,
        "by_ingest": [{"key": k or "manual", "count": n} for k, n in by_ingest],
        "by_type": [{"key": t, "count": n} for t, n in by_type],
        "by_province": [{"key": p, "count": n} for p, n in by_province if p],
    }


# ============================================================
# 运维能力
# ============================================================

# ============ 运维1: 数据质量看板 ============

@router.get("/quality", summary="数据质量看板(完整度/过期/去重)")
def quality_dashboard(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """数据质量总览：完整度分布、低质量文档、过期数据、审核待办。

    质量评分规则（0-100）：
    - 有内容正文 +30, 有AI摘要 +20, 有分类 +20, 有省份 +10,
      有发布日期 +10, 有知识点关联 +10
    """
    from sqlalchemy import or_, text
    all_docs = db.execute(select(KnowledgeDoc)).scalars().all()

    # 计算质量分
    quality_buckets = {"high": 0, "mid": 0, "low": 0}  # >=80 / 50-79 / <50
    issues = []  # 有问题的文档
    for d in all_docs:
        score = 0
        if d.content and len(d.content) > 50:
            score += 30
        if d.ai_summary:
            score += 20
        if d.category_code:
            score += 20
        if d.province:
            score += 10
        if d.publish_date:
            score += 10
        if d.knowledge_point_id:
            score += 10
        d.quality_score = score  # 更新（不立即commit，批量）
        if score >= 80:
            quality_buckets["high"] += 1
        elif score >= 50:
            quality_buckets["mid"] += 1
        else:
            quality_buckets["low"] += 1
            issues.append({"id": d.id, "title": d.title[:30], "score": score,
                           "missing": _missing_fields(d)})
    db.commit()

    # 过期检测（发布日期超过3年且是政策类）
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=365 * 3)).isoformat()
    outdated = db.execute(
        select(func.count()).select_from(
            select(KnowledgeDoc).where(
                KnowledgeDoc.publish_date.isnot(None),
                KnowledgeDoc.publish_date < cutoff,
                KnowledgeDoc.doc_type.in_(["national_policy", "regulation"]),
            ).subquery()
        )
    ).scalar() or 0

    # 审核待办
    pending = db.execute(
        select(func.count()).select_from(
            select(KnowledgeDoc).where(KnowledgeDoc.review_status == "pending").subquery()
        )
    ).scalar() or 0

    return {
        "total": len(all_docs),
        "quality": quality_buckets,
        "outdated": outdated,
        "pending_review": pending,
        "low_quality_samples": issues[:20],
    }


def _missing_fields(d) -> list:
    missing = []
    if not (d.content and len(d.content) > 50):
        missing.append("正文")
    if not d.ai_summary:
        missing.append("摘要")
    if not d.category_code:
        missing.append("分类")
    if not d.province:
        missing.append("省份")
    if not d.publish_date:
        missing.append("日期")
    return missing


# ============ 运维2: 数据流向追踪 ============

class RefTrackReq(BaseModel):
    doc_id: int
    ref_type: str = "ai"  # ai/exam/rule/study
    note: Optional[str] = None


@router.post("/track-ref", summary="记录数据被引用(流向追踪)")
def track_reference(req: RefTrackReq, current_user=Depends(require_admin), db: Session = Depends(get_db)):
    """记录一条数据被上层模块引用（AI助手召回/题目关联/规则引用/学习推荐）。

    供 AI助手/考试/交易 等上层模块在调用数据时调用，形成可追溯链。
    """
    from app.db.models import KnowledgeDoc
    d = db.get(KnowledgeDoc, req.doc_id)
    if not d:
        raise HTTPException(status_code=404, detail="文档不存在")
    d.ref_count += 1
    db.commit()
    return {"ok": True, "doc_id": req.doc_id, "ref_count": d.ref_count,
            "ref_type": req.ref_type}


@router.get("/refs/{doc_id}", summary="文档引用情况")
def doc_references(doc_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """查看一篇文档被引用了多少次，被哪些模块用。
    （当前是计数维度，后续可扩展明细日志表）
    """
    d = db.get(KnowledgeDoc, doc_id)
    if not d:
        raise HTTPException(status_code=404, detail="文档不存在")
    # 检查是否被题目引用
    from app.db.models import Question
    related_qs = []
    if d.knowledge_point_id:
        qs = db.execute(
            select(Question).where(Question.knowledge_point_id == d.knowledge_point_id).limit(5)
        ).scalars().all()
        related_qs = [{"id": q.id, "stem": q.stem[:40], "type": q.type} for q in qs]
    return {
        "doc_id": doc_id, "title": d.title,
        "ref_count": d.ref_count,
        "quality_score": d.quality_score,
        "related_questions": related_qs,
    }


# ============ 运维3: 审核工作流 ============

class ReviewReq(BaseModel):
    doc_id: int
    action: str  # approve/reject


@router.post("/review", summary="审核数据(通过/驳回)")
def review_doc(req: ReviewReq, current_user=Depends(require_admin), db: Session = Depends(get_db)):
    """审核待审数据：approve（通过对外可见）/ reject（驳回隐藏）。"""
    d = db.get(KnowledgeDoc, req.doc_id)
    if not d:
        raise HTTPException(status_code=404, detail="文档不存在")
    if req.action == "approve":
        d.review_status = "approved"
    elif req.action == "reject":
        d.review_status = "rejected"
    else:
        raise HTTPException(status_code=400, detail="action必须是approve或reject")
    db.commit()
    return {"ok": True, "doc_id": req.doc_id, "review_status": d.review_status}


@router.post("/review/batch", summary="批量审核所有待审数据")
def batch_review(action: str = "approve", current_user=Depends(require_admin), db: Session = Depends(get_db)):
    """批量把所有 pending 数据审为 approved/rejected（官方源可信度高时快速过审）。"""
    status = "approved" if action == "approve" else "rejected"
    docs = db.execute(
        select(KnowledgeDoc).where(KnowledgeDoc.review_status == "pending")
    ).scalars().all()
    for d in docs:
        d.review_status = status
    db.commit()
    return {"ok": True, "count": len(docs), "review_status": status}


class DocUpdateReq(BaseModel):
    doc_id: int
    content: Optional[str] = None
    ai_summary: Optional[str] = None
    category_code: Optional[str] = None
    province: Optional[str] = None
    publish_date: Optional[str] = None


@router.post("/doc/update", summary="补充/更新文档字段(质量提升)")
def update_doc(req: DocUpdateReq, current_user=Depends(require_admin), db: Session = Depends(get_db)):
    """补充低质量文档的缺失字段（正文/摘要/分类/省份/日期），保存后重算缺失项返回。"""
    d = db.get(KnowledgeDoc, req.doc_id)
    if not d:
        raise HTTPException(status_code=404, detail="文档不存在")
    if req.content is not None:
        d.content = req.content
    if req.ai_summary is not None:
        d.ai_summary = req.ai_summary
    if req.category_code is not None:
        d.category_code = req.category_code
    if req.province is not None:
        d.province = req.province
    if req.publish_date is not None:
        d.publish_date = req.publish_date
    db.commit()
    return {"ok": True, "doc_id": d.id, "missing": _missing_fields(d)}


@router.get("/review/pending", summary="待审核列表")
def pending_review(page: int = 1, page_size: int = 20, current_user=Depends(require_admin), db: Session = Depends(get_db)):
    """待审核数据队列（外部爬虫/API/RSS 进来的数据可设为pending先审核）。"""
    stmt = select(KnowledgeDoc).where(KnowledgeDoc.review_status == "pending")
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    stmt = stmt.order_by(*knowledge_doc_order_by()).offset((page - 1) * page_size).limit(page_size)
    items = db.execute(stmt).scalars().all()
    return {"total": total, "items": [_doc_brief(d) for d in items]}


def _doc_brief(d: KnowledgeDoc) -> dict:
    import json
    return {
        "id": d.id, "title": d.title, "doc_type": d.doc_type,
        "province": d.province, "ingest_type": d.ingest_type,
        "source": d.source, "source_url": d.source_url, "ai_summary": d.ai_summary,
        "publish_date": d.publish_date,
        "review_status": getattr(d, "review_status", "approved"),
        "quality_score": getattr(d, "quality_score", None),
        "ref_count": getattr(d, "ref_count", 0),
        "tags": json.loads(d.tags) if d.tags else None,
    }
