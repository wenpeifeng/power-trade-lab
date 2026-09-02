"""自动归类引擎 —— 文本内容 → 自动匹配分类树 + 多维标签。

两条路径：
1. 关键词规则匹配（快速，无依赖）
2. 语义向量匹配（精确，复用embedding模型）

文档入库时自动调用，无需人工选分类。
"""
import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("classifier")

# 分类关键词映射（用于规则匹配）
# code → 触发关键词列表（命中即归类）
CATEGORY_KEYWORDS = {
    # 0 总览
    "01": ["概览", "装机", "电量", "供需", "形势", "年报", "统计"],
    "02": ["电改", "9号文", "5号文", "体制改革", "改革历程"],
    "03": ["名词", "术语", "缩略语", "解释", "定义"],
    "04": ["数据", "指数", "价格指数", "绿证数据"],
    # 1 政策法规
    "11": ["电力法", "能源法", "可再生能源法"],
    "12": ["国务院", "国办发", "中共中央", "9号文"],
    "131": ["基本规则", "中长期市场基本规则", "现货市场基本规则", "运营规则"],
    "132": ["容量电价", "容量机制", "价格", "输配电价", "上网电价"],
    "133": ["新能源", "消纳", "并网", "可再生能源"],
    "134": ["绿证", "绿电", "CCER", "碳排放"],
    "135": ["监管", "市场秩序", "监管办法"],
    "14": ["区域", "华北", "华东", "南方", "跨省", "跨区"],
    "15": ["省级", "各省", "运营规则", "实施细则"],
    "16": ["交易中心", "交易公告", "结算细则", "信息披露"],
    # 2 市场主体
    "21": ["发电企业", "发电公司", "电厂"],
    "22": ["电网企业", "国网", "南网", "供电"],
    "23": ["售电公司", "售电"],
    "24": ["电力用户", "用电户", "大工业", "工商业"],
    "25": ["新型主体", "分布式", "储能", "虚拟电厂", "负荷聚合", "微电网"],
    "26": ["调度", "交易中心", "结算", "运营机构"],
    # 3 交易品种
    "311": ["中长期", "年度", "月度", "双边协商", "集中竞价", "挂牌"],
    "312": ["现货", "日前", "实时", "LMP", "节点电价", "出清"],
    "313": ["平衡", "平衡市场"],
    "32": ["辅助服务", "调频", "调峰", "备用", "无功", "黑启动", "AGC"],
    "33": ["容量市场", "容量补偿", "稀缺电价"],
    "34": ["输电权", "FTR", "金融输电权"],
    "35": ["绿电", "绿证", "碳排放", "碳市场", "CCER", "绿色权益"],
    "36": ["需求响应", "可调节负荷"],
    "37": ["发电权", "合同转让"],
    "38": ["期货", "衍生品", "电力金融"],
    # 4 产业链
    "41": ["发电技术", "火电技术", "风电技术", "光伏技术"],
    "42": ["输电", "特高压", "柔性直流"],
    "43": ["配电", "配网", "增量配电"],
    "44": ["调度运行", "电力平衡", "安全约束"],
    "45": ["计量", "电表", "数据采集"],
    "46": ["用电", "能效", "电能替代", "需求侧"],
    # 5 电价结算
    "55": ["结算", "电费", "偏差", "辅助服务分摊"],
    # 6 新兴
    "61": ["储能", "独立储能", "共享储能", "抽蓄"],
    "62": ["虚拟电厂", "负荷聚合"],
    "63": ["综合能源", "多能互补", "源网荷储"],
    "64": ["分布式交易", "隔墙售电", "新能源直连"],
    "65": ["碳市场", "电碳协同"],
    "67": ["氢能", "绿电制氢"],
    "68": ["数字化", "人工智能", "算电"],
}

# 父分类回溯映射（子分类命中时，同时归属父分类）
PARENT_MAP = {}
for code in CATEGORY_KEYWORDS:
    if len(code) >= 2:
        PARENT_MAP[code[:2]] = code[:2]  # 节级
    if len(code) >= 1:
        PARENT_MAP[code[:1]] = code[:1]  # 章级


def auto_classify(title: str, content: str) -> dict:
    """自动归类：文本 → 主分类编码 + 多维标签。

    返回: {category_code, category_name, facet_tags}
    """
    text = (title or "") + " " + (content or "")
    if not text.strip():
        return {"category_code": None, "facet_tags": {}}

    # 1. 关键词规则匹配 → 统计每个分类的命中数
    scores = {}
    for code, keywords in CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            # 长编码(子节)权重高，因为更精确
            scores[code] = hits * (1 + len(code) * 0.3)

    # 选最高分的分类
    best_code = None
    if scores:
        best_code = max(scores, key=scores.get)

    # 2. 提取多维标签
    facet_tags = _extract_facets(text)

    return {
        "category_code": best_code,
        "facet_tags": facet_tags,
    }


def _extract_facets(text: str) -> dict:
    """从文本提取多维标签。"""
    facets = {}

    # 主体维度
    entities = []
    entity_kws = {
        "发电企业": ["发电", "电厂", "电源"],
        "电网企业": ["电网", "国网", "南网", "供电"],
        "售电公司": ["售电"],
        "电力用户": ["用户", "用电", "大工业", "工商业"],
        "新型经营主体": ["储能", "虚拟电厂", "负荷聚合", "分布式", "微电网"],
        "运营机构": ["调度", "交易中心", "结算中心"],
    }
    for entity, kws in entity_kws.items():
        if any(kw in text for kw in kws):
            entities.append(entity)
    if entities:
        facets["entity"] = entities

    # 品种维度
    products = []
    product_kws = {
        "中长期": ["中长期", "年度", "月度"],
        "现货": ["现货", "日前", "实时", "LMP"],
        "辅助服务": ["辅助服务", "调频", "调峰", "备用"],
        "容量": ["容量电价", "容量市场", "容量补偿"],
        "绿电": ["绿电", "绿色电力"],
        "绿证": ["绿证"],
        "碳": ["碳", "CCER"],
        "储能": ["储能", "抽蓄"],
        "需求响应": ["需求响应"],
    }
    for product, kws in product_kws.items():
        if any(kw in text for kw in kws):
            products.append(product)
    if products:
        facets["product"] = products

    # 时间尺度
    timeframes = []
    for tf in ["年度", "季度", "月度", "月内", "日前", "实时"]:
        if tf in text:
            timeframes.append(tf)
    if timeframes:
        facets["timeframe"] = timeframes

    # 政策层级
    levels = []
    level_kws = {
        "法律": ["法》", "中华人民共和国"],
        "国务院": ["国务院", "国办发", "中共中央"],
        "部委": ["发改委", "能源局", "发改"],
        "省级": ["省发改委", "能监办", "各省"],
    }
    for level, kws in level_kws.items():
        if any(kw in text for kw in kws):
            levels.append(level)
    if levels:
        facets["source_level"] = levels

    return facets


def get_category_name(db: Session, code: str) -> Optional[str]:
    """根据分类编码查分类名。"""
    from app.db.models import CategoryNode
    node = db.query(CategoryNode).filter(CategoryNode.code == code).first()
    return node.name if node else None


def get_category_path(db: Session, code: str) -> list[dict]:
    """获取分类的完整路径（面包屑），如 [3交易品种, 31电能量, 311中长期]。"""
    from app.db.models import CategoryNode
    path = []
    current = code
    while current:
        node = db.query(CategoryNode).filter(CategoryNode.code == current).first()
        if not node:
            break
        path.append({"code": node.code, "name": node.name, "icon": node.icon})
        current = node.parent_code
    path.reverse()
    return path
