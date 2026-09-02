"""AI 电力交易助手 —— RAG 检索增强生成。

链路：
1. 用户提问
2. 混合检索知识库（BM25 + 向量语义 + RRF 融合）召回 Top-K 相关片段
3. 组装 prompt（系统角色 + 召回上下文 + 用户问题）
4. LLM 生成答案
5. 返回 答案 + 引用来源（哪篇文档的哪个片段）

无 LLM 时降级：直接返回召回的最相关片段作为答案。
"""
import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger("assistant")


def chat(
    db: Session,
    question: str,
    user_id: int,
    history: Optional[list] = None,
    top_k: int = 5,
) -> dict:
    """AI 助手问答。

    返回: {answer, sources: [{doc_id, title, chunk_text, score}], mode}
    """
    # ① 混合检索召回
    from app.knowledge.embedding import retrieve
    sources = retrieve(db, question, top_k=top_k, mode="hybrid")

    if not sources:
        return {
            "answer": "抱歉，知识库中暂未找到与您问题相关的内容。您可以尝试：\n1. 换个关键词提问\n2. 在数据资产中心导入相关文档\n3. 等待爬虫更新更多政策数据",
            "sources": [],
            "mode": "no_match",
        }

    # ② 组装上下文
    context_parts = []
    for i, s in enumerate(sources, 1):
        context_parts.append(
            f"【片段{i}】来源：《{s.get('title', '未知')}》\n{s.get('chunk_text', '')[:500]}"
        )
    context = "\n\n".join(context_parts)

    # ③ 构造 prompt
    history_str = ""
    if history:
        recent = history[-4:]  # 最近2轮对话
        for h in recent:
            role = "用户" if h.get("role") == "user" else "助手"
            history_str += f"{role}: {h.get('content', '')[:200]}\n"

    prompt = f"""请基于以下知识库资料回答用户的问题。

要求：
1. 只基于提供的资料回答，不要编造
2. 如果资料中没有答案，明确说明"现有知识库未覆盖此问题"
3. 回答要专业、准确、有条理
4. 适当引用资料来源（如"根据《xxx》..."）

【知识库资料】
{context}

{('【对话历史】' + chr(10) + history_str) if history_str else ''}

【用户问题】
{question}
"""

    # ④ 调用 LLM
    from app.ai.question_generator import call_llm
    answer = call_llm(
        prompt,
        system="你是电力交易专家助手，基于知识库内容为用户解答电力市场、交易规则、政策法规等问题。回答要准确专业，基于资料不编造。",
        db=db,
        user_id=user_id,
    )

    if not answer:
        # 降级：返回最相关的片段
        top = sources[0]
        answer = (
            f"根据知识库《{top.get('title', '')}》的内容：\n\n"
            f"{top.get('chunk_text', '')[:800]}\n\n"
            f"（当前未接入LLM，以上为最相关的知识库片段。配置LLM后可获得更智能的回答。）"
        )
        mode = "fallback_chunk"
    else:
        mode = "rag"

    # ⑤ 记录引用追踪（更新文档被引用次数）
    try:
        from app.db.models import KnowledgeDoc
        for s in sources[:3]:
            doc_id = s.get("doc_id")
            if doc_id:
                doc = db.get(KnowledgeDoc, doc_id)
                if doc:
                    doc.ref_count = (doc.ref_count or 0) + 1
        db.commit()
    except Exception as e:
        logger.debug(f"引用追踪失败(不影响回答): {e}")

    return {
        "answer": answer,
        "sources": [
            {
                "doc_id": s.get("doc_id"),
                "title": s.get("title", ""),
                "chunk_text": s.get("chunk_text", "")[:200],
                "score": s.get("score", 0),
            }
            for s in sources[:5]
        ],
        "mode": mode,
    }
