"""FastAPI 应用入口。

启动：uvicorn app.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings, ensure_dirs
from app.common.logging_security import install_sensitive_log_filter
from app.db.database import init_db
from app.admin.router import router as admin_router
from app.exam.router import router as exam_router
from app.knowledge.router import router as knowledge_router
from app.knowledge.admin_router import router as asset_router
from app.knowledge.category_router import router as category_router
from app.learn.router import router as learn_router
from app.policy.router import router as policy_router
from app.portal import router as portal_router
from app.study.router import router as study_router
from app.study.book_router import router as study_book_router
from app.trade.router import router as trade_router
from app.auth.router import router as auth_router
from app.ai.assistant_router import router as ai_router
from app.ai.eval_router import router as ai_eval_router
from app.eval.eval_router import router as eval_router
from app.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表、建目录。"""
    # 让爬虫日志(crawler.*)输出到 stdout → 后端日志文件，方便排查抓取明细
    import logging
    _cl = logging.getLogger("crawler")
    _cl.setLevel(logging.INFO)
    if not _cl.handlers:
        _h = logging.StreamHandler()
        _h.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(message)s"))
        _cl.addHandler(_h)
        _cl.propagate = False
    install_sensitive_log_filter()
    ensure_dirs()
    init_db()
    # 灌入种子数据（首次启动）
    _seed_if_empty()
    # 启动爬虫定时调度器
    try:
        from crawlers.scheduler import init_scheduler
        init_scheduler()
    except Exception as e:
        import logging
        logging.getLogger("crawler").warning(f"调度器启动失败(不影响主功能): {e}")
    # 预热 embedding 模型：把冷启动(约3.5s)挪到服务启动时，避免用户首次AI问答同步等待→超时
    try:
        import threading
        from app.knowledge.embedding import get_embedder
        threading.Thread(target=get_embedder, daemon=True).start()
    except Exception as e:
        import logging
        logging.getLogger("vector_kb").warning(f"embedding预热失败(不影响主功能): {e}")
    yield


settings.validate_production_security()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="电力行业交易模拟系统 —— 学习 / 刷题 / 政策 / 模拟交易",
    lifespan=lifespan,
    debug=settings.DEBUG and not settings.is_production,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

if settings.is_production:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

# CORS：允许前端开发地址访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)

