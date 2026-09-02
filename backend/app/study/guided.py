"""小白主动学习课程。

每课遵循：目标 → 先修 → 讲解 → 数据观察 → 即时检查 → 业务成果 → 来源。
内容是课程骨架；官方规则和知识资产由数据库动态关联，避免把静态文案冒充最新规则。
"""
from __future__ import annotations

from typing import Optional


GUIDED_UNITS = [
    {
        "code": "power_system_map",
        "order": 1,
        "title": "电从哪里来：发、输、配、用",
        "subtitle": "先看懂物理系统，再理解为什么需要交易",
        "duration_min": 25,
        "knowledge_code": "industry",
        "prerequisites": [],
        "objectives": [
            "说清发电、输电、配电和用电的边界",
            "区分电网运行与电力交易",
            "解释电力必须实时平衡的原因",
        ],
        "concepts": [
            {
                "title": "电能不是普通库存商品",
                "body": "电力系统需要在每个时刻维持发用平衡。交易计划解决经济安排，调度控制负责物理执行，两者相互衔接但不能混为一谈。",
            },
            {
                "title": "一条电力业务链",
                "body": "发电企业形成可交易电量，经批发市场与售电公司或大用户成交，再通过输配电网络交付，最终进入计量、结算和偏差考核。",
            },
        ],
        "observation": {
            "title": "观察全国供需两端",
            "instruction": "对照全国装机容量与全社会用电量，判断“装机增长”为什么不等于“每个时段都不缺电”。",
            "data_types": ["national_power_statistics", "national_power_consumption"],
        },
        "deliverable": {
            "title": "画出你的第一张电力业务链",
            "prompt": "用文字按“主体 → 行为 → 数据/单据”写出从发电到结算的完整链条，至少包含6个节点。",
            "example": "发电企业→申报量价曲线→交易机构出清→调度执行→计量采集→结算对账",
        },
        "checks": [
            {
                "question": "电力交易成交后，物理送电是否可以脱离电网调度独立完成？",
                "options": ["可以", "不可以"],
                "answer": 1,
                "explanation": "交易形成经济计划，物理执行仍必须服从电网安全约束和调度。",
            },
        ],
        "source_keywords": ["全国电力统计", "全社会用电量", "电力市场"],
    },
    {
        "code": "market_roles",
        "order": 2,
        "title": "市场里都有谁：主体、资产与职责",
        "subtitle": "用交易员视角识别谁申报、谁校验、谁结算",
        "duration_min": 30,
        "knowledge_code": "industry",
        "prerequisites": ["power_system_map"],
        "objectives": ["识别六类核心市场主体", "理解交易机构与调度机构分工", "完成主体职责矩阵"],
        "concepts": [
            {
                "title": "经营主体",
                "body": "发电企业、售电公司、电力用户、储能、虚拟电厂和分布式新能源以不同资产和计量边界参与市场，各自承担申报、履约和偏差责任。",
            },
            {
                "title": "运营机构",
                "body": "交易机构组织注册、交易与结算依据管理；调度机构负责安全校核和实时运行；电网企业承担输配电、计量等职责。",
            },
        ],
        "observation": {
            "title": "观察主体注册规则",
            "instruction": "从官方注册或许可文件中找出准入条件、材料、持续义务三个层次。",
            "data_types": [],
        },
        "deliverable": {
            "title": "主体职责矩阵",
            "prompt": "选择发电企业、售电公司、电力用户三类主体，分别写出资产、申报内容、主要风险和结算责任。",
            "example": "售电公司｜资产/合同：零售合同｜申报：分时购电曲线｜风险：量价与偏差｜责任：客户结算",
        },
        "checks": [
            {
                "question": "负责实时安全运行与调度控制的主要机构是？",
                "options": ["交易机构", "调度机构", "售电公司"],
                "answer": 1,
                "explanation": "交易机构组织市场，调度机构负责电网实时安全运行。",
            },
        ],
        "source_keywords": ["市场注册", "信息披露", "电力业务许可"],
    },
    {
        "code": "wholesale_basics",
        "order": 3,
        "title": "批发市场：电能量如何成交",
        "subtitle": "理解市场品种、时间尺度和价格形成",
        "duration_min": 35,
        "knowledge_code": "wholesale",
        "prerequisites": ["market_roles"],
        "objectives": ["区分中长期与现货", "理解分时电量和量价曲线", "读懂基础成交结果"],
        "concepts": [
            {
                "title": "时间尺度决定交易任务",
                "body": "中长期市场提前锁定电量和价格，现货市场根据更接近运行时点的供需与约束修正计划。二者共同构成完整电能量交易体系。",
            },
            {
                "title": "申报不是一个总数",
                "body": "真实申报通常按24时段或96时点组织，并允许多段量价。总电量相同，曲线形状不同，风险和结算结果可能完全不同。",
            },
        ],
        "observation": {
            "title": "观察真实市场交易结构",
            "instruction": "比较全国中长期、现货、跨省跨区和绿电交易电量，识别当前占比最大的交易方式。",
            "data_types": ["national_market_transaction", "national_market_transaction_ytd"],
        },
        "deliverable": {
            "title": "交易品种选择说明",
            "prompt": "假设你是售电公司，要为下月客户锁定80%预计用电量。说明选择的市场、剩余风险和后续修正方式。",
            "example": "先用月度中长期锁定基础曲线，再用日前现货修正预测偏差，实时市场承担最后偏差。",
        },
        "checks": [
            {
                "question": "日前市场最主要解决什么问题？",
                "options": ["永久锁定多年价格", "基于次日预测形成分时计划", "替代电网实时调度"],
                "answer": 1,
                "explanation": "日前市场依据次日负荷、新能源和机组边界形成分时交易计划。",
            },
        ],
        "source_keywords": ["电力市场交易电量", "中长期", "现货市场"],
    },
    {
        "code": "retail_basics",
        "order": 4,
        "title": "零售市场：售电公司如何服务用户",
        "subtitle": "从客户负荷到零售合同和购电组合",
        "duration_min": 35,
        "knowledge_code": "retail",
        "prerequisites": ["wholesale_basics"],
        "objectives": ["理解批零衔接", "识别客户负荷特征", "设计基础零售套餐"],
        "concepts": [
            {"title": "批零价差不是全部利润", "body": "售电公司同时承担客户服务、负荷预测、组合购电、偏差和信用风险。只比较平均买卖价会低估真实成本。"},
        ],
        "observation": {"title": "观察行业用电结构", "instruction": "比较二产、三产和居民用电变化，思考不同客户的曲线风险。", "data_types": ["national_power_consumption"]},
        "deliverable": {"title": "零售客户画像", "prompt": "选择一种工商业客户，写出营业时段、峰谷特点、可调节负荷和适合的零售价格结构。", "example": "商业综合体｜10-22时高负荷｜空调可调｜适合分时价格+需求响应奖励"},
        "checks": [{"question": "售电公司的偏差风险主要来自？", "options": ["客户实际用电与购电计划不一致", "发电机颜色不同"], "answer": 0, "explanation": "预测误差会形成计划与实际电量偏差并进入结算。"}],
        "source_keywords": ["零售市场", "售电公司", "代理购电"],
    },
    {
        "code": "mid_long_term",
        "order": 5,
        "title": "中长期交易：合同曲线与履约",
        "subtitle": "不只看总量，要看分时曲线、价格与执行",
        "duration_min": 40,
        "knowledge_code": "mid_long_term",
        "prerequisites": ["retail_basics"],
        "objectives": ["区分双边、挂牌、集中竞价", "制作合同分时曲线", "理解合同转让与调整"],
        "concepts": [{"title": "合同电量必须落到时间", "body": "年度或月度合同最终要分解到日和时段，才能与现货计划、实际用电和偏差结算衔接。"}],
        "observation": {"title": "观察中长期市场规模", "instruction": "查看全国市场交易数据中的中长期电量并与现货比较。", "data_types": ["national_market_transaction"]},
        "deliverable": {"title": "24时段合同曲线", "prompt": "描述一个100MWh日合同如何分配到24时段，并解释峰段与谷段分配依据。", "example": "按客户基线负荷分解，峰段优先覆盖不可调负荷，谷段保留现货优化空间。"},
        "checks": [{"question": "只签总电量、不形成分时曲线，最直接影响的是？", "options": ["无法与分时计划和实际电量准确对账", "无法显示企业名称"], "answer": 0, "explanation": "偏差与结算均依赖时段电量。"}],
        "source_keywords": ["中长期交易", "合同", "集中竞价"],
    },
    {
        "code": "spot_market",
        "order": 6,
        "title": "现货交易：日前、实时与出清",
        "subtitle": "进入96点量价申报和统一出清",
        "duration_min": 50,
        "knowledge_code": "spot",
        "prerequisites": ["mid_long_term"],
        "objectives": ["理解日前与实时衔接", "读懂量价曲线", "完成一次单人日前仿真"],
        "concepts": [{"title": "价格是供需和约束的结果", "body": "现货价格随时段供需、新能源出力、机组成本和网络约束变化。统一出清不是简单平均价。"}],
        "observation": {"title": "观察南方现货周行情", "instruction": "比较日前与实时均价、成交量及省间差异。", "data_types": ["southern_spot_weekly"]},
        "deliverable": {"title": "日前申报方案", "prompt": "写出你的角色、目标、至少三个关键时段的申报量价及理由，然后进入仿真实操。", "example": "售电公司｜晚高峰提高买入限价以保证成交｜谷段降低限价控制成本"},
        "checks": [{"question": "买方报价低于市场出清价时通常会怎样？", "options": ["更容易成交", "可能无法成交"], "answer": 1, "explanation": "买方愿付价格不足以覆盖出清价时，申报可能不被接受。"}],
        "source_keywords": ["现货市场", "日前", "实时"],
        "simulation_scenario": "day_ahead_retailer",
    },
    {
        "code": "ancillary_services",
        "order": 7,
        "title": "辅助服务：为灵活性定价",
        "subtitle": "调频、备用和电能量市场不能混用",
        "duration_min": 35,
        "knowledge_code": "ancillary",
        "prerequisites": ["spot_market"],
        "objectives": ["区分调频与备用", "理解容量和里程", "识别性能考核"],
        "concepts": [{"title": "卖的是调节能力", "body": "辅助服务补偿的是容量、响应速度、调用里程或可用性，不等同于单纯出售电量。"}],
        "observation": {"title": "观察灵活性需求", "instruction": "结合风光装机增速分析为什么系统需要更多调节资源。", "data_types": ["national_power_statistics"]},
        "deliverable": {"title": "辅助服务能力卡", "prompt": "为一座储能电站写出可提供的服务、容量、持续时间、响应速度和主要考核风险。", "example": "二次调频｜10MW｜1h｜秒级响应｜风险：跟踪误差与可用率"},
        "checks": [{"question": "调频里程主要描述什么？", "options": ["资源实际调节动作量", "年度总发电量"], "answer": 0, "explanation": "里程反映跟随调频指令的累计调节量。"}],
        "source_keywords": ["辅助服务", "调频", "备用"],
    },
    {
        "code": "settlement",
        "order": 8,
        "title": "结算与偏差：每一分钱如何对账",
        "subtitle": "从计划电量、实际电量到偏差费用和复盘",
        "duration_min": 45,
        "knowledge_code": "settlement",
        "prerequisites": ["ancillary_services"],
        "objectives": ["建立结算公式链", "计算偏差电量", "完成结算核对清单"],
        "concepts": [{"title": "成交不等于最终收益", "body": "最终结果还取决于实际计量、合同与现货价格、偏差规则、输配电价、政府性基金以及考核费用。"}],
        "observation": {"title": "比较计划与实际", "instruction": "在仿真结算中逐时核对成交电量、实际电量、偏差价格和偏差费用。", "data_types": []},
        "deliverable": {"title": "结算对账清单", "prompt": "列出交易员收到结算单后必须核对的字段、公式和异常处理步骤，至少8项。", "example": "合同曲线→现货成交→计量电量→偏差电量→偏差价格→考核→税费→总金额"},
        "checks": [{"question": "偏差电量通常等于？", "options": ["实际电量减计划/成交电量", "成交价格减申报价格"], "answer": 0, "explanation": "偏差首先是电量差，再按适用规则计价。"}],
        "source_keywords": ["结算", "偏差", "计量"],
    },
]

UNIT_BY_CODE = {unit["code"]: unit for unit in GUIDED_UNITS}


def get_unit(code: str) -> Optional[dict]:
    return UNIT_BY_CODE.get(code)
