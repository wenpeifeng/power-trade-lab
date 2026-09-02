"""可复现的单人电力交易仿真引擎。

引擎只处理确定性业务计算；行情快照、权限与阶段流转由路由层负责。
"""
from __future__ import annotations

import random
from typing import Any


ENGINE_VERSION = "sim-clearing-1.0"
RULES_VERSION = "learning-day-ahead-1.0"

SCENARIOS = {
    "day_ahead_retailer": {
        "code": "day_ahead_retailer",
        "title": "售电公司日前购电",
        "subtitle": "根据客户负荷预测提交24时段分段买入申报",
        "role": "retailer",
        "side": "buy",
        "product": "day_ahead",
        "period_count": 24,
        "max_volume": 420.0,
        "objective": "在保障客户用电成交的同时控制购电成本与偏差费用",
        "briefing": [
            "逐时客户负荷预测是申报量的基础，不应只报一个全天总量。",
            "买方报价高于或等于出清价的分段才能成交。",
            "成交量不足会形成缺口；实际用电与成交量不同会产生偏差费用。",
        ],
    },
    "day_ahead_generator": {
        "code": "day_ahead_generator",
        "title": "发电企业日前售电",
        "subtitle": "结合可用容量与成本提交24时段分段卖出申报",
        "role": "generator",
        "side": "sell",
        "product": "day_ahead",
        "period_count": 24,
        "max_volume": 360.0,
        "objective": "在保证成交率的同时覆盖边际成本并控制偏差风险",
        "briefing": [
            "申报量不得超过时段可用容量。",
            "卖方报价低于或等于出清价的分段才能成交。",
            "低价提高成交概率，但过低报价会压缩策略空间。",
        ],
    },
}


class BidValidationError(ValueError):
    pass


def validate_bid_schedule(
    bids: list[dict[str, Any]],
    *,
    period_count: int,
    max_volume: float,
    side: str,
) -> list[dict[str, Any]]:
    if side not in {"buy", "sell"}:
        raise BidValidationError("交易方向必须是 buy 或 sell")
    if len(bids) != period_count:
        raise BidValidationError(f"必须完整申报 {period_count} 个时段")
    periods = {int(row.get("period", -1)) for row in bids}
    if periods != set(range(period_count)):
        raise BidValidationError("时段编号必须连续且不可重复")

    normalized = []
    for row in sorted(bids, key=lambda item: int(item["period"])):
        period = int(row["period"])
        segments = row.get("segments") or []
        if not 1 <= len(segments) <= 5:
            raise BidValidationError(f"第{period + 1}时段须包含1至5段报价")
        clean_segments = []
        for segment in segments:
            price = float(segment.get("price", -1))
            volume = float(segment.get("volume", 0))
            if not 0 <= price <= 3000:
                raise BidValidationError(f"第{period + 1}时段报价应在0至3000元/MWh")
            if volume <= 0:
                raise BidValidationError(f"第{period + 1}时段申报电量必须大于0")
            clean_segments.append({"price": round(price, 2), "volume": round(volume, 3)})
        if sum(item["volume"] for item in clean_segments) > max_volume + 1e-9:
            raise BidValidationError(f"第{period + 1}时段总申报量超过上限{max_volume}MWh")
        prices = [item["price"] for item in clean_segments]
        expected = sorted(prices, reverse=side == "buy")
        if prices != expected:
            direction = "递减" if side == "buy" else "递增"
            raise BidValidationError(f"第{period + 1}时段各段价格须按{direction}顺序排列")
        normalized.append({"period": period, "segments": clean_segments})
    return normalized


