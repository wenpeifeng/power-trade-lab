"""电力市场完整分类体系 —— 8章主分类树。

来源：国家发改委/能源局/中电联权威口径深度调研
设计：主分类树（业务导航）+ 多维标签（交叉检索）
原则：官方口径优先、物理层与市场层分离、预留扩展位
"""
# 主分类树（章-节-子节三级），可直接初始化到 CategoryNode
CATEGORY_TREE = [
    # ===== 0_总览与基础 =====
    {"code": "0", "name": "总览与基础", "facet": "chapter", "icon": "📊", "children": [
        {"code": "01", "name": "电力行业概览"},
        {"code": "02", "name": "电力体制改革历程"},
        {"code": "03", "name": "名词术语表"},
        {"code": "04", "name": "数据与统计"},
    ]},
    # ===== 1_政策法规（6级金字塔）=====
    {"code": "1", "name": "政策法规", "facet": "chapter", "icon": "📜", "children": [
        {"code": "11", "name": "法律", "children": [
            {"code": "111", "name": "电力法"},
            {"code": "112", "name": "能源法"},
        ]},
        {"code": "12", "name": "党中央国务院文件"},
        {"code": "13", "name": "部委规章", "children": [
            {"code": "131", "name": "市场基本规则"},
            {"code": "132", "name": "价格与容量机制"},
            {"code": "133", "name": "新能源与消纳"},
            {"code": "134", "name": "绿色权益"},
            {"code": "135", "name": "监管"},
        ]},
        {"code": "14", "name": "区域规则"},
        {"code": "15", "name": "省级规则"},
        {"code": "16", "name": "交易机构规则"},
    ]},
    # ===== 2_市场主体（官方4+1分类）=====
    {"code": "2", "name": "市场主体", "facet": "chapter", "icon": "🏢", "children": [
        {"code": "21", "name": "发电企业", "children": [
            {"code": "211", "name": "火电"},
            {"code": "212", "name": "水电（含抽蓄）"},
            {"code": "213", "name": "核电"},
            {"code": "214", "name": "风电"},
            {"code": "215", "name": "光伏"},
            {"code": "216", "name": "生物质及其他"},
        ]},
        {"code": "22", "name": "电网企业"},
        {"code": "23", "name": "售电公司"},
        {"code": "24", "name": "电力用户"},
        {"code": "25", "name": "新型经营主体", "children": [
            {"code": "251", "name": "分布式发电"},
            {"code": "252", "name": "新型储能"},
            {"code": "253", "name": "虚拟电厂"},
            {"code": "254", "name": "负荷聚合商"},
            {"code": "255", "name": "微电网"},
        ]},
        {"code": "26", "name": "运营机构"},
    ]},
    # ===== 3_交易品种（核心，6大类）=====
    {"code": "3", "name": "交易品种与市场", "facet": "chapter", "icon": "💱", "children": [
        {"code": "31", "name": "电能量市场", "children": [
            {"code": "311", "name": "中长期市场"},
            {"code": "312", "name": "现货市场"},
            {"code": "313", "name": "平衡市场"},
        ]},
        {"code": "32", "name": "辅助服务市场", "children": [
            {"code": "321", "name": "有功平衡（调频/调峰/备用）"},
            {"code": "322", "name": "无功平衡"},
            {"code": "323", "name": "黑启动"},
        ]},
        {"code": "33", "name": "容量市场与机制"},
        {"code": "34", "name": "输电权市场"},
        {"code": "35", "name": "绿色权益市场", "children": [
            {"code": "351", "name": "绿色电力交易"},
            {"code": "352", "name": "绿证交易"},
            {"code": "353", "name": "碳排放权交易"},
            {"code": "354", "name": "CCER"},
        ]},
        {"code": "36", "name": "需求响应"},
        {"code": "37", "name": "发电权与合同转让"},
        {"code": "38", "name": "电力金融（期货/衍生品）"},
    ]},
    # ===== 4_产业链技术与运行 =====
    {"code": "4", "name": "产业链技术与运行", "facet": "chapter", "icon": "⚙️", "children": [
        {"code": "41", "name": "发电技术"},
        {"code": "42", "name": "输电"},
        {"code": "43", "name": "配电"},
        {"code": "44", "name": "调度运行"},
        {"code": "45", "name": "计量"},
        {"code": "46", "name": "用电与能效"},
    ]},
    # ===== 5_电价与结算 =====
    {"code": "5", "name": "电价与结算", "facet": "chapter", "icon": "💰", "children": [
        {"code": "51", "name": "输配电价"},
        {"code": "52", "name": "上网电价"},
        {"code": "53", "name": "销售电价"},
        {"code": "54", "name": "容量电价与两部制"},
        {"code": "55", "name": "结算规则"},
        {"code": "56", "name": "交叉补贴与政府性基金"},
    ]},
    # ===== 6_新兴与交叉领域 =====
    {"code": "6", "name": "新兴与交叉领域", "facet": "chapter", "icon": "🚀", "children": [
        {"code": "61", "name": "储能"},
        {"code": "62", "name": "虚拟电厂与负荷聚合"},
        {"code": "63", "name": "综合能源服务"},
        {"code": "64", "name": "分布式交易与隔墙售电"},
        {"code": "65", "name": "碳市场联动"},
        {"code": "66", "name": "算电协同"},
        {"code": "67", "name": "氢能"},
        {"code": "68", "name": "电力数字化与人工智能"},
    ]},
    # ===== 7_区域与省级市场 =====
    {"code": "7", "name": "区域与省级市场", "facet": "chapter", "icon": "🗺️", "children": [
        {"code": "71", "name": "区域市场"},
        {"code": "72", "name": "省级市场"},
        {"code": "73", "name": "跨省跨区交易"},
    ]},
    # ===== 8_国际与比较 =====
    {"code": "8", "name": "国际与比较", "facet": "chapter", "icon": "🌍", "children": [
        {"code": "81", "name": "国际电力市场经验"},
        {"code": "82", "name": "国际能源转型比较"},
    ]},
]

# 多维标签维度（facet），每篇文档可同时打多个维度标签
FACET_DIMENSIONS = {
    "entity": {
        "label": "市场主体",
        "values": ["发电企业", "电网企业", "售电公司", "电力用户", "新型经营主体", "运营机构"],
    },
    "product": {
        "label": "交易品种",
        "values": ["中长期", "现货", "辅助服务", "容量", "输电权", "绿电", "绿证", "碳", "需求响应"],
    },
    "timeframe": {
        "label": "时间尺度",
        "values": ["年度", "季度", "月度", "月内", "多日", "日前", "实时", "平衡"],
    },
    "source_level": {
        "label": "政策层级",
        "values": ["法律", "国务院", "部委", "区域", "省级", "交易机构"],
    },
    "region": {
        "label": "地域",
        "values": ["全国", "省间", "华北", "华东", "南方", "西北", "东北", "华中"],
    },
}


def flatten_tree(tree=None, parent_code=None, result=None):
    """把分类树展开为扁平节点列表（便于批量入库）。"""
    if tree is None:
        tree = CATEGORY_TREE
    if result is None:
        result = []
    for node in tree:
        result.append({
            "code": node["code"],
            "name": node["name"],
            "parent_code": parent_code,
            "level": len(node["code"]),  # 1位=章, 2位=节, 3位=子节
            "facet": node.get("facet", "chapter"),
            "icon": node.get("icon", ""),
        })
        if "children" in node:
            flatten_tree(node["children"], node["code"], result)
    return result
