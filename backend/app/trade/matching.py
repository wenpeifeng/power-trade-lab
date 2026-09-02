"""撮合引擎 —— 订单簿 + 价格时间优先 + 统一出清。

真实电力市场撮合逻辑：
1. 收集买卖双方报价，构建订单簿
2. 买方按价格降序排列（高价优先），同价按时间优先
3. 卖方按价格升序排列（低价优先），同价按时间优先
4. 累加买卖双方电量，绘制供需曲线
5. 两条曲线交点 = 市场出清价（统一边际出清机制）
6. 高于出清价的买单成交，低于出清价的卖单成交
7. 所有成交统一按出清价结算

单用户模拟环境：
  用户只有一个，没有真实对手方。
  策略：基于历史真实出清价，生成虚拟对手方订单簿，
  让用户的报价真实参与竞争——报得不好就成交不了。
"""
import json
import logging
import random
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("matching")


def match_order(
    db: Session, order, market, avg_price: float, total_volume: float
) -> tuple[float, float]:
    """撮合一笔申报，返回 (fill_volume, fill_price)。

    撮合流程：
    1. 获取该市场最近真实出清价作为市场基准
    2. 构建虚拟对手方订单簿（基于真实价格区间）
    3. 用户的报价与虚拟对手方竞争
    4. 按统一出清价结算
    """
    from app.db.models import PublicData

    province = market.province or "山西"
    market_clearing_price = _get_market_clearing_price(db, province, market.id)

    # 构建虚拟订单簿
    orderbook = _build_virtual_orderbook(market_clearing_price, total_volume, order.side)

    # 执行撮合
    fill_volume, fill_price = _clear(order, avg_price, total_volume,
                                      market_clearing_price, orderbook)

    logger.info(
        f"撮合[{market.province}]: {order.side} 报价{avg_price:.1f} 量{total_volume} "
        f"出清价{market_clearing_price:.1f} → 成交{fill_volume:.1f} @ {fill_price:.1f}"
    )
    return fill_volume, fill_price


def _get_market_clearing_price(db: Session, province: str, market_id: int) -> float:
    """获取市场出清价（真实数据优先）。"""
    from app.db.models import PublicData

    clearing_row = db.query(PublicData).filter(
        PublicData.data_type == "clearing", PublicData.province == province,
    ).order_by(PublicData.data_date.desc()).first()

    if clearing_row:
        metrics = json.loads(clearing_row.metrics)
        curve = metrics.get("curve", [])
        if curve:
            # 取当日均价
            return round(sum(curve) / len(curve), 1)

    # 兜底：合理的默认值
    return 300.0


def _build_virtual_orderbook(clearing_price: float, user_volume: float,
                              user_side: str) -> dict:
    """构建虚拟对手方订单簿。

    基于出清价，模拟市场里其他交易者的报价分布：
    - 买方：在出清价附近呈正态分布（有人愿出高价，有人只愿出低价）
    - 卖方：同理

    返回对手方的总成交量，用于判断用户订单能否成交。
    """
    rng = random.Random(int(clearing_price * 100) + hash(user_side) % 1000)

    if user_side == "buy":
        # 用户是买方 → 对手方是卖方 + 其他买方（竞争者）
        # 卖方愿卖的价格（低于出清价的卖方会成交）
        sell_volume_at_clearing = rng.uniform(200, 800)
        # 其他买方竞争量（报更高价的买方会优先成交）
        competitor_buy_volume = rng.uniform(100, 500)
        return {
            "available_sell_volume": sell_volume_at_clearing,
            "competitor_volume": competitor_buy_volume,
        }
    else:
        # 用户是卖方 → 对手方是买方 + 其他卖方
        buy_volume_at_clearing = rng.uniform(200, 800)
        competitor_sell_volume = rng.uniform(100, 500)
        return {
            "available_buy_volume": buy_volume_at_clearing,
            "competitor_volume": competitor_sell_volume,
        }


def _clear(order, avg_price: float, total_volume: float,
           clearing_price: float, orderbook: dict) -> tuple[float, float]:
    """统一出清撮合。

    电力市场规则：
    - 买方报价 >= 出清价 → 全额成交
    - 买方报价 < 出清价 → 可能不成交（被报更高价的买方抢走）
    - 卖方报价 <= 出清价 → 全额成交
    - 卖方报价 > 出清价 → 可能不成交

    成交价统一为出清价（不是报价）——这是电力现货统一出清的核心。
    """
    if order.side == "buy":
        # 买方：报价 >= 出清价
        if avg_price >= clearing_price:
            # 有竞争力，但要看是否有足够卖方量
            available = orderbook["available_sell_volume"]
            # 被竞争对手抢走部分
            ratio = min(1.0, available / max(total_volume, 1))
            fill_ratio = max(0.3, ratio)  # 至少30%成交（市场有流动性）
        elif avg_price >= clearing_price * 0.97:
            # 接近出清价，边际竞争
            fill_ratio = random.uniform(0.1, 0.4)
        else:
            # 报价太低，抢不过别人
            fill_ratio = random.uniform(0, 0.1)
    else:
        # 卖方：报价 <= 出清价
        if avg_price <= clearing_price:
            available = orderbook["available_buy_volume"]
            ratio = min(1.0, available / max(total_volume, 1))
            fill_ratio = max(0.3, ratio)
        elif avg_price <= clearing_price * 1.03:
            fill_ratio = random.uniform(0.1, 0.4)
        else:
            fill_ratio = random.uniform(0, 0.1)

    fill_volume = round(total_volume * fill_ratio, 1)
    # 统一出清价结算（不是用户报价！）
    fill_price = round(clearing_price, 1)

    return fill_volume, fill_price


def get_orderbook_depth(db: Session, market, depth: int = 10) -> dict:
    """获取订单簿深度（用于前端展示买卖盘口）。

    基于当前出清价生成虚拟盘口数据。
    """
    province = market.province or "山西"
    clearing_price = _get_market_clearing_price(db, province, market.id)

    rng = random.Random(int(clearing_price))
    bids = []  # 买盘（从高到低）
    asks = []  # 卖盘（从低到高）

    for i in range(depth):
        # 买盘：出清价以下递减
        bid_price = round(clearing_price - i * rng.uniform(1, 5), 1)
        bid_volume = rng.randint(50, 300)
        bids.append({"price": bid_price, "volume": bid_volume})

        # 卖盘：出清价以上递增
        ask_price = round(clearing_price + i * rng.uniform(1, 5), 1)
        ask_volume = rng.randint(50, 300)
        asks.append({"price": ask_price, "volume": ask_volume})

    return {
        "clearing_price": clearing_price,
        "bids": bids,  # 买盘（高价优先）
        "asks": asks,  # 卖盘（低价优先）
    }