# 挂载路由
app.include_router(auth_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
app.include_router(ai_eval_router, prefix="/api")
app.include_router(eval_router, prefix="/api")
app.include_router(portal_router, prefix="/api")
app.include_router(health_router, prefix="/api")
app.include_router(learn_router, prefix="/api")
app.include_router(policy_router, prefix="/api")
app.include_router(trade_router, prefix="/api")
app.include_router(exam_router, prefix="/api")
app.include_router(study_router, prefix="/api")
app.include_router(study_book_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(asset_router, prefix="/api")
app.include_router(category_router, prefix="/api")
app.include_router(admin_router, prefix="/api")


@app.get("/", tags=["健康"])
def root():
    return {"app": settings.APP_NAME, "version": settings.APP_VERSION, "status": "running"}


@app.get("/health", tags=["健康"])
def health():
    return {"status": "ok"}


def _seed_if_empty():
    """首次启动时灌入种子数据：知识点、市场品种、示例政策/题目。"""
    from app.db.database import SessionLocal
    from app.db.models import (
        ExamBlueprint,
        ExamWeight,
        KnowledgePoint,
        Policy,
        Question,
        TradeMarket,
    )

    db = SessionLocal()
    try:
        # 知识点树（对齐国家职业标准的8大模块）
        if db.execute(select(KnowledgePoint)).scalars().first() is None:
            _seed_knowledge_points(db)

        # 市场品种
        if db.execute(select(TradeMarket)).scalars().first() is None:
            _seed_markets(db)

        # 示例题目（若飞书题库还没导入，先放几道让刷题能跑）
        if db.execute(select(Question)).scalars().first() is None:
            _seed_sample_questions(db)

        # 历年真题（独立判断，补真题标记题）
        from app.db.models import Question as _Q
        has_real = db.execute(select(_Q).where(_Q.is_real_exam.is_(True))).scalars().first()
        if has_real is None:
            _seed_real_exam_questions(db)

        # 示例政策（若还没导入基线，先放几条让新闻流能展示）
        if db.execute(select(Policy)).scalars().first() is None:
            _seed_sample_policies(db)

        # 考试蓝图 + 考点权重（对齐2024国家职业标准真实占比）
        if db.execute(select(ExamBlueprint)).scalars().first() is None:
            _seed_exam_blueprint(db)

        # 省份配置（支撑主省份深入+对比）
        from app.db.models import ProvinceConfig as _PC
        if db.execute(select(_PC)).scalars().first() is None:
            _seed_provinces(db)

        # 知识库沉淀种子（演示文档+公共数据）
        from app.db.models import KnowledgeDoc as _KD
        if db.execute(select(_KD)).scalars().first() is None:
            _seed_knowledge(db)

        # 分类树（电力市场完整分类体系，8章）
        from app.db.models import CategoryNode as _CN
        if db.execute(select(_CN)).scalars().first() is None:
            _seed_categories(db)
    finally:
        db.close()


def _seed_knowledge_points(db):
    """知识点体系树。"""
    from app.db.models import KnowledgePoint

    tree = [
        ("行业认知", "industry", None, "电力行业整体认知：发输配用、市场主体"),
        ("批发市场", "wholesale", None, "发电企业与售电公司/大用户间的交易"),
        ("零售市场", "retail", None, "售电公司与终端用户的交易"),
        ("中长期交易", "mid_long_term", None, "年度/月度/月内，双边协商/集中竞价/挂牌"),
        ("现货市场", "spot", None, "日前/实时市场，节点电价LMP"),
        ("辅助服务", "ancillary", None, "调频、备用、黑启动"),
        ("绿电绿证", "green", None, "绿色电力交易与绿证"),
        ("结算与信用", "settlement", None, "电费结算、偏差考核、信用管理"),
    ]
    for i, (name, code, _parent, desc) in enumerate(tree):
        db.add(KnowledgePoint(name=name, code=code, level=1, sort=i, description=desc))
    db.commit()


def _seed_markets(db):
    """交易品种。"""
    from app.db.models import TradeMarket

    markets = [
        ("mid_long_term", "中长期交易"),
        ("day_ahead", "日前现货"),
        ("realtime", "实时现货"),
        ("freq", "调频辅助服务"),
        ("green", "绿电交易"),
    ]
    for product, label in markets:
        db.add(TradeMarket(product=product, product_label=label))
    db.commit()


def _seed_sample_questions(db):
    """示例题目（飞书题库导入前的占位，让刷题可用）。"""
    import json

    from app.db.models import KnowledgePoint, Question

    spot_kp = db.execute(select(KnowledgePoint).where(KnowledgePoint.code == "spot")).scalar_one()

    samples = [
        {
            "type": "single",
            "stem": "在电力现货市场中，节点边际电价（LMP）由哪几部分组成？",
            "options": [
                {"key": "A", "text": "能量价格 + 损耗价格"},
                {"key": "B", "text": "能量价格 + 网损价格 + 阻塞价格", "is_correct": True},
                {"key": "C", "text": "仅能量价格"},
                {"key": "D", "text": "阻塞价格 + 容量价格"},
            ],
            "answer": "B",
            "analysis": "LMP（Locational Marginal Price）= 系统边际能量价格 + 网损价格 + 阻塞价格，反映在某节点增加1单位负荷的边际成本。",
            "difficulty": 2,
        },
        {
            "type": "judge",
            "stem": "电力中长期交易是指年内及以上的电能交易。",
            "options": [
                {"key": "对", "text": "对", "is_correct": False},
                {"key": "错", "text": "错"},
            ],
            "answer": "错",
            "analysis": "中长期交易指较长时间跨度（年度、月度、月内多日）的电能交易，并非特指年内及以上。",
            "difficulty": 1,
        },
        {
            "type": "multiple",
            "stem": "下列哪些属于电力市场辅助服务？",
            "options": [
                {"key": "A", "text": "调频", "is_correct": True},
                {"key": "B", "text": "备用", "is_correct": True},
                {"key": "C", "text": "中长期电量交易"},
                {"key": "D", "text": "黑启动", "is_correct": True},
            ],
            "answer": "ABD",
            "analysis": "辅助服务包括一次调频、自动发电控制（AGC）、调峰、备用、无功调节、黑启动等；中长期电量交易属于电能交易，不属于辅助服务。",
            "difficulty": 2,
        },
        {
            "type": "single",
            "stem": "现货市场日前出清中，发电机组的报价曲线通常呈什么形态？",
            "options": [
                {"key": "A", "text": "随出力增加而单调递增", "is_correct": True},
                {"key": "B", "text": "随出力增加而单调递减"},
                {"key": "C", "text": "水平直线"},
                {"key": "D", "text": "随机波动"},
            ],
            "answer": "A",
            "analysis": "发电机组边际成本随出力增加而上升（高效机组先发、低效机组后发），因此报价曲线通常随出力增加而单调递增。",
            "difficulty": 3,
        },
    ]
    for s in samples:
        db.add(Question(
            type=s["type"], stem=s["stem"], options=json.dumps(s["options"], ensure_ascii=False),
            answer=s["answer"], analysis=s["analysis"], difficulty=s["difficulty"],
            knowledge_point_id=spot_kp.id, source="系统预置题库",
        ))
    db.commit()


def _seed_sample_policies(db):
    """示例政策（飞书基线导入前的占位，让新闻流可用）。"""
    from app.db.models import Policy
    import hashlib

    samples = [
        {
            "title": "国务院办公厅关于完善全国统一电力市场体系的实施意见",
            "publish_date": "2026-02-11",
            "doc_number": "国办发〔2026〕4号",
            "category": "national",
            "province": None,
            "content": "推动全国统一电力市场体系建设，健全多层次统一电力市场架构...",
            "priority": 2,
        },
        {
            "title": "国家发改委办公厅 国家能源局综合司关于建立全国统一电力市场评价制度的通知",
            "publish_date": "2025-12-17",
            "doc_number": "发改办体改〔2025〕1032号",
            "category": "national",
            "province": None,
            "content": "建立电力市场建设成效评价机制...",
            "priority": 1,
        },
        {
            "title": "浙江电力交易中心7月月度中长期交易公告",
            "publish_date": "2026-07-14",
            "doc_number": None,
            "category": "market",
            "province": "浙江",
            "content": "交易品种：月度中长期；申报截止时间7月20日...",
            "priority": 0,
        },
        {
            "title": "山西电力现货市场日前出清结果",
            "publish_date": "2026-07-15",
            "doc_number": None,
            "category": "clearing",
            "province": "山西",
            "content": "日前现货均价0.314元/kWh...",
            "priority": 0,
        },
    ]
    for s in samples:
        dedup = hashlib.md5(f"{s['title']}|{s['publish_date']}".encode()).hexdigest()
        db.add(Policy(
            title=s["title"], publish_date=s["publish_date"], doc_number=s.get("doc_number"),
            category=s["category"], province=s.get("province"), source="国务院/国家发改委",
            content=s["content"], priority=s["priority"], dedup_key=dedup, is_read=False,
        ))
    db.commit()


def _seed_exam_blueprint(db):
    """考试蓝图 + 考点权重（对齐2024国家职业标准真实占比）。

    题型配比：单选100×0.5 + 多选30×1 + 判断40×0.5 = 100分（已核实）。
    各模块权重参考国家职业标准「理论知识权重表」中级工一列。
    """
    import json

    from app.db.models import ExamBlueprint, ExamWeight, KnowledgePoint

    # 真实统考题型配比
    type_config = {
        "single": {"count": 100, "score": 0.5, "label": "单选题"},
        "multiple": {"count": 30, "score": 1.0, "label": "多选题"},
        "judge": {"count": 40, "score": 0.5, "label": "判断题"},
    }

    # 中级工 / 高级工 两个蓝图
    for level, label in [("four", "中级工理论"), ("three", "高级工理论")]:
        bp = ExamBlueprint(
            name=label, level=level,
            type_config=json.dumps(type_config, ensure_ascii=False),
            total_score=100.0, pass_score=60.0, duration_min=90,
            is_active=True,
        )
        db.add(bp)
    db.commit()

    # 各知识模块权重（参考国家职业标准中级工权重表，合计约100%）
    # 模块名 + 知识点code + 权重%
    points = {p.code: p for p in db.execute(select(KnowledgePoint)).scalars().all() if p.code}
    weights_four = [
        ("职业道德与基础知识", "industry", 15),
        ("批发市场交易", "wholesale", 10),
        ("零售市场交易", "retail", 10),
        ("中长期交易", "mid_long_term", 20),
        ("现货市场交易", "spot", 20),
        ("辅助服务", "ancillary", 10),
        ("绿电绿证交易", "green", 5),
        ("结算与信用管理", "settlement", 10),
    ]
    for module_name, kp_code, weight in weights_four:
        kp = points.get(kp_code)
        # 预测加成：现货/结算/绿电是政策活跃区，适度加权
        boost = 0.0
        if kp_code in ("spot", "settlement"):
            boost = 3.0  # 现货和结算是近年政策密集区
        elif kp_code == "green":
            boost = 2.0  # 绿电绿证政策推进快
        db.add(ExamWeight(
            blueprint_id=1, knowledge_point_id=kp.id if kp else None,
            module_name=module_name, weight_pct=weight, level="four",
            prediction_boost=boost,
        ))
    db.commit()


def _seed_real_exam_questions(db):
    """历年真题种子（带年份+级别标记）。

    题目基于调研到的真实考点（偏差结算、市场力、LMP、输电权等），
    标注真题年份与级别，供"历年真题"入口使用。
    中级(four)为主，高级(three)可选。
    """
    import hashlib
    import json

    from app.db.models import KnowledgePoint, Question

    points = {p.code: p for p in db.execute(select(KnowledgePoint)).scalars().all() if p.code}

    # 真题数据：(年份, 级别, 题型, 知识点code, 题干, 选项, 答案, 解析, 难度, 预测标签)
    real_questions = [
        # ===== 2024 中级真题 =====
        (2024, "four", "single", "settlement",
         "电力中长期交易中，偏差电量结算通常采用以下哪种方式？",
         [{"key": "A", "text": "按合同价全额结算"}, {"key": "B", "text": "按现货价格结算偏差部分", "is_correct": True},
          {"key": "C", "text": "不结算偏差"}, {"key": "D", "text": "按月度均价结算"}],
         "B", "偏差电量指实际用电量与合同电量之差，超出免赔范围的部分按现货市场价格结算，激励市场主体精准预测。", 2, ["高频"]),
        (2024, "four", "single", "spot",
         "现货市场中，节点边际电价（LMP）反映的是？",
         [{"key": "A", "text": "发电厂的报价"}, {"key": "B", "text": "某节点增加1单位负荷的边际成本", "is_correct": True},
          {"key": "C", "text": "系统的平均电价"}, {"key": "D", "text": "输配电价"}],
         "B", "LMP = 能量价格 + 网损价格 + 阻塞价格，反映在特定节点增加1单位负荷的边际供电成本。", 2, ["高频"]),
        (2024, "four", "judge", "mid_long_term",
         "中长期交易可以采取双边协商、集中竞价、挂牌交易等方式。",
         [{"key": "对", "text": "对", "is_correct": True}, {"key": "错", "text": "错"}],
         "对", "中长期交易支持双边协商、集中竞价、挂牌交易等多种方式，市场主体可自主选择。", 1, None),
        (2024, "four", "multiple", "ancillary",
         "下列哪些属于电力辅助服务？",
         [{"key": "A", "text": "调频", "is_correct": True}, {"key": "B", "text": "备用", "is_correct": True},
          {"key": "C", "text": "中长期电量交易"}, {"key": "D", "text": "黑启动", "is_correct": True}],
         "ABD", "辅助服务包括调频、备用、调峰、无功、黑启动等；中长期电量交易属于电能交易，不是辅助服务。", 2, None),
        (2024, "four", "single", "wholesale",
         "电力批发市场的交易主体通常包括？",
         [{"key": "A", "text": "发电企业与售电公司/大用户", "is_correct": True},
          {"key": "B", "text": "售电公司与居民用户"}, {"key": "C", "text": "电网企业与居民"}, {"key": "D", "text": "仅发电企业"}],
         "A", "批发市场是发电企业与售电公司、电力大用户之间的交易，零售市场才是售电公司与终端用户间。", 1, None),
        (2024, "four", "judge", "green",
         "绿色电力交易是指以绿色电力产品为标的物的电力交易。",
         [{"key": "对", "text": "对", "is_correct": True}, {"key": "错", "text": "错"}],
         "对", "绿电交易是以风电、光伏等可再生能源发电量为核心标的的交易，同时获得绿证。", 1, ["政策关联"]),
        (2024, "four", "single", "spot",
         "电力现货市场的阻塞盈余来源于？",
         [{"key": "A", "text": "发电厂利润"}, {"key": "B", "text": "节点电价差引起的结算差额", "is_correct": True},
          {"key": "C", "text": "输配电费"}, {"key": "D", "text": "政府补贴"}],
         "B", "当输电阻塞导致不同节点LMP不同，负荷侧按高价支付、发电侧按低价结算，差额即阻塞盈余。", 3, ["高频"]),

        # ===== 2023 中级真题 =====
        (2023, "four", "single", "settlement",
         "现货市场偏差电量结算中，用户侧实际用电量低于合同电量时，偏差电量按什么价格结算？",
         [{"key": "A", "text": "合同价"}, {"key": "B", "text": "现货价格", "is_correct": True},
          {"key": "C", "text": "中长期均价"}, {"key": "D", "text": "免于结算"}],
         "B", "无论正偏差还是负偏差，超出免赔范围的部分均按现货价格结算，体现「谁偏差谁承担」原则。", 2, ["高频"]),
        (2023, "four", "multiple", "spot",
         "电力现货市场出清的基本原则包括？",
         [{"key": "A", "text": "社会福利最大化", "is_correct": True}, {"key": "B", "text": "报价从低到高排序", "is_correct": True},
          {"key": "C", "text": "发电侧报价越高越优先成交"}, {"key": "D", "text": "满足系统约束", "is_correct": True}],
         "ABD", "现货出清按报价由低到高排序，在满足系统约束（潮流、备用等）前提下实现社会福利最大化。", 2, None),
        (2023, "four", "judge", "retail",
         "零售市场的交易主体是售电公司与终端电力用户。",
         [{"key": "对", "text": "对", "is_correct": True}, {"key": "错", "text": "错"}],
         "对", "零售市场指售电公司向终端用户售电的市场，与批发市场（发电-售电）相对应。", 1, None),
        (2023, "four", "single", "industry",
         "我国电力体制改革「管住中间、放开两头」中的「中间」指？",
         [{"key": "A", "text": "发电侧"}, {"key": "B", "text": "输配电环节", "is_correct": True},
          {"key": "C", "text": "售电侧"}, {"key": "D", "text": "用户侧"}],
         "B", "「管住中间」指对输配电价进行政府监管，「放开两头」指发电侧和售电侧引入竞争。", 1, None),

        # ===== 2024 高级真题（可选）=====
        (2024, "three", "single", "spot",
         "输电权交易的主要作用是？",
         [{"key": "A", "text": "增加发电利润"}, {"key": "B", "text": "对冲阻塞风险", "is_correct": True},
          {"key": "C", "text": "降低输电成本"}, {"key": "D", "text": "提高用电效率"}],
         "B", "输电权（FTR）允许持有者在阻塞时获得阻塞盈余补偿，对冲节点电价波动风险。这是近年新增考点。", 3, ["新增", "政策关联"]),
        (2024, "three", "multiple", "spot",
         "电力市场力抑制的主要手段包括？",
         [{"key": "A", "text": "市场份额限制", "is_correct": True}, {"key": "B", "text": "报价上限", "is_correct": True},
          {"key": "C", "text": "取消竞争"}, {"key": "D", "text": "行为监测", "is_correct": True}],
         "ABD", "抑制市场力包括市场份额限制、报价/价格上限、行为监测与监管，而非取消竞争。", 3, ["高频"]),
        (2024, "three", "single", "settlement",
         "现货市场中「影子价格」的经济含义是？",
         [{"key": "A", "text": "实际交易价格"}, {"key": "B", "text": "约束放松1单位带来的系统成本变化", "is_correct": True},
          {"key": "C", "text": "发电报价"}, {"key": "D", "text": "输配电价"}],
         "B", "影子价格是某约束（如输电容量）放松1单位时目标函数（总成本）的变化量，用于评估约束的经济影响。", 3, ["高频"]),

        # ===== 2023 高级真题 =====
        (2023, "three", "judge", "spot",
         "节点边际电价中，阻塞价格不可能为负值。",
         [{"key": "对", "text": "对"}, {"key": "错", "text": "错", "is_correct": True}],
         "错", "当某节点发电充裕而外送受阻时，该节点LMP可能低于系统边际价，阻塞分量可为负。", 3, None),
        (2023, "three", "single", "ancillary",
         "调频辅助服务市场中，性能最好的机组通常？",
         [{"key": "A", "text": "报价最高"}, {"key": "B", "text": "优先被调用", "is_correct": True},
          {"key": "C", "text": "不参与调频"}, {"key": "D", "text": "容量最大"}],
         "B", "调频市场按调节速率和性能排序，性能好（响应快）的机组优先调用。", 2, None),
    ]

    for year, level, qtype, kp_code, stem, options, answer, analysis, difficulty, tags in real_questions:
        kp = points.get(kp_code)
        stem_hash = hashlib.md5(stem.encode()).hexdigest()[:16]
        db.add(Question(
            type=qtype, stem=stem, options=json.dumps(options, ensure_ascii=False),
            answer=answer, analysis=analysis, difficulty=difficulty,
            knowledge_point_id=kp.id if kp else None,
            source=f"{year}年{level}真题",
            source_type="real_exam",
            is_real_exam=True, exam_year=year, exam_level=level,
            prediction_tags=json.dumps(tags, ensure_ascii=False) if tags else None,
            stem_hash=stem_hash,
        ))
    db.commit()


def _seed_provinces(db):
    """省份配置种子（基于调研：国网/南网/蒙西三套体系 + 现货试点批次）。

    支撑主省份深入 + 其他省份对比。
    """
    import json

    from app.db.models import ProvinceConfig

    provinces = [
        # 国网PXF体系
        {"name": "浙江", "code": "zj", "grid": "sgcc", "spot_pilot": "第一批", "spot_status": "已转正式运行",
         "platform_url": "https://zjpx.com.cn", "info_path": "/pxf-settlement-outnetpub-phbzj/",
         "rule_summary": "中长期+现货并行，现货已转正式运行。中长期含年度/月度/月内，现货日前+实时。",
         "differences": json.dumps(["现货已转正", "绿电交易用户破万"], ensure_ascii=False)},
        {"name": "山西", "code": "sx", "grid": "sgcc", "spot_pilot": "第一批", "spot_status": "已转正式运行",
         "platform_url": "https://pmos.sx.sgcc.com.cn", "info_path": "/pxf-settlement-outnetpub/",
         "rule_summary": "全国首个现货转正省份，日前均价约0.31元/kWh，现货市场最成熟。",
         "differences": json.dumps(["现货最成熟", "出清结果公开度高"], ensure_ascii=False)},
        {"name": "山东", "code": "sd", "grid": "sgcc", "spot_pilot": "第一批", "spot_status": "已转正式运行",
         "platform_url": "https://pmos.sd.sgcc.com.cn", "info_path": "/pxf-settlement-outnetpub/",
         "rule_summary": "现货已转正，日前均价约0.32元/kWh，新能源占比高导致价格波动大。",
         "differences": json.dumps(["新能源占比高", "价格波动大"], ensure_ascii=False)},
        {"name": "福建", "code": "fj", "grid": "sgcc", "spot_pilot": "第一批", "spot_status": "连续结算试运行",
         "platform_url": "https://pmos.fj.sgcc.com.cn", "info_path": "/pxf-settlement-outnetpub/",
         "rule_summary": "第一批现货试点，目前连续结算试运行阶段。",
         "differences": json.dumps(["试运行阶段", "规则仍在迭代"], ensure_ascii=False)},
        {"name": "四川", "code": "sc", "grid": "sgcc", "spot_pilot": "第一批", "spot_status": "连续结算试运行",
         "platform_url": "https://pmos.sc.sgcc.com.cn", "info_path": "/pxf-settlement-outnetpub/",
         "rule_summary": "水电占比高，丰枯期差异大，现货规则需适应水文特性。",
         "differences": json.dumps(["水电为主", "丰枯期电价差异极大"], ensure_ascii=False)},
        {"name": "上海", "code": "sh", "grid": "sgcc", "spot_pilot": "第二批", "spot_status": "连续结算试运行",
         "platform_url": "https://pmos.sh.sgcc.com.cn", "info_path": "/pxf-settlement-outnetpub/",
         "rule_summary": "第二批现货试点，信息公开栏目最清晰，PXF架构典型代表。",
         "differences": json.dumps(["第二批试点", "信息公开规范"], ensure_ascii=False)},
        {"name": "江苏", "code": "js", "grid": "sgcc", "spot_pilot": "第二批", "spot_status": "连续结算试运行",
         "platform_url": "https://pmos.js.sgcc.com.cn", "info_path": "/pxf-settlement-outnetpub/",
         "rule_summary": "第二批现货试点，用电大省，中长期交易量大。",
         "differences": json.dumps(["用电量大", "中长期交易活跃"], ensure_ascii=False)},
        {"name": "辽宁", "code": "ln", "grid": "sgcc", "spot_pilot": "第二批", "spot_status": "连续结算试运行",
         "platform_url": "https://pmos.ln.sgcc.com.cn", "info_path": "/pxf-settlement-outnetpub/",
         "rule_summary": "第二批现货试点，东北地区代表。",
         "differences": json.dumps(["东北代表", "供暖期影响大"], ensure_ascii=False)},
        # 南方电网体系
        {"name": "广东", "code": "gd", "grid": "csg", "spot_pilot": "第一批", "spot_status": "已转正式运行",
         "platform_url": "https://pm.gd.csg.cn", "info_path": "",
         "rule_summary": "南方电网体系，现货已转正，日前均价约0.35元/kWh。西电东送受端。",
         "differences": json.dumps(["南网体系(非PXF)", "西电东送受端", "现货均价较高"], ensure_ascii=False)},
        {"name": "云南", "code": "yn", "grid": "csg", "spot_pilot": None, "spot_status": "推进中",
         "platform_url": "https://pm.yn.csg.cn", "info_path": "",
         "rule_summary": "南网体系，水电大省，西电东送送端，丰水期外送量大。",
         "differences": json.dumps(["水电外送大省", "南网体系"], ensure_ascii=False)},
        # 蒙西
        {"name": "蒙西", "code": "mxi", "grid": "impc", "spot_pilot": "第一批", "spot_status": "已转正式运行",
         "platform_url": "https://www.impc.com.cn", "info_path": "",
         "rule_summary": "内蒙古电力集团独立运营（非国网非南网），多边交易市场，现货已转正。",
         "differences": json.dumps(["独立电网体系", "多边交易市场", "风电占比高"], ensure_ascii=False)},
    ]

    for p in provinces:
        db.add(ProvinceConfig(**p))
    db.commit()


def _seed_knowledge(db):
    """知识库沉淀种子：文档 + 公共数据，演示分类检索能力。"""
    import hashlib
    import json

    from app.db.models import KnowledgeDoc, KnowledgePoint, PublicData

    points = {p.code: p for p in db.execute(select(KnowledgePoint)).scalars().all() if p.code}

    docs = [
        {
            "title": "国务院办公厅关于完善全国统一电力市场体系的实施意见",
            "doc_type": "national_policy", "province": None, "region": None,
            "publish_date": "2026-02-11", "doc_number": "国办发〔2026〕4号",
            "source": "中国政府网", "source_url": "https://www.gov.cn/zhengce/",
            "content": "推动全国统一电力市场体系建设，健全多层次统一电力市场架构，完善交易机制...",
            "ai_summary": "统一电力市场建设的顶层设计文件，明确多层次市场架构、交易品种、价格机制。",
            "ai_keywords": ["统一电力市场", "市场架构", "交易机制"],
            "knowledge_point_code": "industry",
            "tags": ["顶层设计", "里程碑"],
        },
        {
            "title": "浙江电力交易中心2026年7月月度中长期交易公告",
            "doc_type": "exchange_info", "province": "浙江", "grid": "sgcc",
            "publish_date": "2026-07-10", "source": "浙江电力交易中心",
            "source_url": "https://zjpx.com.cn",
            "content": "交易品种：月度中长期；交易方式：双边协商+集中竞价；申报截止7月15日...",
            "ai_summary": "浙江7月中长期月度交易组织安排，含交易品种、申报时间、出清方式。",
            "ai_keywords": ["中长期", "月度交易", "双边协商"],
            "knowledge_point_code": "mid_long_term",
            "tags": ["浙江", "月度交易"],
        },
        {
            "title": "山西电力现货市场2026年二季度运行分析报告",
            "doc_type": "industry_news", "province": "山西", "grid": "sgcc",
            "publish_date": "2026-07-05", "source": "山西电力交易中心",
            "content": "二季度现货日前均价0.318元/kWh，新能源占比提升至28%...",
            "ai_summary": "山西现货市场二季度运行情况：日前均价0.318元，新能源占比28%创新高。",
            "ai_keywords": ["现货", "出清价格", "新能源"],
            "knowledge_point_code": "spot",
            "tags": ["山西", "运行分析", "现货"],
        },
        {
            "title": "国家能源局综合司关于公开征求《电力辅助服务市场基本规则》意见",
            "doc_type": "national_policy", "province": None,
            "publish_date": "2026-06-20", "doc_number": None,
            "source": "国家能源局", "source_url": "https://www.nea.gov.cn",
            "content": "规范电力辅助服务市场建设，明确调频、备用、爬坡等服务交易机制...",
            "ai_summary": "辅助服务市场基本规则征求意见，统一调频/备用/爬坡等交易机制。",
            "ai_keywords": ["辅助服务", "调频", "备用", "市场规则"],
            "knowledge_point_code": "ancillary",
            "tags": ["征求意见", "辅助服务", "新增考点"],
        },
        {
            "title": "2026年上半年全国绿色电力交易情况通报",
            "doc_type": "industry_news", "province": None,
            "publish_date": "2026-07-12", "source": "中国电力企业联合会",
            "content": "上半年绿电交易电量同比增长65%，绿证核发量突破1亿个...",
            "ai_summary": "上半年绿电交易大幅增长65%，绿证核发破亿，绿电市场快速扩张。",
            "ai_keywords": ["绿电", "绿证", "增长"],
            "knowledge_point_code": "green",
            "tags": ["绿电", "通报", "增长"],
        },
        {
            "title": "国家能源局华北监管局关于印发《华北区域电力市场运营规则》的通知",
            "doc_type": "regulation", "region": "华北", "province": None,
            "publish_date": "2026-05-15", "source": "华北能源监管局",
            "source_url": "http://hbj.nea.gov.cn",
            "content": "华北区域电力市场运营规则，含中长期、现货、辅助服务衔接机制...",
            "ai_summary": "华北区域市场运营规则，规范中长期/现货/辅助服务衔接。",
            "ai_keywords": ["华北", "运营规则", "市场衔接"],
            "knowledge_point_code": "wholesale",
            "tags": ["华北", "运营规则"],
        },
    ]

    for d in docs:
        dedup = hashlib.md5(f"{d['title']}|{d.get('publish_date','')}".encode()).hexdigest()[:16]
        kp = points.get(d.get("knowledge_point_code", ""))
        db.add(KnowledgeDoc(
            title=d["title"], doc_type=d["doc_type"],
            province=d.get("province"), region=d.get("region"), grid=d.get("grid"),
            publish_date=d.get("publish_date"), doc_number=d.get("doc_number"),
            source=d.get("source"), source_url=d.get("source_url"),
            content=d.get("content"), ai_summary=d.get("ai_summary"),
            ai_keywords=json.dumps(d.get("ai_keywords", []), ensure_ascii=False),
            knowledge_point_id=kp.id if kp else None,
            tags=json.dumps(d.get("tags", []), ensure_ascii=False),
            dedup_key=dedup,
        ))

    # 公共数据种子（出清价格）。固定基准日和值，确保所有干净环境首次启动一致。
    # 这些记录始终标记 synthetic / internal，不能当作真实市场行情使用。
    seed_anchor = date(2026, 1, 7)
    provinces_data = [
        ("山西", "day_ahead", 302.5, 9200),
        ("山东", "day_ahead", 318.4, 11300),
        ("广东", "day_ahead", 336.8, 13700),
    ]
    for prov, prod, base_price, base_load in provinces_data:
        for days_ago in range(7):
            d = (seed_anchor - timedelta(days=days_ago)).isoformat()
            price = round(base_price + days_ago * 2.7, 1)
            load = base_load + days_ago * 180
            dedup = hashlib.md5(f"clearing|{prov}|{d}".encode()).hexdigest()[:16]
            db.add(PublicData(
                data_type="clearing", province=prov, data_date=d,
                metrics=json.dumps({
                    "clearing_price": price,
                    "load": load,
                    "product": prod,
                    "provenance_level": "synthetic",
                    "disclosure_scope": "internal",
                }),
                source="系统种子数据", dedup_key=dedup,
            ))
    db.commit()


# select 在模块级被种子函数用，提前导入避免循环引用
from sqlalchemy import select  # noqa: E402
from datetime import date, timedelta  # noqa: E402


def _seed_categories(db):
    """初始化电力市场完整分类树（8章，基于权威口径调研）。"""
    from app.db.models import CategoryNode
    from app.knowledge.categories import flatten_tree

    nodes = flatten_tree()
    for i, n in enumerate(nodes):
        db.add(CategoryNode(
            code=n["code"], name=n["name"], parent_code=n.get("parent_code"),
            level=n["level"], facet=n.get("facet", "chapter"),
            icon=n.get("icon", ""), sort=i,
            description=f"{n['name']} - 电力市场分类节点",
        ))
    db.commit()
