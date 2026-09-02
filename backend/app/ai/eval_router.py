"""RAG 评估路由 —— 检索质量评估接口。

/api/ai/eval/run       运行评估（指定mode/top_k）
/api/ai/eval/compare   三模式对比
/api/ai/eval/testset   查看测试集
/api/ai/llm/status     LLM配置状态
/api/ai/llm/config     配置LLM（智谱API Key等）
/api/ai/llm/test       测试LLM连通性
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.credentials import (
    config_status,
    delete_user_llm_config,
    get_user_llm_row,
    save_user_llm_config,
)
from app.common.auth import get_current_user
from app.common.rate_limit import SlidingWindowLimiter
from app.db.database import get_db
from app.db.models import User

logger = logging.getLogger("ai_router")
router = APIRouter(prefix="/ai", tags=["AI助手"])
_llm_test_limiter = SlidingWindowLimiter(max_attempts=5, window_seconds=60)
_eval_limiter = SlidingWindowLimiter(max_attempts=5, window_seconds=600)


def _enforce_user_limit(limiter: SlidingWindowLimiter, key: str, detail: str) -> None:
    state = limiter.check(key)
    if not state.allowed:
        raise HTTPException(
            status_code=429,
            detail=detail,
            headers={"Retry-After": str(state.retry_after)},
        )
    limiter.record(key)


# ============ RAG 评估 ============

@router.get("/eval/testset", summary="查看评估测试集")
def get_testset(current_user: User = Depends(get_current_user)):
    """返回评估测试集概况。"""
    from app.ai.eval.testset import get_test_set, get_test_summary
    cases = get_test_set()
    return {
        "summary": get_test_summary(),
        "cases": [
            {
                "query": tc.query,
                "query_type": tc.query_type,
                "difficulty": tc.difficulty,
                "expected_doc_ids": tc.expected_doc_ids,
                "note": tc.note,
            }
            for tc in cases
        ],
    }


@router.get("/eval/run", summary="运行检索评估")
def run_eval(
    mode: str = Query("hybrid", description="dense/sparse/hybrid"),
    top_k: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """运行指定模式的检索质量评估。"""
    _enforce_user_limit(_eval_limiter, f"eval:{current_user.id}", "评估请求过于频繁")
    from app.ai.eval.evaluator import run_evaluation
    return run_evaluation(db, mode=mode, top_k=top_k)


@router.get("/eval/compare", summary="三种检索模式对比")
def compare_eval(
    top_k: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """对比 dense/sparse/hybrid 三种模式的评估结果。"""
    _enforce_user_limit(_eval_limiter, f"eval:{current_user.id}", "评估请求过于频繁")
    from app.ai.eval.evaluator import compare_modes
    return compare_modes(db, top_k=top_k)


# ============ LLM 配置管理 ============

class LLMConfigReq(BaseModel):
    provider: str = "zhipu"  # zhipu/openai/deepseek/ollama/none
    api_key: str = Field("", max_length=4096)
    base_url: str = Field("", max_length=500)
    model: str = Field("", max_length=150)


@router.get("/llm/status", summary="当前用户的 LLM 配置状态")
def llm_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """只返回当前用户的配置与 Key 末四位，不返回密文或明文。"""
    return config_status(get_user_llm_row(db, current_user.id))


@router.post("/llm/config", summary="配置当前用户自己的 LLM")
def config_llm(
    req: LLMConfigReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        row = save_user_llm_config(
            db,
            current_user.id,
            provider=req.provider,
            api_key=req.api_key,
            base_url=req.base_url,
            model=req.model,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **config_status(row), "message": "个人 AI 配置已加密保存"}


@router.delete("/llm/config", summary="停用并删除当前用户的 LLM Key")
def remove_llm_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    delete_user_llm_config(db, current_user.id)
    return {"ok": True, "message": "个人 AI 配置已删除"}


@router.post("/llm/test", summary="测试LLM连通性")
def test_llm(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """测试当前 LLM 配置是否能正常调用。"""
    _enforce_user_limit(
        _llm_test_limiter,
        f"llm-test:{current_user.id}",
        "模型连接测试过于频繁",
    )
    from app.ai.question_generator import call_llm
    try:
        result = call_llm(
            "请回复'LLM连接成功'这5个字",
            system="你是一个测试助手",
            db=db,
            user_id=current_user.id,
        )
        row = get_user_llm_row(db, current_user.id)
        if result:
            return {
                "ok": True,
                "response": result[:100],
                "provider": row.provider if row else "none",
            }
        return {"ok": False, "error": "LLM返回空（可能未配置或连接失败）"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
