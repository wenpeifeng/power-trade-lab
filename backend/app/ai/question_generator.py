"""AI生题引擎 —— LLM 基于政策/课程内容自动生成题目。

策略：
- 输入：政策原文 / 课程知识点 / 历年真题风格
- LLM 生成：单选/多选/判断题 + 选项 + 答案 + 解析 + 考点标签
- 质量校验：格式校验 + 去重 + 人工可审核
- 入库标注：is_ai_generated=True，source_type="ai_generated"

LLM后端可配：Ollama本地 / OpenAI兼容API / 无LLM时用模板生题。
"""
import json
import logging
import re
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.ai.credentials import LLMRuntimeConfig, get_user_runtime_config
from app.common.input_security import safe_http_request
from app.db.models import KnowledgePoint, Question
from crawlers.base import CrawledQuestion

logger = logging.getLogger("ai.generator")


# ============ LLM 调用（支持自然语言/JSON两种输出模式）============

def call_llm(
    prompt: str,
    system: str = "",
    json_mode: bool = False,
    *,
    db: Optional[Session] = None,
    user_id: Optional[int] = None,
    runtime_config: Optional[LLMRuntimeConfig] = None,
) -> Optional[str]:
    """调用LLM。

    json_mode:
    - True: 强制JSON输出（生题/结构化提取用），走 response_format=json_object
    - False: 自然语言输出（RAG问答/摘要用），不加格式约束

    无LLM时返回None，调用方降级。
    """
    config = runtime_config
    if config is None and db is not None and user_id is not None:
        config = get_user_runtime_config(db, user_id)
    # 没有明确的当前用户配置就降级，绝不回退到开发者的全局 Key。
    if config is None or not config.configured:
        return None

    try:
        if config.provider == "ollama":
            return _call_ollama(config, prompt, system, json_mode)
        if config.provider in ("openai", "zhipu", "deepseek"):
            return _call_openai_compat(config, prompt, system, json_mode)
    except Exception as e:
        logger.warning("LLM调用失败，已安全降级: %s", type(e).__name__)
        return None
    return None


def _call_ollama(
    config: LLMRuntimeConfig, prompt: str, system: str, json_mode: bool
) -> Optional[str]:
    """调用本地Ollama。"""
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system or "你是电力交易考试出题专家"},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    if json_mode:
        payload["format"] = "json"
    with httpx.Client(trust_env=False) as client:
        resp = client.post(
            f"{config.base_url}/api/chat",
            json=payload,
            timeout=httpx.Timeout(connect=3.0, read=60.0, write=5.0, pool=3.0),
        )
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content")


