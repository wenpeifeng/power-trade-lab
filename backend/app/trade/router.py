"""交易模拟模块路由。

数据策略：
- 优先从 PublicData 读取出清价/负荷时序，并保留真实来源等级
- 无数据时降级合成，并标注 data_source = "synthetic"
- 支持历史日期回放（trade_date 参数）
- 提供可用日期列表，前端可切换历史回放
"""
import json
import hashlib
import logging
import math
import random
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import (
    PublicData,
    SimulationSession,
    TradeAccount,
    TradeMarket,
    TradeOrder,
    TradePosition,
    TradeTrade,
    User,
)
from app.common.auth import get_current_user
from app.trade.simulation import (
    ENGINE_VERSION,
    RULES_VERSION,
    SCENARIOS,
    BidValidationError,
    build_review,
    run_clearing,
    run_settlement,
    validate_bid_schedule,
)

logger = logging.getLogger("trade")
router = APIRouter(prefix="/trade", tags=["交易模拟"])


class CreateSimulationReq(BaseModel):
    scenario_code: str
    province: str = "山西"
    trade_date: Optional[str] = None


class SimulationBidsReq(BaseModel):
    bids: list[dict]


@router.get("/markets", summary="交易品种列表")
def list_markets(db: Session = Depends(get_db)):
    markets = db.execute(
        select(TradeMarket).where(TradeMarket.is_open.is_(True)).order_by(TradeMarket.id)
    ).scalars().all()
    return [
        {
            "id": m.id,
            "product": m.product,
            "product_label": m.product_label,
            "province": m.province,
        }
        for m in markets
    ]


@router.get("/quote", summary="行情数据(附来源等级)")
def get_quote(
    market_id: int,
    trade_date: Optional[str] = Query(None, description="历史回放日期 YYYY-MM-DD，默认最新"),
    province: Optional[str] = Query(None, description="省份覆盖(前端切换省份用)"),
    db: Session = Depends(get_db),
):
    """获取行情数据。

    数据来源优先级：
    1. PublicData 表中该省份的出清价/负荷
    2. 降级合成（标注 synthetic）

    返回 provenance_level 标注来源等级。无法证明是原始观测的旧数据
    默认按 reconstructed 处理，避免把重构曲线误标为真实数据。
    """
    market = db.get(TradeMarket, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="市场不存在")

    # 省份优先级：URL参数 > 市场绑定 > 默认山西(现货首批数据最全)
    province = province or market.province or "山西"

    # 优先从 PublicData 取已归档数据；是否为真实观测由 provenance_level 决定。
    archived_data = _load_public_quote(db, province, trade_date)
    if archived_data:
        archived_data["market_id"] = market_id
        archived_data["product"] = market.product
        archived_data["province"] = province
        return archived_data

    # 降级：合成数据
    logger.info(f"[trade] {province} 无已归档行情(trade_date={trade_date})，降级合成")
    prices = _synth_price_curve(province, trade_date)
    loads = [round(p * 2.0 + random.uniform(-50, 50), 0) for p in prices]
    clearing = round(sum(prices) / len(prices), 1)
    return {
        "market_id": market_id,
        "product": market.product,
        "province": province,
        "trade_date": trade_date or date.today().isoformat(),
        "clearing_price": clearing,
        "data_source": "synthetic",
        "provenance_level": "synthetic",
        "source_name": "模拟推算",
        "source_note": "基于该省历史真实价格区间推算，非实时交易数据",
        "time_series": [
            {
                "time": f"{i // 4:02d}:{(i % 4) * 15:02d}",
                "price": prices[i],
                "load": loads[i],
            }
            for i in range(96)
        ],
    }


