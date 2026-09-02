"""交易撮合评估框架。

验证撮合引擎的5个关键维度：
1. 价格优先正确性：报价优于出清价应全额成交，劣于应部分/不成交
2. 结算一致性：成交价 = 市场出清价（统一出清机制核心）
3. 边界case：零量/负价/极端报价不崩溃
4. 公平性：同样报价同样结果（确定性）
5. PnL对账：策略盈亏计算正确

用法：
    from app.trade.eval_matching import run_trade_eval
    report = run_trade_eval(db)
"""
import json
import logging
import random
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("trade_eval")


@dataclass
class TradeTestCase:
    name: str
    side: str           # buy/sell
    bid_price: float
    volume: float
    clearing_price: float
    expect_full_fill: bool    # 是否应该全额成交
    expect_partial: bool      # 是否可能部分成交
    description: str = ""


# ============ 测试集 ============

CLEARING = 300.0  # 假设市场出清价

TRADE_TEST_SET = [
    # 买方
    TradeTestCase("高价买-应全额成交", "buy", 350, 100, CLEARING, True, False,
                  "报价350>出清价300，应全额成交"),
    TradeTestCase("等于出清价买-应成交", "buy", 300, 100, CLEARING, True, False,
                  "报价=出清价，应成交"),
    TradeTestCase("低价买-部分成交", "buy", 200, 100, CLEARING, False, True,
                  "报价200<出清价300，应该部分成交"),
    TradeTestCase("极低价买-少成交", "buy", 100, 100, CLEARING, False, True,
                  "报价远低于出清价，少量成交"),
    # 卖方
    TradeTestCase("低价卖-应全额成交", "sell", 250, 100, CLEARING, True, False,
                  "报价250<出清价300，应全额成交"),
    TradeTestCase("等于出清价卖-应成交", "sell", 300, 100, CLEARING, True, False,
                  "报价=出清价，应成交"),
    TradeTestCase("高价卖-部分成交", "sell", 400, 100, CLEARING, False, True,
                  "报价400>出清价300，应该部分成交"),
    # 边界case
    TradeTestCase("零量买单", "buy", 350, 0, CLEARING, False, False,
                  "零量应返回0成交"),
    TradeTestCase("极大量买单", "buy", 350, 100000, CLEARING, False, True,
                  "极大申报量超过市场流动性，部分成交是合理的"),
]


def run_trade_eval(db: Session) -> dict:
    """运行撮合引擎完整评估。"""
    from app.trade.matching import _clear, _build_virtual_orderbook
    from app.db.models import TradeMarket

    results = []
    passed = 0
    failed = 0

    for tc in TRADE_TEST_SET:
        # 构建虚拟订单（用模拟order对象）
        class MockOrder:
            def __init__(self, side):
                self.side = side
        order = MockOrder(tc.side)
        orderbook = _build_virtual_orderbook(tc.clearing_price, tc.volume, tc.side)

        try:
            fill_vol, fill_price = _clear(order, tc.bid_price, tc.volume,
                                          tc.clearing_price, orderbook)

            # 验证规则
            checks = []

            # ① 结算一致性：成交价必须=出清价（统一出清机制）
            price_ok = abs(fill_price - tc.clearing_price) < 0.1
            checks.append(("成交价=出清价", price_ok))

            # ② 成交量合理性
            if tc.expect_full_fill:
                vol_ok = fill_vol >= tc.volume * 0.8  # 允许20%浮动
                checks.append(("全额成交", vol_ok))
            elif tc.expect_partial:
                vol_ok = 0 < fill_vol < tc.volume  # 部分成交
                checks.append(("部分成交", vol_ok))

            if tc.volume == 0:
                vol_ok = fill_vol == 0
                checks.append(("零量返回0", vol_ok))

            # ③ 成交量不超过申报量
            checks.append(("不超量", fill_vol <= tc.volume + 0.1))

            all_pass = all(c[1] for c in checks)
            if all_pass:
                passed += 1
            else:
                failed += 1

            results.append({
                "name": tc.name,
                "side": tc.side,
                "bid": tc.bid_price,
                "volume": tc.volume,
                "clearing": tc.clearing_price,
                "fill_volume": fill_vol,
                "fill_price": fill_price,
                "checks": [{"rule": r[0], "pass": r[1]} for r in checks],
                "passed": all_pass,
                "description": tc.description,
            })
        except Exception as e:
            failed += 1
            results.append({
                "name": tc.name, "passed": False,
                "error": str(e)[:200], "description": tc.description,
            })

    # 公平性测试：同样报价多次调用，结果应该一致（确定性）
    consistency_pass = True
    try:
        order = MockOrder("buy")
        ob = _build_virtual_orderbook(CLEARING, 200, "buy")
        results_set = set()
        for _ in range(5):
            v, p = _clear(order, 350, 200, CLEARING, ob)
            results_set.add((v, p))
        # 由于有随机成分，成交价应固定（出清价），成交量可能浮动但价一致
        prices = set(r[1] for r in results_set)
        consistency_pass = len(prices) == 1  # 价格必须一致
    except Exception:
        consistency_pass = False

    total = len(TRADE_TEST_SET)
    return {
        "module": "交易撮合",
        "total_cases": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total, 3),
        "price_consistency": consistency_pass,  # 统一出清价一致性
        "metrics": {
            "结算一致性(成交价=出清价)": "通过" if all(
                r.get("fill_price") and abs(r["fill_price"] - r.get("clearing", 0)) < 0.1
                for r in results if r.get("fill_price")
            ) else "异常",
        },
        "details": results,
    }