def _call_openai_compat(
    config: LLMRuntimeConfig, prompt: str, system: str, json_mode: bool
) -> Optional[str]:
    """调用OpenAI兼容API（支持智谱GLM/DeepSeek/OpenAI）。

    智谱 GLM 等云模型由当前登录用户在“个人 AI 设置”中配置；
    服务端不读取全局开发者 API Key。
    """
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system or "你是电力交易考试出题专家"},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    # 仅生题等JSON场景才加 response_format（智谱GLM对自然语言问答不该约束格式）
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    resp = safe_http_request(
        "POST",
        f"{config.base_url}/chat/completions",
        headers=headers,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=60,
        max_bytes=5 * 1024 * 1024,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ============ 生题 Prompt ============

GEN_PROMPT_TEMPLATE = """请基于以下内容，出 {count} 道电力交易员考试题。

【内容来源】{source_title}
【内容摘要】{content}

要求：
1. 题型混合：单选题(single)、多选题(multiple)、判断题(judge)
2. 每题必须有4个选项(A/B/C/D，判断题为"对/错")，标注正确答案
3. 每题必须有解析说明
4. 标注难度(1简单/2中等/3困难)和考点标签(如"高频""新增""政策关联")
5. 严格按以下JSON格式输出，不要多余文字：

{{
  "questions": [
    {{
      "type": "single",
      "stem": "题干内容",
      "options": [
        {{"key":"A","text":"选项A"}},
        {{"key":"B","text":"选项B"}},
        {{"key":"C","text":"选项C"}},
        {{"key":"D","text":"选项D"}}
      ],
      "answer": "B",
      "analysis": "解析说明",
      "difficulty": 2,
      "tags": ["高频"]
    }}
  ]
}}
"""


def generate_from_policy(
    db: Session, policy_id: int, count: int = 5, llm_user_id: Optional[int] = None
) -> list[dict]:
    """基于一条政策内容生题。"""
    from app.db.models import Policy

    policy = db.get(Policy, policy_id)
    if not policy:
        return []

    content = policy.ai_summary or policy.content or ""
    if len(content) < 20:
        return []

    prompt = GEN_PROMPT_TEMPLATE.format(
        count=count,
        source_title=policy.title,
        content=content[:1000],
    )

    result = call_llm(prompt, json_mode=True, db=db, user_id=llm_user_id)
    if not result:
        # 降级：模板生题（返回 CrawledQuestion 列表统一处理）
        return _template_generate_and_save(db, policy, count)

    questions = _parse_llm_questions(result, source=f"AI生成(基于:{policy.title[:20]})")
    # 入库
    saved = []
    for q in questions:
        qid = _save_question(db, q)
        if qid:
            saved.append(_question_to_dict(q, qid))
    return saved


def _template_generate_and_save(db, policy, count: int) -> list[dict]:
    """模板降级：生成并存入数据库。"""
    title = policy.title[:30]
    q = CrawledQuestion(
        type="judge",
        stem=f"《{title}》是当前电力市场建设的重要政策文件。",
        options=[{"key": "对", "text": "对"}, {"key": "错", "text": "错"}],
        answer="对",
        analysis=f"该文件{policy.doc_number or ''}是电力市场相关政策，表述正确。",
        difficulty=1,
        prediction_tags=["政策关联"],
        source=f"AI生成(基于:{title})",
    )
    qid = _save_question(db, q)
    return [_question_to_dict(q, qid)] if qid else []


def _question_to_dict(q: CrawledQuestion, qid: int) -> dict:
    return {
        "id": qid, "type": q.type, "stem": q.stem, "answer": q.answer,
        "analysis": q.analysis, "difficulty": q.difficulty,
        "source": q.source, "prediction_tags": q.prediction_tags,
    }


def generate_from_knowledge(
    db: Session,
    knowledge_point_code: str,
    count: int = 5,
    llm_user_id: Optional[int] = None,
) -> list[dict]:
    """基于一个知识点生题。"""
    kp = db.query(KnowledgePoint).filter(
        KnowledgePoint.code == knowledge_point_code
    ).first()
    if not kp:
        return []

    prompt = GEN_PROMPT_TEMPLATE.format(
        count=count,
        source_title=f"知识点: {kp.name}",
        content=kp.description or kp.name,
    )

    result = call_llm(prompt, json_mode=True, db=db, user_id=llm_user_id)
    if not result:
        return _template_generate_kp_and_save(db, kp, knowledge_point_code, count)

    questions = _parse_llm_questions(result, source=f"AI生成(知识点:{kp.name})")
    saved = []
    for q in questions:
        q.knowledge_point_code = knowledge_point_code
        qid = _save_question(db, q)
        if qid:
            saved.append(_question_to_dict(q, qid))
    return saved


def _template_generate_kp_and_save(db, kp, kp_code: str, count: int) -> list[dict]:
    """知识点模板降级：生成并存入。"""
    q = CrawledQuestion(
        type="single",
        stem=f"关于{kp.name}，下列说法正确的是？",
        options=[
            {"key": "A", "text": (kp.description or "相关概念")[:40], "is_correct": True},
            {"key": "B", "text": "与上述概念无关"},
            {"key": "C", "text": "完全错误的描述"},
            {"key": "D", "text": "不属于电力交易范畴"},
        ],
        answer="A",
        analysis=f"{kp.name}: {kp.description or '电力交易核心知识点'}",
        difficulty=1, source=f"AI生成(知识点:{kp.name})",
        knowledge_point_code=kp_code,
    )
    qid = _save_question(db, q)
    return [_question_to_dict(q, qid)] if qid else []


# ============ 解析与校验 ============

def _parse_llm_questions(raw: str, source: str = "") -> list[CrawledQuestion]:
    """解析LLM返回的JSON为题目列表。"""
    questions = []
    try:
        # 尝试提取JSON
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            return []
        data = json.loads(json_match.group())
        for item in data.get("questions", []):
            q = _validate_question(item, source)
            if q:
                questions.append(q)
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"LLM题目解析失败: {e}")
    return questions


def _validate_question(item: dict, source: str) -> Optional[CrawledQuestion]:
    """校验单题格式合法性。"""
    qtype = item.get("type", "")
    if qtype not in ("single", "multiple", "judge"):
        return None

    stem = item.get("stem", "").strip()
    if len(stem) < 5:
        return None

    options = item.get("options", [])
    answer = item.get("answer", "").strip()

    # 判断题特殊处理
    if qtype == "judge":
        if not any(k in answer for k in ["对", "错", "A", "B"]):
            return None
        options = [{"key": "对", "text": "对"}, {"key": "错", "text": "错"}]
        answer = answer if answer in ("对", "错") else ("对" if "对" in answer else "错")
    else:
        if len(options) < 2:
            return None
        # 标注正确选项
        correct_keys = set(answer.replace(" ", ""))
        opts = []
        for o in options:
            key = o.get("key", "")
            text = o.get("text", "").strip()
            if key and text:
                opts.append({"key": key, "text": text[:100], "is_correct": key in correct_keys})

    return CrawledQuestion(
        type=qtype, stem=stem[:300], options=options if qtype == "judge" else opts,
        answer=answer, analysis=item.get("analysis", ""),
        difficulty=int(item.get("difficulty", 2)),
        source=source, prediction_tags=item.get("tags"),
    )


def _save_question(db: Session, q: CrawledQuestion) -> Optional[int]:
    """保存题目到数据库（去重）。"""
    import hashlib

    stem_hash = hashlib.md5(q.stem.encode()).hexdigest()[:16]
    exists = db.query(Question).filter(Question.stem_hash == stem_hash).first()
    if exists:
        return None

    kp_id = None
    if q.knowledge_point_code:
        kp = db.query(KnowledgePoint).filter(
            KnowledgePoint.code == q.knowledge_point_code
        ).first()
        if kp:
            kp_id = kp.id

    question = Question(
        type=q.type, stem=q.stem,
        options=json.dumps(q.options, ensure_ascii=False),
        answer=q.answer, analysis=q.analysis, difficulty=q.difficulty,
        knowledge_point_id=kp_id, province=q.province,
        source=q.source, source_type="ai_generated",
        is_ai_generated=True, is_real_exam=False,
        prediction_tags=json.dumps(q.prediction_tags, ensure_ascii=False) if q.prediction_tags else None,
        stem_hash=stem_hash,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question.id


# ============ 模板降级生题逻辑已移至 _template_generate_and_save ============
# （无LLM时生成 CrawledQuestion 并直接入库，保持与LLM路径统一）