@router.get("/available-dates", summary="可回放的历史日期列表")
def available_dates(
    market_id: int,
    province: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """返回该市场有已归档行情的可用日期，供前端历史回放切换。"""
    market = db.get(TradeMarket, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="市场不存在")
    province = province or market.province or "山西"

    rows = db.execute(
        select(PublicData.data_date)
        .where(PublicData.data_type == "clearing", PublicData.province == province)
        .order_by(PublicData.data_date.desc())
        .limit(30)
    ).scalars().all()
    return {"province": province, "dates": list(rows)}


def _load_public_quote(db: Session, province: Optional[str], trade_date: Optional[str]) -> Optional[dict]:
    """从 PublicData 加载已归档的出清价和负荷。

    优先选带 96 点 curve 的记录，避免命中只有均价的旧种子数据。
    数据是否为原始观测由 provenance_level 单独标记。
    """
    # 查出清价：优先带 curve 的，按日期降序
    clearing_q = select(PublicData).where(
        PublicData.data_type == "clearing", PublicData.province == province
    )
    if trade_date:
        clearing_q = clearing_q.where(PublicData.data_date == trade_date)
    # 取最近的多条，在 Python 层挑选带 curve 的
    clearing_rows = db.execute(
        clearing_q.order_by(PublicData.data_date.desc()).limit(10)
    ).scalars().all()
    clearing_row = None
    for r in clearing_rows:
        m = json.loads(r.metrics)
        if m.get("curve") and len(m["curve"]) >= 96:
            clearing_row = r
            break
    if not clearing_row and clearing_rows:
        clearing_row = clearing_rows[0]  # 兜底取最新
    if not clearing_row:
        return None

    c_metrics = json.loads(clearing_row.metrics)
    curve = c_metrics.get("curve", [])

    # 查同日负荷（同样优先带 curve 的）
    load_rows = db.execute(
        select(PublicData).where(
            PublicData.data_type == "load",
            PublicData.province == province,
            PublicData.data_date == clearing_row.data_date,
        ).limit(5)
    ).scalars().all()
    load_curve = []
    for lr in load_rows:
        lm = json.loads(lr.metrics)
        if lm.get("curve") and len(lm["curve"]) >= 96:
            load_curve = lm["curve"]
            break

    # 组装96点
    time_series = []
    for i in range(96):
        point = {
            "time": f"{i // 4:02d}:{(i % 4) * 15:02d}",
            "price": curve[i] if i < len(curve) else None,
            "load": load_curve[i] if i < len(load_curve) else None,
        }
        time_series.append(point)

    provenance_level = _infer_provenance(clearing_row, c_metrics)
    return {
        "trade_date": clearing_row.data_date,
        "clearing_price": c_metrics.get("clearing_price") or (round(sum(curve) / len(curve), 1) if curve else None),
        "peak_price": c_metrics.get("peak_price") or (round(max(curve), 1) if curve else None),
        "valley_price": c_metrics.get("valley_price") or (round(min(curve), 1) if curve else None),
        # data_source 暂保留兼容旧前端；新代码统一使用 provenance_level。
        "data_source": provenance_level,
        "provenance_level": provenance_level,
        "disclosure_scope": c_metrics.get("disclosure_scope", "public"),
        "source_name": clearing_row.source or _province_source_name(province),
        "source_note": c_metrics.get("params_note", ""),
        "time_series": time_series,
    }


def _infer_provenance(row: PublicData, metrics: dict) -> str:
    """判断公共数据来源等级，宁可保守标注，也不冒充原始观测。

    新数据应显式写入 provenance_level。旧数据没有该字段时：
    - 含“构建/推算/模拟”等来源描述 → reconstructed
    - 当前仓库历史数据均缺少原始响应与哈希，默认 reconstructed
    """
    explicit = metrics.get("provenance_level")
    allowed = {"observed_public", "observed_authorized", "reconstructed", "synthetic"}
    if explicit in allowed:
        return explicit

    source_text = f"{row.source or ''} {metrics.get('params_note', '')}"
    if any(marker in source_text for marker in ("构建", "推算", "模拟", "典型曲线", "价格区间")):
        return "reconstructed"
    return "reconstructed"


def _province_source_name(province: Optional[str]) -> str:
    """根据省份返回对应电力交易中心名称。"""
    mapping = {
        "山西": "山西电力交易中心",
        "山东": "山东电力交易中心",
        "广东": "广东电力交易中心",
        "浙江": "浙江电力交易中心",
        "蒙西": "内蒙古电力交易中心",
    }
    return mapping.get(province, "电力交易中心")


def _synth_price_curve(province: Optional[str], trade_date: Optional[str]) -> list[float]:
    """合成价格曲线（兜底）。不同省份用不同参数。"""
    from crawlers.adapters.market_data import PROVINCE_PARAMS
    params = PROVINCE_PARAMS.get(province) or next(iter(PROVINCE_PARAMS.values()))
    lo, hi = params["price_range"]
    mc, mw = params["peak_morning"]
    ec, ew = params["peak_evening"]
    seed_str = trade_date or date.today().isoformat()
    rng = random.Random(sum(ord(c) for c in seed_str))
    prices = []
    for i in range(96):
        hour = i / 4.0
        morning = (hi - lo) * 0.4 * math.exp(-((hour - mc) ** 2) / (2 * mw ** 2))
        evening = (hi - lo) * 0.5 * math.exp(-((hour - ec) ** 2) / (2 * ew ** 2))
        base = lo + (hi - lo) * 0.25
        noise = rng.uniform(-(hi - lo) * 0.05, (hi - lo) * 0.05)
        p = max(lo, min(hi, base + morning + evening + noise))
        prices.append(round(p, 1))
    return prices


def _gauss_bump(x: float, center: float, width: float) -> float:
    return math.exp(-((x - center) ** 2) / (2 * width ** 2))


@router.get("/account", summary="模拟账户")
def get_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acc = db.execute(select(TradeAccount).where(TradeAccount.user_id == current_user.id)).scalars().first()
    if not acc:
        acc = TradeAccount(user_id=current_user.id)
        db.add(acc)
        db.commit()
        db.refresh(acc)
    return {
        "balance": acc.balance,
        "frozen": acc.frozen,
        "available": acc.balance - acc.frozen,
    }


@router.post("/order", summary="提交申报")
def submit_order(
    market_id: int,
    side: str,
    bid_curve: list[dict],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交申报。当前按加权均价撮合成交。

    bid_curve: [{"price":320,"volume":500}, ...]
    """
    if side not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="side 必须是 buy 或 sell")
    if not bid_curve:
        raise HTTPException(status_code=400, detail="bid_curve 不能为空")

    market = db.get(TradeMarket, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="市场不存在")

    total_volume = sum(b.get("volume", 0) for b in bid_curve)
    avg_price = (
        sum(b["price"] * b["volume"] for b in bid_curve) / total_volume if total_volume else 0
    )

    order = TradeOrder(
        user_id=current_user.id, market_id=market_id, side=side,
        bid_curve=json.dumps(bid_curve, ensure_ascii=False),
        total_volume=total_volume, status="pending",
    )
    db.add(order)
    db.flush()

    # 撮合引擎
    from app.trade.matching import match_order
    fill_volume, fill_price = match_order(db, order, market, avg_price, total_volume)

    trade = TradeTrade(
        user_id=current_user.id, market_id=market_id, order_id=order.id, side=side,
        price=fill_price, volume=fill_volume, clearing_price=fill_price,
    )
    order.status = "filled"
    db.add(trade)
    db.commit()

    return {
        "order_id": order.id,
        "status": order.status,
        "filled_volume": fill_volume,
        "filled_price": fill_price,
        "trade_id": trade.id,
    }


@router.get("/positions", summary="持仓与成交")
def get_positions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    trades = db.execute(
        select(TradeTrade).where(TradeTrade.user_id == current_user.id).order_by(TradeTrade.id.desc()).limit(50)
    ).scalars().all()
    return {
        "trades": [
            {
                "id": t.id, "side": t.side, "price": t.price,
                "volume": t.volume, "clearing_price": t.clearing_price,
                "trade_time": t.trade_time,
            }
            for t in trades
        ]
    }


# ============ 订单簿盘口 ============

@router.get("/orderbook", summary="订单簿盘口(买卖深度)")
def get_orderbook(
    market_id: int,
    depth: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回买卖盘口深度数据，供前端展示五档/十档行情。"""
    market = db.get(TradeMarket, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="市场不存在")
    from app.trade.matching import get_orderbook_depth
    return get_orderbook_depth(db, market, depth)


# ============ 交易复盘报告 ============

@router.get("/review", summary="交易复盘报告")
def trade_review(
    market_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """复盘：对比你的报价 vs 市场出清价，分析策略得失。

    核心价值：让用户理解"报得高/低对成交的影响"，
    形成真实的电力交易策略认知。
    """
    market = db.get(TradeMarket, market_id)
    if not market:
        raise HTTPException(status_code=404, detail="市场不存在")

    # 拿用户最近的成交记录
    trades = db.execute(
        select(TradeTrade).where(
            TradeTrade.user_id == current_user.id,
            TradeTrade.market_id == market_id,
        ).order_by(TradeTrade.id.desc()).limit(20)
    ).scalars().all()

    # 拿用户最近的申报
    orders = db.execute(
        select(TradeOrder).where(
            TradeOrder.user_id == current_user.id,
            TradeOrder.market_id == market_id,
        ).order_by(TradeOrder.id.desc()).limit(20)
    ).scalars().all()

    # 获取市场出清价基准
    from app.trade.matching import _get_market_clearing_price
    province = market.province or "山西"
    market_clearing = _get_market_clearing_price(db, province, market_id)

    # 分析每笔申报的策略得失
    analysis = []
    for o in orders:
        curve = json.loads(o.bid_curve) if o.bid_curve else []
        if not curve:
            continue
        avg_bid = sum(b["price"] * b["volume"] for b in curve) / max(
            sum(b.get("volume", 0) for b in curve), 1)
        # 对比出清价
        if o.side == "buy":
            advice = "报价高于出清价，竞争力强" if avg_bid >= market_clearing else "报价低于出清价，可能抢不到量"
            cost_saving = (avg_bid - market_clearing) * o.total_volume
        else:
            advice = "报价低于出清价，容易成交" if avg_bid <= market_clearing else "报价高于出清价，可能卖不掉"
            cost_saving = (market_clearing - avg_bid) * o.total_volume

        analysis.append({
            "order_id": o.id,
            "side": o.side,
            "bid_price": round(avg_bid, 1),
            "bid_volume": o.total_volume,
            "market_clearing": market_clearing,
            "spread": round(avg_bid - market_clearing, 1),
            "advice": advice,
            "potential_pnl": round(cost_saving, 0),  # 正=赚了，负=亏了
        })

    # 统计
    total_pnl = sum(a["potential_pnl"] for a in analysis)
    total_volume = sum(a["bid_volume"] for a in analysis)

    return {
        "market_clearing_price": market_clearing,
        "province": market.province,
        "total_orders": len(analysis),
        "total_volume": total_volume,
        "total_pnl": total_pnl,
        "pnl_label": "盈利" if total_pnl > 0 else "亏损" if total_pnl < 0 else "持平",
        "orders": analysis,
        "summary": _build_review_summary(analysis, market_clearing),
    }


def _build_review_summary(analysis: list, clearing: float) -> str:
    """生成复盘总结。"""
    if not analysis:
        return "暂无交易记录，开始你的第一笔申报吧！"

    buys = [a for a in analysis if a["side"] == "buy"]
    sells = [a for a in analysis if a["side"] == "sell"]

    parts = []
    parts.append(f"市场出清价 {clearing} 元/MWh。")

    if buys:
        avg_buy_spread = sum(a["spread"] for a in buys) / len(buys)
        if avg_buy_spread > 0:
            parts.append(f"你的买入报价平均高出清清价 {avg_buy_spread:.1f} 元，成交意愿强烈但成本偏高。")
        else:
            parts.append(f"你的买入报价平均低于出清价 {abs(avg_buy_spread):.1f} 元，省了成本但可能抢不到量。")

    if sells:
        avg_sell_spread = sum(a["spread"] for a in sells) / len(sells)
        if avg_sell_spread < 0:
            parts.append(f"你的卖出报价平均低于出清价 {abs(avg_sell_spread):.1f} 元，容易成交但收益偏低。")
        else:
            parts.append(f"你的卖出报价平均高出清价 {avg_sell_spread:.1f} 元，惜售但可能成交困难。")

    parts.append("电力交易策略核心：在出清价附近报量报价，才能兼顾成交率和收益。")
    return " ".join(parts)


# ============ 单人全流程仿真 ============

def _simulation_row(row: SimulationSession) -> dict:
    scenario = SCENARIOS[row.scenario_code]
    snapshot = json.loads(row.input_snapshot)
    public_snapshot = {k: v for k, v in snapshot.items() if k != "clearing_curve"}
    if row.stage in {"cleared", "settled"}:
        public_snapshot["revealed_clearing_curve"] = snapshot["clearing_curve"]
    return {
        "id": row.id,
        "scenario": scenario,
        "market_id": row.market_id,
        "province": row.province,
        "trade_date": row.trade_date,
        "role": row.role,
        "side": scenario["side"],
        "stage": row.stage,
        "period_count": row.period_count,
        "rules_version": row.rules_version,
        "engine_version": row.engine_version,
        "random_seed": row.random_seed,
        "input": public_snapshot,
        "bids": json.loads(row.orders_snapshot) if row.orders_snapshot else None,
        "clearing": json.loads(row.clearing_result) if row.clearing_result else None,
        "settlement": json.loads(row.settlement_result) if row.settlement_result else None,
        "review": json.loads(row.review_result) if row.review_result else None,
    }


def _owned_session(db: Session, session_id: int, user_id: int) -> SimulationSession:
    row = db.get(SimulationSession, session_id)
    if not row or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="仿真任务不存在")
    return row


def _require_stage(row: SimulationSession, allowed: set[str]) -> None:
    if row.stage not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"当前阶段为 {row.stage}，不能执行此操作",
        )


def _hourly(values: list, fallback: list[float]) -> list[float]:
    usable = [
        float(value) if value is not None else float(fallback[index])
        for index, value in enumerate(values[:96])
    ]
    if len(usable) < 96:
        usable.extend(float(value) for value in fallback[len(usable):96])
    return [
        round(sum(usable[hour * 4:(hour + 1) * 4]) / 4, 2)
        for hour in range(24)
    ]


@router.get("/sim/scenarios", summary="可用的完整流程仿真场景")
def simulation_scenarios():
    return {"scenarios": list(SCENARIOS.values())}


@router.get("/sim/sessions", summary="我的仿真任务")
def simulation_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.execute(
        select(SimulationSession)
        .where(SimulationSession.user_id == current_user.id)
        .order_by(SimulationSession.id.desc())
        .limit(20)
    ).scalars().all()
    return {"sessions": [_simulation_row(row) for row in rows]}


@router.post("/sim/sessions", summary="创建单人仿真任务")
def create_simulation(
    req: CreateSimulationReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenario = SCENARIOS.get(req.scenario_code)
    if not scenario:
        raise HTTPException(status_code=400, detail="未知仿真场景")
    market = db.execute(
        select(TradeMarket).where(
            TradeMarket.product == scenario["product"],
            TradeMarket.is_open.is_(True),
        ).order_by(TradeMarket.id)
    ).scalars().first()
    if not market:
        raise HTTPException(status_code=409, detail="日前市场尚未配置")

    requested_date = req.trade_date or date.today().isoformat()
    archived = _load_public_quote(db, req.province, req.trade_date)
    if archived:
        series = archived["time_series"]
        raw_prices = [point.get("price") for point in series]
        fallback_prices = _synth_price_curve(req.province, archived["trade_date"])
        clearing_curve = _hourly(raw_prices, fallback_prices)
        raw_load = [point.get("load") for point in series]
        default_load = [
            max(80.0, min(scenario["max_volume"] * 0.92, price * 0.72))
            for price in fallback_prices
        ]
        reference_curve = _hourly(raw_load, default_load)
        # 系统级负荷的绝对量级不能直接当成单个学习主体的申报上限；
        # 保留真实曲线形状，按场景主体容量等比例归一化。
        peak_reference = max(reference_curve) if reference_curve else 0
        if peak_reference > scenario["max_volume"] * 0.92:
            scale = scenario["max_volume"] * 0.92 / peak_reference
            reference_curve = [round(value * scale, 2) for value in reference_curve]
        actual_date = archived["trade_date"]
        provenance = {
            "level": archived["provenance_level"],
            "source_name": archived["source_name"],
            "source_note": archived.get("source_note") or "",
        }
    else:
        price_curve = _synth_price_curve(req.province, requested_date)
        clearing_curve = _hourly(price_curve, price_curve)
        reference_curve = [
            round(scenario["max_volume"] * (0.56 + 0.22 * _gauss_bump(hour, 19, 2.5)), 2)
            for hour in range(24)
        ]
        actual_date = requested_date
        provenance = {
            "level": "synthetic",
            "source_name": "教学场景生成器",
            "source_note": "无公开逐时观测数据，使用可复现教学曲线；不会标记为真实行情",
        }

    seed_text = f"{current_user.id}|{req.scenario_code}|{req.province}|{actual_date}"
    seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed)
    forecast_curve = [
        round(max(1.0, value * (1 + rng.uniform(-0.025, 0.025))), 2)
        for value in reference_curve
    ]
    snapshot = {
        "forecast_curve": forecast_curve,
        "reference_curve_label": "客户负荷预测" if scenario["side"] == "buy" else "可用出力预测",
        "price_reference": [
            round(price * (1 + rng.uniform(-0.035, 0.035)), 2)
            for price in clearing_curve
        ],
        "clearing_curve": clearing_curve,
        "constraints": {
            "max_volume_per_period": scenario["max_volume"],
            "price_floor": 0,
            "price_cap": 3000,
            "segments_per_period": "1-5",
        },
        "provenance": provenance,
    }
    row = SimulationSession(
        user_id=current_user.id,
        scenario_code=req.scenario_code,
        market_id=market.id,
        province=req.province,
        trade_date=actual_date,
        role=scenario["role"],
        stage="briefing",
        period_count=scenario["period_count"],
        rules_version=RULES_VERSION,
        engine_version=ENGINE_VERSION,
        random_seed=seed,
        input_snapshot=json.dumps(snapshot, ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _simulation_row(row)


@router.get("/sim/sessions/{session_id}", summary="仿真任务详情")
def simulation_detail(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _simulation_row(_owned_session(db, session_id, current_user.id))


@router.post("/sim/sessions/{session_id}/open", summary="确认简报并进入报价")
def open_simulation(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _owned_session(db, session_id, current_user.id)
    _require_stage(row, {"briefing"})
    row.stage = "bidding"
    db.commit()
    db.refresh(row)
    return _simulation_row(row)


@router.put("/sim/sessions/{session_id}/bids", summary="保存24时段分段申报")
def save_simulation_bids(
    session_id: int,
    req: SimulationBidsReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _owned_session(db, session_id, current_user.id)
    _require_stage(row, {"bidding"})
    scenario = SCENARIOS[row.scenario_code]
    try:
        bids = validate_bid_schedule(
            req.bids,
            period_count=row.period_count,
            max_volume=scenario["max_volume"],
            side=scenario["side"],
        )
    except BidValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row.orders_snapshot = json.dumps(bids, ensure_ascii=False)
    db.commit()
    db.refresh(row)
    return _simulation_row(row)


@router.post("/sim/sessions/{session_id}/seal", summary="封盘")
def seal_simulation(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _owned_session(db, session_id, current_user.id)
    _require_stage(row, {"bidding"})
    if not row.orders_snapshot:
        raise HTTPException(status_code=400, detail="请先保存完整申报")
    row.stage = "sealed"
    db.commit()
    db.refresh(row)
    return _simulation_row(row)


@router.post("/sim/sessions/{session_id}/clear", summary="执行市场出清")
def clear_simulation(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _owned_session(db, session_id, current_user.id)
    _require_stage(row, {"sealed"})
    scenario = SCENARIOS[row.scenario_code]
    result = run_clearing(
        json.loads(row.input_snapshot),
        json.loads(row.orders_snapshot),
        side=scenario["side"],
    )
    row.clearing_result = json.dumps(result, ensure_ascii=False)
    row.stage = "cleared"
    db.commit()
    db.refresh(row)
    return _simulation_row(row)


@router.post("/sim/sessions/{session_id}/settle", summary="执行计量结算并生成复盘")
def settle_simulation(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = _owned_session(db, session_id, current_user.id)
    _require_stage(row, {"cleared"})
    scenario = SCENARIOS[row.scenario_code]
    clearing = json.loads(row.clearing_result)
    settlement = run_settlement(
        clearing,
        side=scenario["side"],
        random_seed=row.random_seed,
    )
    review = build_review(clearing, settlement, side=scenario["side"])
    row.settlement_result = json.dumps(settlement, ensure_ascii=False)
    row.review_result = json.dumps(review, ensure_ascii=False)
    row.stage = "settled"
    db.commit()
    db.refresh(row)
    return _simulation_row(row)
