#!/usr/bin/env python3
"""幂等灌入手写核心题到 questions 表（source_type='core'）。

面向小白的核心题库，平衡题池：为 6 个偏薄知识点各补约 10 题，
覆盖绿电绿证/结算与信用/零售市场/中长期交易/辅助服务/批发市场。
不写 spot/industry（已充足）。

设计：
- type 混用 single/multiple/judge，难度 ~40% 易 / 40% 中 / 20% 难。
- options JSON 对齐 learn/router._question_to_out 的 [{key,text,is_correct}]，
  is_correct = key in answer；answer 为字母串如 "B"/"AC"，判断题 "A"=对 "B"=错。
- stem_hash(sha256) 去重，已存在则跳过；可重复安全运行。
- source='core', source_type='core', is_ai_generated=False, is_active=True。

调用：python -m scripts.seed_core_questions
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import KnowledgePoint, Question  # noqa: E402


# 目标知识点 code（偏薄的 6 类，spot/industry 不写）
TARGET_KP_CODES = ("green", "settlement", "retail", "mid_long_term", "ancillary", "wholesale")


def _stem_hash(stem: str) -> str:
    return hashlib.sha256(stem.strip().encode("utf-8")).hexdigest()


def _build_options(options: list[tuple[str, str]], answer: str) -> str:
    """构造 options JSON：[{key,text,is_correct}]，is_correct = key 在 answer 中。"""
    ans = (answer or "").strip()
    return json.dumps(
        [
            {"key": k, "text": t, "is_correct": bool(k) and k in ans}
            for k, t in options
        ],
        ensure_ascii=False,
    )


# 每题：dict(kp_code, type, stem, options, answer, analysis, difficulty)
# options = [(key, text), ...]；判断题固定 [("A","对"),("B","错")]
# exam_level 由 difficulty 派生：1-2(基础/中级)→'four'(中级工)，3(高级)→'three'(高级工)，
# 与 exam/engine.py 的级别词汇一致（level 过滤按 'four'/'three' 匹配）。


def _exam_level_for_difficulty(difficulty: int) -> str:
    """难度→考试级别（对齐 engine.py 的 level 词汇：four/three）。"""
    return "three" if difficulty >= 3 else "four"
QUESTIONS: list[dict] = [
    # ======================== green 绿电绿证 (10) ========================
    dict(
        kp_code="green",
        type="single",
        difficulty=1,
        stem="绿电交易最核心的特点是？",
        options=[
            ("A", "买的只是电，环境属性另算"),
            ("B", "把电和它的环境属性一起交易"),
            ("C", "只能买风电，不能买光伏"),
            ("D", "只在跨省交易中出现"),
        ],
        answer="B",
        analysis="绿电交易是“电+环境属性”一起买：用户买绿电，既得到电量，也得到这份电对应的绿色属性，不用再去单独买环境凭证。",
    ),
    dict(
        kp_code="green",
        type="single",
        difficulty=1,
        stem="绿色电力证书（绿证）本质上代表什么？",
        options=[
            ("A", "1度可再生能源电量"),
            ("B", "1兆瓦时（1000度）可再生能源电量的环境属性"),
            ("C", "一张碳排放配额"),
            ("D", "一张售电公司营业执照"),
        ],
        answer="B",
        analysis="1个绿证=1兆瓦时（1000度）可再生能源电量的环境属性凭证。绿证交易的是“环境属性”，不是电量本身。",
    ),
    dict(
        kp_code="green",
        type="judge",
        difficulty=1,
        stem="绿证就是绿电本身。",
        options=[("A", "对"), ("B", "错")],
        answer="B",
        analysis="错。绿电是“电量+环境属性”一起交易；绿证只交易环境属性这一部分，二者不是一回事。",
    ),
    dict(
        kp_code="green",
        type="single",
        difficulty=2,
        stem="CCER 在碳市场中指的是什么？",
        options=[
            ("A", "国家核证自愿减排量"),
            ("B", "全国碳排放配额"),
            ("C", "绿色电力证书"),
            ("D", "可再生能源发电量"),
        ],
        answer="A",
        analysis="CCER=国家核证自愿减排量，是减排项目（如造林、沼气）经核证后产生的减排量，可在碳市场中抵消部分碳排放配额。它与配额（CEA）不同：配额是“总量管制发的指标”，CCER是“项目做出来的减排量”。",
    ),
    dict(
        kp_code="green",
        type="multiple",
        difficulty=2,
        stem="下列哪些属于绿电/绿证交易范畴？",
        options=[
            ("A", "风电场把电量连同环境属性卖给用户"),
            ("B", "光伏企业出售绿证"),
            ("C", "火电厂出售碳排放配额"),
            ("D", "水电参与绿电交易"),
        ],
        answer="ABD",
        analysis="绿电/绿证交易标的是可再生能源（风电、光伏、水电等）的电量或环境属性。碳排放配额（C项）属于碳市场，不是绿电绿证范畴。",
    ),
    dict(
        kp_code="green",
        type="single",
        difficulty=2,
        stem="绿电和绿证最大的区别是什么？",
        options=[
            ("A", "绿电交易电量+环境属性一起交付，绿证可单独交易环境属性"),
            ("B", "绿电只在大用户间交易，绿证只能在居民间交易"),
            ("C", "绿证比绿电便宜，所以都买绿证"),
            ("D", "二者完全相同，只是叫法不同"),
        ],
        answer="A",
        analysis="绿电把电量和环境属性捆绑交付；绿证把环境属性单独抽出来交易，用户可以“买普通电+买绿证”来获得绿色属性。两者是“打包”和“拆分”的关系。",
    ),
    dict(
        kp_code="green",
        type="judge",
        difficulty=2,
        stem="企业购买绿证，可以用来降低其范围二（外购电力）的碳排放核算。",
        options=[("A", "对"), ("B", "错")],
        answer="A",
        analysis="对。范围二（Scope 2）指外购电力的间接排放，买绿证声明这部分电来自可再生能源，可降低范围二的碳排放量，这是企业减碳的常用手段。",
    ),
    dict(
        kp_code="green",
        type="single",
        difficulty=3,
        stem="碳排放权交易（配额CEA）与CCER的关系是？",
        options=[
            ("A", "CEA是总量控制下的配额，CCER是减排项目产生的核证量可抵消部分配额"),
            ("B", "CEA和CCER是完全相同的东西"),
            ("C", "CCER是配额，CEA是减排量"),
            ("D", "买CEA就等于买绿电"),
        ],
        answer="A",
        analysis="CEA（配额）是政府按总量控制发给企业的排放指标，企业超排要买配额；CCER是减排项目做出来的核证减排量，可按比例抵消部分配额（不是1:1，有上限）。二者互补，不是一回事。",
    ),
    dict(
        kp_code="green",
        type="single",
        difficulty=2,
        stem="一个绿证对应多少电量？",
        options=[
            ("A", "1度电"),
            ("B", "100度电"),
            ("C", "1兆瓦时（1000度电）"),
            ("D", "1万千瓦时"),
        ],
        answer="C",
        analysis="1个绿证=1兆瓦时（1000度）可再生能源电量的环境属性。记住“1证=1兆瓦时”这个换算，是绿证交易的基础。",
    ),
    dict(
        kp_code="green",
        type="judge",
        difficulty=3,
        stem="绿电交易价格一定比同电量常规电价便宜。",
        options=[("A", "对"), ("B", "错")],
        answer="B",
        analysis="错。绿电通常带有“环境溢价”——用户为绿色属性多付一点钱，所以绿电价格往往略高于常规电价，而非更便宜。便宜的是“环境价值被低估”的情况，不是常态。",
    ),

    # ======================== settlement 结算与信用 (10) ========================
    dict(
        kp_code="settlement",
        type="single",
        difficulty=1,
        stem="输配电价可以通俗理解为？",
        options=[
            ("A", "电厂卖电给电网的价格"),
            ("B", "电网把电从电厂送到用户家收的“过路费”"),
            ("C", "用户家插座出来的电价"),
            ("D", "政府收的环保税"),
        ],
        answer="B",
        analysis="输配电价是电网“过路费”：电厂把电送上电网，电网输送到用户，按输送量收的费用。它独立于发电成本，由国家核定。",
    ),
    dict(
        kp_code="settlement",
        type="single",
        difficulty=1,
        stem="上网电价指什么？",
        options=[
            ("A", "发电厂把电卖给电网的价格"),
            ("B", "用户付给售电公司的价格"),
            ("C", "电网输送的价格"),
            ("D", "跨省交易的加价"),
        ],
        answer="A",
        analysis="上网电价=发电厂把电“上网”卖给电网的出厂价，是电价链条的起点。后面再叠加输配、基金等，才到用户最终的销售电价。",
    ),
    dict(
        kp_code="settlement",
        type="single",
        difficulty=2,
        stem="两部制电价中，容量电价主要补偿什么？",
        options=[
            ("A", "发电的燃料成本"),
            ("B", "发电机组建成后与发不发电无关的固定成本"),
            ("C", "用户的用电量费用"),
            ("D", "电网的过路费"),
        ],
        answer="B",
        analysis="容量电价补偿的是建机组的固定成本（投资折旧等），不管这台机组发不发电都按容量给一部分收入，这叫“两部制”（容量+电量）。它鼓励建可靠机组保供电。",
    ),
    dict(
        kp_code="settlement",
        type="judge",
        difficulty=1,
        stem="销售电价就是用户最终支付的电费单价（含各项）。",
        options=[("A", "对"), ("B", "错")],
        answer="A",
        analysis="对。销售电价是用户最终在电表上看到的单价，由上网电价+输配电价+政府性基金及附加等组成，是电价链条的终点。",
    ),
    dict(
        kp_code="settlement",
        type="single",
        difficulty=2,
        stem="偏差结算指的是？",
        options=[
            ("A", "实际用电量与合同电量之间的差额按特定规则结算"),
            ("B", "电厂偷电被罚的结算"),
            ("C", "用户拖欠电费的结算"),
            ("D", "跨省多收的钱退还"),
        ],
        answer="A",
        analysis="偏差结算针对“计划与实际不一致”：合同定了100度，实际用了120度，多出来的20度按偏差规则结算（可能比正常价贵或便宜），以此促使市场主体尽量把预测做准。",
    ),
    dict(
        kp_code="settlement",
        type="multiple",
        difficulty=2,
        stem="下列哪些属于电价中的“交叉补贴”？",
        options=[
            ("A", "工商业用户补贴居民用户"),
            ("B", "高电压等级大用户补贴低电压小用户"),
            ("C", "上网电价补贴燃料成本"),
            ("D", "城市用户补贴农村用户的部分成本"),
        ],
        answer="ABD",
        analysis="交叉补贴是“一类用户替另一类用户多承担成本”的做法，常见为工商业补居民、高压补低压、城市补农村。它是政策性安排，不是按真实成本定价。上网电价补燃料成本不属于交叉补贴。",
    ),
    dict(
        kp_code="settlement",
        type="single",
        difficulty=3,
        stem="履约保函在电力市场结算中的作用是？",
        options=[
            ("A", "担保市场主体履行交易合同和结算义务的信用凭证"),
            ("B", "一种电价折扣券"),
            ("C", "给用户的用电补贴"),
            ("D", "电厂的发电许可证"),
        ],
        answer="A",
        analysis="履约保函由银行出具，担保市场主体（售电公司、用户等）能按合同结算、不违约跑路。它是市场准入和风险防控的信用工具，违约时由银行赔付。",
    ),
    dict(
        kp_code="settlement",
        type="single",
        difficulty=2,
        stem="现货结算与中长期结算的主要区别是？",
        options=[
            ("A", "现货按各时段实际出清价结算，中长期按合同约定价结算"),
            ("B", "现货只能月结，中长期只能年结"),
            ("C", "现货价格更低，中长期价格更高"),
            ("D", "二者完全相同"),
        ],
        answer="A",
        analysis="中长期按合同约定的固定价/公式结算；现货按每个时段（如15分钟、小时）实际出清的市场价结算。两者衔接时，中长期合同量与实际量的差额走现货价结算。",
    ),
    dict(
        kp_code="settlement",
        type="judge",
        difficulty=2,
        stem="有了容量电价，电厂即使一段时间不发电，也能拿到一部分固定收入。",
        options=[("A", "对"), ("B", "错")],
        answer="A",
        analysis="对。容量电价按机组的可用容量付费，与是否实际发电无关，这正是两部制电价保障可靠供电机组生存的设计初衷。",
    ),
    dict(
        kp_code="settlement",
        type="single",
        difficulty=3,
        stem="偏差结算中设置“允许偏差范围”的设计意图是？",
        options=[
            ("A", "兼顾预测不可避免有误差，给市场主体容错空间"),
            ("B", "鼓励大家多报少发以赚取差价"),
            ("C", "让用户少交电费"),
            ("D", "让电厂多发不计成本"),
        ],
        answer="A",
        analysis="用电预测不可能100%准，允许偏差范围内按正常价结算、超出部分才加扣，是给合理误差留容错，同时仍激励把预测做准。这是机制兼顾公平与效率的体现。",
    ),

    # ======================== retail 零售市场 (10) ========================
    dict(
        kp_code="retail",
        type="single",
        difficulty=1,
        stem="售电公司在零售市场的主要角色是？",
        options=[
            ("A", "替用户向批发市场买电、谈价、管结算的中间服务方"),
            ("B", "自己发电自己卖"),
            ("C", "负责电网建设"),
            ("D", "代表政府收电费"),
        ],
        answer="A",
        analysis="售电公司是“中间人”：替中小用户去批发市场集中买电、谈好价格，再零售给用户，并代办结算、用电优化等服务，让没能力直接参与批发市场的用户也能享受市场价。",
    ),
    dict(
        kp_code="retail",
        type="single",
        difficulty=1,
        stem="零售电价主要由哪几部分组成？",
        options=[
            ("A", "上网电价 + 输配电价 + 政府性基金及附加等"),
            ("B", "只有发电成本"),
            ("C", "只有电网过路费"),
            ("D", "只有政府基金"),
        ],
        answer="A",
        analysis="零售电价=上网电价（发电）+输配电价（电网）+政府性基金及附加（政策性），可能再叠加售电服务费，是从出厂到用户全链条的汇总。",
    ),
    dict(
        kp_code="retail",
        type="judge",
        difficulty=1,
        stem="隔墙售电是指分布式电源把电直接卖给隔壁的电力用户。",
        options=[("A", "对"), ("B", "错")],
        answer="A",
        analysis="对。“隔墙售电”形象说法是：屋顶光伏这类分布式电源，把电就近直接卖给邻居/隔壁用户，而不必全部低价卖给电网。它让分布式能源获得更好收益。",
    ),
    dict(
        kp_code="retail",
        type="single",
        difficulty=2,
        stem="“大用户”与“一般用户”的关键区别是？",
        options=[
            ("A", "大用户用电量大、电压等级高，可直接参与批发市场购电"),
            ("B", "大用户只能找售电公司，一般用户可直接购电"),
            ("C", "大用户不交电费"),
            ("D", "二者只是名字不同，待遇完全一样"),
        ],
        answer="A",
        analysis="大用户电压等级高、用电量大，有资格直接进入批发市场找电厂购电；一般中小用户因量小、专业性不足，通常通过售电公司代理购电。",
    ),
    dict(
        kp_code="retail",
        type="single",
        difficulty=2,
        stem="售电公司准入通常要求具备什么？",
        options=[
            ("A", "一定的资产规模、专业人员和履约保函等条件"),
            ("B", "只要有办公室即可"),
            ("C", "必须是发电企业"),
            ("D", "必须有自己的电网"),
        ],
        answer="A",
        analysis="售电公司准入要求资产规模、专业从业人员、信用（履约保函）等，目的是保证它有履行合同和承担风险的能力，防止“皮包公司”跑路损害用户利益。",
    ),
    dict(
        kp_code="retail",
        type="multiple",
        difficulty=2,
        stem="售电公司可以为用户提供哪些服务？",
        options=[
            ("A", "代理购电、谈价"),
            ("B", "用电优化与节能建议"),
            ("C", "代办电费结算"),
            ("D", "自行投资发电并网输电"),
        ],
        answer="ABC",
        analysis="售电公司主业是代理购电、用电优化、结算代办等服务型业务；投资发电并网输电需要专门的发电/电网资质，不是普通售电公司的事。",
    ),
    dict(
        kp_code="retail",
        type="judge",
        difficulty=2,
        stem="所有用户都必须通过售电公司买电，不能直接购电。",
        options=[("A", "对"), ("B", "错")],
        answer="B",
        analysis="错。符合条件的大用户可直接与发电企业签订购电合同进入批发市场；只有不具备直接参与条件的中小用户才走售电公司零售。",
    ),
    dict(
        kp_code="retail",
        type="single",
        difficulty=3,
        stem="隔墙售电目前面临的主要难点是？",
        options=[
            ("A", "过网费核定、电网调度配合、计量结算机制等"),
            ("B", "屋顶光伏发不出电"),
            ("C", "用户不愿意用电"),
            ("D", "没有用户愿意买绿电"),
        ],
        answer="A",
        analysis="隔墙售电难在机制：过网费怎么核定、电网如何调度这些分布式电源、双向计量和结算怎么做，都需要配套规则落地，不是技术发不出电的问题。",
    ),
    dict(
        kp_code="retail",
        type="single",
        difficulty=2,
        stem="分布式发电市场化交易的核心标的是？",
        options=[
            ("A", "分布式电源就近消纳的电量"),
            ("B", "大型火电跨省电量"),
            ("C", "碳排放配额"),
            ("D", "电网调度服务"),
        ],
        answer="A",
        analysis="分布式发电市场化交易的标的是分布式电源（屋顶光伏、分散式风电等）就近消纳的电量，强调“就近、直供”，减少长距离输送损耗。",
    ),
    dict(
        kp_code="retail",
        type="judge",
        difficulty=3,
        stem="售电公司若亏损跑路，用户的供电会被立即中断。",
        options=[("A", "对"), ("B", "错")],
        answer="B",
        analysis="错。电力有保底供电机制：售电公司退出时，由电网或兜底售电公司接管用户供电，用户不会断电，但可能需要重新签合同、价格条件可能调整。",
    ),

    # ======================== mid_long_term 中长期交易 (10) ========================
    # （导学课已有8题，以下为新写、不重复）
    dict(
        kp_code="mid_long_term",
        type="single",
        difficulty=1,
        stem="双边协商交易最大的特点是？",
        options=[
            ("A", "双方一对一谈价格和电量，灵活但效率较低"),
            ("B", "由交易所集中出清定价"),
            ("C", "只能由政府定价"),
            ("D", "只在现货市场做"),
        ],
        answer="A",
        analysis="双边协商是买卖双方“面对面”谈价、谈量、谈曲线，最灵活、最能体现双方意愿，但逐对谈判效率低，适合大额长协。",
    ),
    dict(
        kp_code="mid_long_term",
        type="single",
        difficulty=2,
        stem="集中竞价交易里，出清价格通常怎么定？",
        options=[
            ("A", "按买卖报价匹配，取能够成交的边际价格作为统一出清价"),
            ("B", "取所有报价的平均值"),
            ("C", "取最高买价和最低卖价之和"),
            ("D", "由政府指定一个固定价"),
        ],
        answer="A",
        analysis="集中竞价把买卖报价集中排序匹配，按“边际”价格统一出清：即最后一笔能成交的那档价格作为所有成交量的统一结算价，激励各方如实报价。",
    ),
    dict(
        kp_code="mid_long_term",
        type="single",
        difficulty=2,
        stem="挂牌交易最像日常的哪种场景？",
        options=[
            ("A", "股票挂单买卖，一方挂牌、对手方摘牌成交"),
            ("B", "超市固定标价自选"),
            ("C", "政府发文件定价"),
            ("D", "彩票抽奖"),
        ],
        answer="A",
        analysis="挂牌交易类似股票挂单：一方把“卖多少电、什么价、什么时间”挂出，对手方看到合适就“摘牌”成交，介于双边协商与集中竞价之间，效率比双边高、比竞价灵活。",
    ),
    dict(
        kp_code="mid_long_term",
        type="multiple",
        difficulty=2,
        stem="中长期交易的典型周期有哪些？",
        options=[
            ("A", "年度交易"),
            ("B", "月度交易"),
            ("C", "月内/月前交易"),
            ("D", "实时（5分钟）交易"),
        ],
        answer="ABC",
        analysis="中长期交易覆盖年度、月度、月内/月前等较长期限，用来锁定大部分电量的价格和基础供需；实时5分钟交易属于现货市场，不是中长期范畴。",
    ),
    dict(
        kp_code="mid_long_term",
        type="judge",
        difficulty=2,
        stem="发电权交易本质是把已签订的发电合同转让给另一家发电厂。",
        options=[("A", "对"), ("B", "错")],
        answer="A",
        analysis="对。发电权交易=“合同转让”：原合同持有方把发电义务转给另一方（如成本更低或可再生优先的机组），实现资源优化和减排，差价由双方结算。",
    ),
    dict(
        kp_code="mid_long_term",
        type="single",
        difficulty=2,
        stem="中长期交易中的“曲线分解”指什么？",
        options=[
            ("A", "把年度/月度合同电量分解到各时段，形成带时标的电力曲线"),
            ("B", "把电价曲线画出来看趋势"),
            ("C", "把电网线路拆开维护"),
            ("D", "把合同文本分章节"),
        ],
        answer="A",
        analysis="曲线分解是把“一年10万度”这种总量，按峰谷、季节分到每个时段，变成带时标（如每小时）的电力曲线，便于和现货、调度、计量对接。中长期必须分解才能执行。",
    ),
    dict(
        kp_code="mid_long_term",
        type="judge",
        difficulty=3,
        stem="中长期合同价格一旦签订，就永远不能调整。",
        options=[("A", "对"), ("B", "错")],
        answer="B",
        analysis="错。中长期合同可与现货衔接、可设置动态调整或联动机制（如与煤价、现货均价挂钩），不是死签死结。机制上鼓励与现货衔接灵活调整。",
    ),
    dict(
        kp_code="mid_long_term",
        type="single",
        difficulty=3,
        stem="中长期与现货衔接的关键结算逻辑是？",
        options=[
            ("A", "中长期按合同价结算，实际量与合同量的差额走现货价结算"),
            ("B", "中长期和现货都按现货价结算"),
            ("C", "中长期按现货价，现货按合同价"),
            ("D", "两者完全无关，各结各的"),
        ],
        answer="A",
        analysis="衔接规则：中长期合同量按合同约定价结算；实际用电/发电与合同量的差额（偏差）按现货价结算。这样既锁定大部分价格（中长期），又让短期偏差反映真实市场价（现货）。",
    ),
    dict(
        kp_code="mid_long_term",
        type="single",
        difficulty=1,
        stem="年度交易主要解决什么问题？",
        options=[
            ("A", "锁定全年大部分电量的价格和供需基础"),
            ("B", "解决某5分钟的临时供需"),
            ("C", "处理昨日缺电"),
            ("D", "给电网做检修"),
        ],
        answer="A",
        analysis="年度交易在年初把全年大部分电量价格和供需关系锁定，给电厂和用户一个稳定的预期基础，剩下的短期波动再由月度、现货补足。",
    ),
    dict(
        kp_code="mid_long_term",
        type="single",
        difficulty=2,
        stem="合同转让交易中，受让方通常是？",
        options=[
            ("A", "成本更低或更愿意发电的发电企业（如可再生优先）"),
            ("B", "用电量最大的工业用户"),
            ("C", "电网调度中心"),
            ("D", "政府价格主管部门"),
        ],
        answer="A",
        analysis="发电权/合同转让时，受让方一般是发电成本更低、或政策优先（如可再生能源优先消纳）的机组，这样转让能优化资源配置、降低整体成本并促进清洁能源。",
    ),

    # ======================== ancillary 辅助服务 (10) ========================
    dict(
        kp_code="ancillary",
        type="single",
        difficulty=1,
        stem="一次调频主要靠什么实现？",
        options=[
            ("A", "发电机组根据频率偏差自动快速调整出力"),
            ("B", "调度员手动打电话让电厂加出力"),
            ("C", "用户手动关灯节电"),
            ("D", "电网换粗的电线"),
        ],
        answer="A",
        analysis="一次调频是机组自身的“本能反应”：电网频率一偏离额定值（50Hz），机组调速器自动快速加减出力，是秒级的第一道防线，无需人工介入。",
    ),
    dict(
        kp_code="ancillary",
        type="single",
        difficulty=1,
        stem="AGC（自动发电控制）的作用是？",
        options=[
            ("A", "调度自动远控机组出力，维持频率和联络线功率在目标值"),
            ("B", "让发电机自动开关机"),
            ("C", "自动给用户停电"),
            ("D", "自动抄表"),
        ],
        answer="A",
        analysis="AGC是调度端通过通信自动调节机组出力，在秒到分钟级把频率和省间联络线功率维持在计划值，比一次调频更精细，是第二道防线。",
    ),
    dict(
        kp_code="ancillary",
        type="judge",
        difficulty=1,
        stem="调峰服务主要是为了应对用电负荷的昼夜波动。",
        options=[("A", "对"), ("B", "错")],
        answer="A",
        analysis="对。白天用电多、深夜少，部分机组要“跟着调上调下”来填谷削峰，这种为适应负荷变化而调整出力的服务就是调峰。",
    ),
    dict(
        kp_code="ancillary",
        type="single",
        difficulty=2,
        stem="“黑启动”指的是什么？",
        options=[
            ("A", "电网全停后，不依赖外部电源，靠具备自启动能力的机组恢复供电"),
            ("B", "机组烧煤烧到发黑"),
            ("C", "给发电机换黑色油漆"),
            ("D", "夜间启动发电"),
        ],
        answer="A",
        analysis="黑启动是电网大面积停电后的“自救”能力：少数机组（如柴油、水电机组）不需要外部电源就能自己启动，再带动其他机组逐步恢复整个电网，是最后的保底手段。",
    ),
    dict(
        kp_code="ancillary",
        type="single",
        difficulty=2,
        stem="冷备用和热备用的主要区别是？",
        options=[
            ("A", "热备用机组并网旋转、可立即加载，冷备用需启动并网才能加载"),
            ("B", "热备用是夏天用、冷备用是冬天用"),
            ("C", "热备用更便宜"),
            ("D", "二者完全相同"),
        ],
        answer="A",
        analysis="热备用=机组并网空转（旋转备用），几秒到几分钟内可加负荷；冷备用=机组停着，要启动并网才能带负荷，需十几分钟到数小时。响应速度不同，补偿也不同。",
    ),
    dict(
        kp_code="ancillary",
        type="multiple",
        difficulty=2,
        stem="下列哪些属于辅助服务？",
        options=[
            ("A", "一次调频"),
            ("B", "AGC（自动发电控制）"),
            ("C", "无功支撑与电压控制"),
            ("D", "电能量现货交易"),
        ],
        answer="ABC",
        analysis="辅助服务是为保障电网安全稳定而提供的“非电能量”服务，包括调频、AGC、调峰、备用、无功、黑启动等。电能量现货交易是有功电量的买卖，不属于辅助服务。",
    ),
    dict(
        kp_code="ancillary",
        type="judge",
        difficulty=2,
        stem="无功功率支撑电压，通常不计入有功电费，但属于辅助服务。",
        options=[("A", "对"), ("B", "错")],
        answer="A",
        analysis="对。无功不直接做“有用功”，但支撑电压稳定，是电网安全必需的辅助服务。它不按有功电度收费，而是按无功补偿/辅助服务机制计费。",
    ),
    dict(
        kp_code="ancillary",
        type="single",
        difficulty=3,
        stem="电力行业的“两个细则”通常指？",
        options=[
            ("A", "并网发电机组辅助服务管理细则 + 并网运行管理细则"),
            ("B", "电价细则 + 结算细则"),
            ("C", "用户用电细则 + 售电细则"),
            ("D", "安全细则 + 环保细则"),
        ],
        answer="A",
        analysis="“两个细则”指《并网发电机组辅助服务管理实施细则》和《发电厂并网运行管理实施细则》，由能源监管机构发布，规定了辅助服务的考核、补偿和并网运行管理标准。",
    ),
    dict(
        kp_code="ancillary",
        type="single",
        difficulty=2,
        stem="需求响应（DR）聚合参与辅助服务时，聚合商的角色是？",
        options=[
            ("A", "把大量可调节负荷打包成资源，统一参与调度"),
            ("B", "自己发电卖给电网"),
            ("C", "替用户买绿证"),
            ("D", "给电网修变压器"),
        ],
        answer="A",
        analysis="聚合商把成千上万分散的可调负荷（空调、充电桩、储能等）聚合成一个“虚拟电厂”，统一响应调度调频/调峰指令，让小负荷也能像电源一样提供辅助服务。",
    ),
    dict(
        kp_code="ancillary",
        type="judge",
        difficulty=3,
        stem="黑启动容量不需要专门补偿，因为所有电厂都能黑启动。",
        options=[("A", "对"), ("B", "错")],
        answer="B",
        analysis="错。仅少数具备自启动能力的机组（如水轮机、柴油机组）能黑启动，且维持黑启动能力有成本，所以黑启动作为稀缺辅助服务需要专门补偿。",
    ),

    # ======================== wholesale 批发市场 (10) ========================
    dict(
        kp_code="wholesale",
        type="single",
        difficulty=1,
        stem="电力批发市场主要在哪个层面交易？",
        options=[
            ("A", "发电企业与售电公司/大用户之间的电量批发层面"),
            ("B", "居民家里的插座层面"),
            ("C", "电网公司内部财务层面"),
            ("D", "政府定价层面"),
        ],
        answer="A",
        analysis="批发市场是“电量批发”：发电企业把电成批量卖给售电公司或大用户，类似商品批发市场；售电公司再零售给中小用户，是批发—零售的两层结构。",
    ),
    dict(
        kp_code="wholesale",
        type="single",
        difficulty=1,
        stem="批发市场与零售市场的分界是？",
        options=[
            ("A", "批发卖给中间方（售电公司/大用户），零售卖给终端中小用户"),
            ("B", "批发在白天、零售在晚上"),
            ("C", "批发贵、零售便宜"),
            ("D", "二者是同一回事"),
        ],
        answer="A",
        analysis="批发面向中间方和大用户（量大、专业），零售面向终端中小用户（量小、分散）。两者像商品流通的“批发—零售”两层，电价形成机制也不同。",
    ),
    dict(
        kp_code="wholesale",
        type="judge",
        difficulty=1,
        stem="省间交易通常通过跨省跨区的输电通道完成。",
        options=[("A", "对"), ("B", "错")],
        answer="A",
        analysis="对。省间交易要把电从一个省送到另一个省，必须依托跨省跨区的高压/特高压输电通道完成物理输送，所以省间交易与跨省跨区交易通常相伴。",
    ),
    dict(
        kp_code="wholesale",
        type="single",
        difficulty=2,
        stem="区域电力市场指什么？",
        options=[
            ("A", "跨多个省份、由区域调度/交易机构组织的市场"),
            ("B", "一个市内部的市场"),
            ("C", "一栋楼里的内部市场"),
            ("D", "某售电公司内部账本"),
        ],
        answer="A",
        analysis="区域电力市场是跨越多个省份、由区域级调度/交易机构组织的市场（如曾经的华北、华东等区域市场试点），在比省更大的范围优化资源配置。",
    ),
    dict(
        kp_code="wholesale",
        type="multiple",
        difficulty=2,
        stem="批发市场的典型参与主体包括？",
        options=[
            ("A", "发电企业"),
            ("B", "售电公司"),
            ("C", "电力大用户"),
            ("D", "普通居民家庭"),
        ],
        answer="ABC",
        analysis="批发市场主体是发电企业、售电公司和电力大用户（符合准入条件）。普通居民家庭用电量小、不具备直接参与能力，通过售电公司零售购电，不直接进批发市场。",
    ),
    dict(
        kp_code="wholesale",
        type="single",
        difficulty=2,
        stem="跨省跨区交易的主要目的是？",
        options=[
            ("A", "在更大范围优化资源配置、消纳富余清洁能源"),
            ("B", "让每个省都自给自足不联网"),
            ("C", "把电卖得越贵越好"),
            ("D", "减少发电总量"),
        ],
        answer="A",
        analysis="跨省跨区交易打破省份“各自平衡”的局限，在更大范围调配资源：西部清洁能源送到东部消纳，既优化资源配置又促进新能源消纳，是双碳目标的重要支撑。",
    ),
    dict(
        kp_code="wholesale",
        type="judge",
        difficulty=2,
        stem="省内市场与省间市场完全独立、互不影响。",
        options=[("A", "对"), ("B", "错")],
        answer="B",
        analysis="错。两者通过跨省输电通道和价格耦合相互影响：省间送电改变省内供需，省内余缺也会推升省间交易需求，价格联动而非各自孤立。",
    ),
    dict(
        kp_code="wholesale",
        type="single",
        difficulty=3,
        stem="符合准入条件的高压大用户直接进入批发市场购电，省去了哪一环节？",
        options=[
            ("A", "售电公司（中间零售）环节"),
            ("B", "电网输配环节"),
            ("C", "发电环节"),
            ("D", "政府基金环节"),
        ],
        answer="A",
        analysis="大用户直接进批发市场找电厂购电，省去了售电公司这一中间零售环节（但仍要付电网输配电费和政府性基金），所以叫“直购电”。这是大用户享有的一项权利。",
    ),
    dict(
        kp_code="wholesale",
        type="single",
        difficulty=2,
        stem="特高压把西部电送到东部，这种交易属于哪类？",
        options=[
            ("A", "省间/跨省跨区批发交易"),
            ("B", "省内零售交易"),
            ("C", "居民用电结算"),
            ("D", "辅助服务"),
        ],
        answer="A",
        analysis="特高压跨省送电是典型的省间/跨省跨区批发交易：西部发电企业通过特高压通道把电批发送到东部，是跨省跨区资源优化配置的物理载体。",
    ),
    dict(
        kp_code="wholesale",
        type="judge",
        difficulty=2,
        stem="零售电价通常包含上网电价、输配电价、政府性基金及附加等组成部分。",
        options=[("A", "对"), ("B", "错")],
        answer="A",
        analysis="对。零售电价是用户最终支付的单价，由批发环节的上网电价、输配环节的输配电价、政策性的政府性基金及附加（可能再加售电服务费）共同组成，是全链条汇总。",
    ),
]


def main() -> None:
    init_db()
    db = SessionLocal()
    seeded = 0
    skipped = 0
    per_kp: dict[str, int] = {code: 0 for code in TARGET_KP_CODES}
    try:
        kps = {
            kp.code: kp.id
            for kp in db.execute(select(KnowledgePoint)).scalars().all()
            if kp.code
        }
        for q in QUESTIONS:
            kp_code = q["kp_code"]
            kp_id = kps.get(kp_code)
            if kp_id is None:
                print(f"WARNING: knowledge point code {kp_code!r} not found, skip question")
                continue
            stem = q["stem"]
            sh = _stem_hash(stem)
            exists = db.execute(
                select(Question).where(Question.stem_hash == sh)
            ).scalars().first()
            if exists:
                # 自愈：把历史灌入的旧词汇 exam_level（'中级'/'高级'）规整到
                # 与 difficulty 对应的 four/three，避免 level 过滤把它们排除。
                want = _exam_level_for_difficulty(q["difficulty"])
                if exists.exam_level != want:
                    exists.exam_level = want
                    db.flush()
                skipped += 1
                continue
            options_json = _build_options(q["options"], q["answer"])
            db.add(
                Question(
                    type=q["type"],
                    stem=stem,
                    options=options_json,
                    answer=q["answer"],
                    analysis=q["analysis"],
                    knowledge_point_id=kp_id,
                    source="core",
                    source_type="core",
                    is_ai_generated=False,
                    is_active=True,
                    difficulty=q["difficulty"],
                    exam_level=_exam_level_for_difficulty(q["difficulty"]),
                    stem_hash=sh,
                )
            )
            seeded += 1
            per_kp[kp_code] += 1
        db.commit()
        print(f"seeded {seeded} core questions, skipped {skipped} (already present)")
        for code in TARGET_KP_CODES:
            print(f"  {code}: +{per_kp[code]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
