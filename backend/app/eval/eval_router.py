"""回归测试路由 —— 一键评估全部模块。

/api/eval/all          一键运行全部模块评估
/api/eval/trade        仅交易撮合
/api/eval/exam         仅考试系统
/api/eval/kb           仅知识库
"""
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.auth import require_admin
from app.db.database import get_db
from app.db.models import User

logger = logging.getLogger("eval_api")
router = APIRouter(prefix="/eval", tags=["回归评估"])


@router.get("/all", summary="一键运行全部模块评估")
def eval_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """运行四大模块的完整评估。管理员权限。

    规范：任何关键改动前后运行此接口，对比 pass_rate 是否回归。
    """
    from app.eval.regression import run_all_evals
    return run_all_evals(db)


@router.get("/trade", summary="交易撮合评估")
def eval_trade(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.trade.eval_matching import run_trade_eval
    return run_trade_eval(db)


@router.get("/exam", summary="考试系统评估")
def eval_exam(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.exam.eval_exam import run_exam_eval
    return run_exam_eval(db)


@router.get("/kb", summary="知识库评估")
def eval_kb(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.knowledge.eval_kb import run_kb_eval
    return run_kb_eval(db)
