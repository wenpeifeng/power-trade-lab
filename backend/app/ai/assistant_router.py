"""AI 助手路由 —— 电力交易专家问答。

/api/ai/chat       问答（RAG召回+LLM生成）
/api/ai/suggestions 推荐问题
/api/ai/history    聊天历史
"""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, Text
from sqlalchemy.orm import Session

from app.common.auth import get_current_user
from app.common.rate_limit import SlidingWindowLimiter
from app.db.database import get_db
from app.db.models import User

logger = logging.getLogger("ai_router")
router = APIRouter(prefix="/ai", tags=["AI助手"])
_chat_limiter = SlidingWindowLimiter(max_attempts=20, window_seconds=60)


class ChatTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=4000)


class ChatReq(BaseModel):
    question: str = Field(..., min_length=2, max_length=4000)
    history: Optional[list[ChatTurn]] = Field(None, max_length=20)


@router.post("/chat", summary="AI电力交易助手问答")
def chat(
    req: ChatReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """基于知识库的 RAG 问答。

    用户提问 → 混合检索召回知识 → LLM 生成答案 → 返回答案+引用来源。
    """
    from app.ai.assistant import chat as do_chat

    rate_key = f"ai-chat:{current_user.id}"
    state = _chat_limiter.check(rate_key)
    if not state.allowed:
        raise HTTPException(
            status_code=429,
            detail="AI 请求过于频繁，请稍后再试",
            headers={"Retry-After": str(state.retry_after)},
        )
    _chat_limiter.record(rate_key)

    if not req.question or len(req.question.strip()) < 2:
        raise HTTPException(status_code=400, detail="请输入有效问题")

    history = [turn.model_dump() for turn in req.history] if req.history else None
    result = do_chat(db, req.question.strip(), current_user.id, history)

    # 保存聊天历史
    try:
        _save_history(db, current_user.id, req.question, result.get("answer", ""))
    except Exception as e:
        logger.debug(f"保存历史失败: {e}")

    return result


@router.get("/suggestions", summary="推荐问题(引导用户提问)")
def suggestions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回推荐问题列表，引导用户使用 AI 助手。"""
    return {
        "questions": [
            "电力现货市场和中长期市场有什么区别？",
            "什么是节点边际电价(LMP)？",
            "绿电交易怎么参与？需要什么条件？",
            "浙江电力现货市场的结算规则是什么？",
            "电力交易员证书考哪些内容？",
            "什么是偏差考核？如何避免偏差？",
            "辅助服务市场包括哪些品种？",
            "分布式光伏如何参与电力市场交易？",
        ]
    }


@router.get("/history", summary="聊天历史")
def history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = 20,
):
    """获取当前用户的 AI 助手聊天历史。"""
    from app.db.models import AIChatHistory
    rows = db.execute(
        select(AIChatHistory)
        .where(AIChatHistory.user_id == current_user.id)
        .order_by(AIChatHistory.id.desc())
        .limit(limit)
    ).scalars().all()
    return {
        "history": [
            {
                "id": h.id,
                "question": h.question,
                "answer": h.answer,
                "sources": json.loads(h.sources) if h.sources else [],
                "mode": h.mode,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in reversed(rows)
        ]
    }


def _save_history(db: Session, user_id: int, question: str, answer: str):
    from app.db.models import AIChatHistory
    db.add(AIChatHistory(
        user_id=user_id, question=question, answer=answer,
    ))
    db.commit()
