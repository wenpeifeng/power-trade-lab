"""系统健康检查接口 —— 生产级监控标配。

/api/health        轻量健康检查（存活探测，用于负载均衡）
/api/health/full   完整健康检查（数据库/LLM/向量库/磁盘）
"""
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.common.auth import require_admin

logger = logging.getLogger("health")
router = APIRouter()


@router.get("/health", summary="轻量健康检查(存活探测)", tags=["运维"])
def health(db: Session = Depends(get_db)):
    """轻量探测，用于负载均衡/容器健康检查。快速返回。"""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        return {"status": "error", "error": str(e)[:100]}


@router.get("/health/full", summary="完整健康检查", tags=["运维"])
def health_full(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """完整健康检查：数据库/磁盘/LLM配置/向量库。"""
    checks = {}

    # ① 数据库
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:100]}"

    # ② 磁盘空间
    try:
        stat = os.statvfs(".")
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        checks["disk_free_gb"] = round(free_gb, 1)
        checks["disk"] = "ok" if free_gb > 1 else "low"
    except Exception:
        checks["disk"] = "unknown"

    # ③ 数据量
    try:
        from app.db.models import KnowledgeDoc, DocChunk, Question, User, Policy, PublicData
        checks["data"] = {
            "users": db.query(User).count(),
            "docs": db.query(KnowledgeDoc).count(),
            "chunks": db.query(DocChunk).count(),
            "questions": db.query(Question).count(),
            "policies": db.query(Policy).count(),
            "public_data": db.query(PublicData).count(),
        }
    except Exception as e:
        checks["data"] = f"error: {str(e)[:100]}"

    # ④ LLM配置
    try:
        from app.db.models import UserLLMConfig
        checks["llm"] = {
            "mode": "per_user_byok",
            "configured_users": db.query(UserLLMConfig).filter(
                UserLLMConfig.is_enabled.is_(True)
            ).count(),
        }
    except Exception:
        checks["llm"] = "unknown"

    # ⑤ 向量模型
    try:
        from app.knowledge.embedding import get_embedder
        embedder = get_embedder()
        checks["embedding"] = {
            "loaded": embedder is not None,
            "dim": getattr(embedder, "get_sentence_embedding_dimension", lambda: None)(),
        }
    except Exception as e:
        checks["embedding"] = f"error: {str(e)[:80]}"

    # 总体
    critical_ok = checks.get("database") == "ok"
    return {
        "status": "healthy" if critical_ok else "degraded",
        "timestamp": datetime.now().isoformat(),
        "checks": checks,
    }