def run_clearing(
    input_snapshot: dict[str, Any],
    orders_snapshot: list[dict[str, Any]],
    *,
    side: str,
) -> dict[str, Any]:
    clearing_curve = input_snapshot["clearing_curve"]
    periods = []
    total_volume = 0.0
    total_amount = 0.0
    requested_volume = 0.0
    for row in orders_snapshot:
        period = int(row["period"])
        clearing_price = float(clearing_curve[period])
        requested = sum(float(s["volume"]) for s in row["segments"])
        accepted = sum(
            float(s["volume"])
            for s in row["segments"]
            if (float(s["price"]) >= clearing_price if side == "buy" else float(s["price"]) <= clearing_price)
        )
        amount = accepted * clearing_price
        requested_volume += requested
        total_volume += accepted
        total_amount += amount
        periods.append({
            "period": period,
            "time": f"{period:02d}:00",
            "clearing_price": round(clearing_price, 2),
            "requested_volume": round(requested, 3),
            "cleared_volume": round(accepted, 3),
            "fill_rate": round(accepted / requested * 100, 1) if requested else 0,
            "energy_amount": round(amount, 2),
        })
    return {
        "periods": periods,
        "requested_volume": round(requested_volume, 3),
        "cleared_volume": round(total_volume, 3),
        "fill_rate": round(total_volume / requested_volume * 100, 1) if requested_volume else 0,
        "weighted_price": round(total_amount / total_volume, 2) if total_volume else None,
        "energy_amount": round(total_amount, 2),
    }


def run_settlement(
    clearing_result: dict[str, Any],
    *,
    side: str,
    random_seed: int,
) -> dict[str, Any]:
    rng = random.Random(random_seed + 701)
    periods = []
    total_deviation = 0.0
    deviation_charge = 0.0
    energy_amount = 0.0
    for row in clearing_result["periods"]:
        cleared = float(row["cleared_volume"])
        factor = 1 + rng.uniform(-0.055, 0.055)
        actual = max(0.0, cleared * factor)
        deviation = actual - cleared
        clearing_price = float(row["clearing_price"])
        deviation_price = clearing_price * (1.15 if abs(deviation) > max(cleared * 0.03, 0.01) else 1.02)
        charge = abs(deviation) * deviation_price
        total_deviation += deviation
        deviation_charge += charge
        energy_amount += float(row["energy_amount"])
        periods.append({
            **row,
            "actual_volume": round(actual, 3),
            "deviation_volume": round(deviation, 3),
            "deviation_price": round(deviation_price, 2),
            "deviation_charge": round(charge, 2),
        })
    net_amount = energy_amount + deviation_charge if side == "buy" else energy_amount - deviation_charge
    return {
        "periods": periods,
        "energy_amount": round(energy_amount, 2),
        "total_deviation": round(total_deviation, 3),
        "deviation_charge": round(deviation_charge, 2),
        "net_amount": round(net_amount, 2),
        "amount_label": "总购电成本" if side == "buy" else "售电净收入",
    }


def build_review(
    clearing_result: dict[str, Any],
    settlement_result: dict[str, Any],
    *,
    side: str,
) -> dict[str, Any]:
    fill_rate = float(clearing_result["fill_rate"])
    deviation_ratio = abs(float(settlement_result["total_deviation"])) / max(
        float(clearing_result["cleared_volume"]), 1
    )
    fill_score = min(50.0, fill_rate * 0.5)
    deviation_score = max(0.0, 35.0 - deviation_ratio * 350)
    discipline_score = 15.0
    score = round(fill_score + deviation_score + discipline_score, 1)
    gaps = []
    actions = []
    if fill_rate < 90:
        gaps.append("出清机制与报价竞争力")
        actions.append("复盘未成交时段，比较申报价与出清价的方向关系")
    if deviation_ratio > 0.03:
        gaps.append("负荷/出力预测与偏差结算")
        actions.append("重新检查预测曲线和3%偏差阈值下的费用变化")
    if not gaps:
        gaps.append("多段报价的边际优化")
        actions.append("尝试把单段报价拆成保成交段与成本优化段")
    return {
        "score": score,
        "grade": "优秀" if score >= 90 else "达标" if score >= 70 else "需复盘",
        "summary": (
            f"本次申报出清率{fill_rate:.1f}%，偏差费用"
            f"{settlement_result['deviation_charge']:.2f}元。"
        ),
        "knowledge_gaps": gaps,
        "next_actions": actions,
        "side": side,
    }
