"""教材工坊 API：上传、MinerU解析、行业准入、章节学习和测验复盘。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.auth import get_current_user
from app.common.rate_limit import SlidingWindowLimiter
from app.config import settings
from app.db.database import get_db
from app.db.models import (
    LearningBook,
    LearningBookChapter,
    LearningBookProgress,
    User,
)
from app.study.book_service import (
    iso_now,
    process_book_in_background,
    recalculate_book_progress,
    save_book_upload_stream,
)

router = APIRouter(prefix="/study/books", tags=["教材工坊"])
_book_parse_limiter = SlidingWindowLimiter(max_attempts=6, window_seconds=3600)


def _enforce_parse_limit(user_id: int) -> None:
    key = f"book-parse:{user_id}"
    state = _book_parse_limiter.check(key)
    if not state.allowed:
        raise HTTPException(
            status_code=429,
            detail="教材解析任务过于频繁，请稍后再试",
            headers={"Retry-After": str(state.retry_after)},
        )
    _book_parse_limiter.record(key)


class ChapterProgressReq(BaseModel):
    action: str  # start/read/note/quiz/complete
    progress_pct: Optional[int] = None
    notes: Optional[str] = None
    answers: Optional[list[str]] = None


def _ensure_book(db: Session, book_id: int, user_id: int) -> LearningBook:
    book = db.get(LearningBook, book_id)
    if not book or book.user_id != user_id:
        raise HTTPException(status_code=404, detail="教材不存在")
    return book


def _safe_json(value: Optional[str], default):
    try:
        return json.loads(value) if value else default
    except (json.JSONDecodeError, TypeError):
        return default


def _learning_assets(value: Optional[str]) -> dict:
    payload = _safe_json(value, [])
    if isinstance(payload, dict):
        return {
            "concepts": payload.get("concepts") or [],
            "takeaways": payload.get("takeaways") or [],
            "golden_sentences": payload.get("golden_sentences") or [],
        }
    return {
        "concepts": payload if isinstance(payload, list) else [],
        "takeaways": [],
        "golden_sentences": [],
    }


def _book_brief(book: LearningBook) -> dict:
    return {
        "id": book.id,
        "title": book.title,
        "original_filename": book.original_filename,
        "file_type": book.file_type,
        "file_size": book.file_size,
        "parser_engine": book.parser_engine,
        "parser_status": book.parser_status,
        "parser_message": book.parser_message,
        "industry_relevance": book.industry_relevance,
        "relevance_reason": book.relevance_reason,
        "chapter_count": book.chapter_count,
        "word_count": book.word_count,
        "progress_pct": book.progress_pct,
        "current_chapter_id": book.current_chapter_id,
        "markdown_ready": bool(book.markdown_path and Path(book.markdown_path).is_file()),
        "created_at": book.created_at.isoformat() if book.created_at else None,
    }


@router.get("/mineru-status", summary="MinerU解析引擎状态")
def mineru_status(_user: User = Depends(get_current_user)):
    api_url = settings.MINERU_API_URL.strip().rstrip("/")
    cli_path = shutil.which("mineru")
    if settings.MINERU_ENABLED and api_url:
        try:
            response = httpx.get(f"{api_url}/health", timeout=3)
            response.raise_for_status()
            payload = response.json()
            return {
                "configured": True,
                "available": True,
                "mode": "api",
                "version": payload.get("version"),
                "protocol_version": payload.get("protocol_version"),
                "backend": settings.MINERU_BACKEND,
                "effort": settings.MINERU_EFFORT,
                "queued_tasks": payload.get("queued_tasks", 0),
                "processing_tasks": payload.get("processing_tasks", 0),
                "message": "MinerU 独立解析服务在线",
            }
        except Exception:
            return {
                "configured": True,
                "available": False,
                "mode": "api",
                "message": "MinerU 服务暂时不可用",
            }
    if settings.MINERU_ENABLED and cli_path:
        return {
            "configured": True,
            "available": True,
            "mode": "cli",
            "message": "检测到本机 MinerU CLI",
        }
    return {
        "configured": bool(settings.MINERU_ENABLED),
        "available": False,
        "mode": "fallback",
        "message": (
            "MinerU 已启用但未配置服务地址"
            if settings.MINERU_ENABLED
            else "MinerU 尚未启用；PDF 可使用全文降级解析，Word 需连接 MinerU"
        ),
    }


@router.post("", summary="上传教材并创建解析任务")
async def upload_book(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _enforce_parse_limit(current_user.id)
    filename = file.filename or "教材.pdf"
    try:
        book, dedup = await save_book_upload_stream(
            db,
            user_id=current_user.id,
            filename=filename,
            upload=file,
            title=title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not dedup:
        background_tasks.add_task(process_book_in_background, book.id)
    return {"book": _book_brief(book), "dedup": dedup}


@router.post("/{book_id}/reprocess", summary="使用当前MinerU配置重新解析教材")
def reprocess_book(
    book_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _enforce_parse_limit(current_user.id)
    book = _ensure_book(db, book_id, current_user.id)
    if book.parser_status == "processing":
        raise HTTPException(status_code=409, detail="教材正在解析，请勿重复提交")
    if not settings.MINERU_ENABLED or not settings.MINERU_API_URL.strip():
        raise HTTPException(status_code=409, detail="MinerU 服务尚未配置")
    book.parser_status = "processing"
    book.parser_message = "已进入 MinerU 高质量重新解析队列；原章节将在成功后替换"
    db.commit()
    background_tasks.add_task(process_book_in_background, book.id)
    return {"book": _book_brief(book)}


@router.get("", summary="我的教材列表")
def list_books(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    books = db.execute(
        select(LearningBook)
        .where(LearningBook.user_id == current_user.id)
        .order_by(LearningBook.created_at.desc(), LearningBook.id.desc())
    ).scalars().all()
    return {
        "items": [_book_brief(book) for book in books],
        "total": len(books),
        "processing": sum(book.parser_status == "processing" for book in books),
        "ready": sum(book.parser_status == "ready" for book in books),
        "rejected": sum(book.parser_status == "rejected" for book in books),
    }


@router.get("/{book_id}", summary="教材目录与学习进度")
def book_detail(
    book_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    book = _ensure_book(db, book_id, current_user.id)
    chapters = db.execute(
        select(LearningBookChapter)
        .where(LearningBookChapter.book_id == book.id)
        .order_by(LearningBookChapter.chapter_order)
    ).scalars().all()
    progress_rows = db.execute(
        select(LearningBookProgress).where(
            LearningBookProgress.book_id == book.id,
            LearningBookProgress.user_id == current_user.id,
        )
    ).scalars().all()
    progress_map = {row.chapter_id: row for row in progress_rows}
    return {
        "book": _book_brief(book),
        "chapters": [
            {
                "id": chapter.id,
                "order": chapter.chapter_order,
                "title": chapter.title,
                "summary": chapter.summary,
                "key_points": _learning_assets(chapter.key_points)["concepts"],
                "word_count": chapter.word_count,
                "source_page_start": chapter.source_page_start,
                "source_page_end": chapter.source_page_end,
                "progress": {
                    "status": progress_map[chapter.id].status,
                    "progress_pct": progress_map[chapter.id].progress_pct,
                    "quiz_score": progress_map[chapter.id].quiz_score,
                } if chapter.id in progress_map else {
                    "status": "not_started", "progress_pct": 0, "quiz_score": None,
                },
            }
            for chapter in chapters
        ],
    }


@router.get("/{book_id}/markdown", summary="导出MinerU Markdown")
def download_markdown(
    book_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    book = _ensure_book(db, book_id, current_user.id)
    if not book.markdown_path or not Path(book.markdown_path).is_file():
        raise HTTPException(status_code=404, detail="Markdown 尚未生成")
    return FileResponse(
        book.markdown_path,
        media_type="text/markdown; charset=utf-8",
        filename=f"{book.title}.md",
    )


@router.get("/{book_id}/chapters/{chapter_id}", summary="章节学习内容")
def chapter_detail(
    book_id: int,
    chapter_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    book = _ensure_book(db, book_id, current_user.id)
    if book.parser_status != "ready":
        raise HTTPException(status_code=409, detail="教材尚未完成解析或未通过行业准入")
    chapter = db.get(LearningBookChapter, chapter_id)
    if not chapter or chapter.book_id != book.id:
        raise HTTPException(status_code=404, detail="章节不存在")
    progress = db.execute(
        select(LearningBookProgress).where(
            LearningBookProgress.user_id == current_user.id,
            LearningBookProgress.chapter_id == chapter.id,
        )
    ).scalar_one_or_none()
    quiz = _safe_json(chapter.quiz_json, [])
    assets = _learning_assets(chapter.key_points)
    safe_quiz = [
        {
            "type": question.get("type", "single"),
            "stem": question.get("stem", ""),
            "options": question.get("options", []),
        }
        for question in quiz
    ]
    return {
        "book": _book_brief(book),
        "chapter": {
            "id": chapter.id,
            "order": chapter.chapter_order,
            "title": chapter.title,
            "markdown_content": chapter.markdown_content,
            "summary": chapter.summary,
            "key_points": assets["concepts"],
            "knowledge_takeaways": assets["takeaways"],
            "golden_sentences": assets["golden_sentences"],
            "quiz": safe_quiz,
            "source_page_start": chapter.source_page_start,
            "source_page_end": chapter.source_page_end,
        },
        "progress": {
            "status": progress.status,
            "progress_pct": progress.progress_pct,
            "quiz_score": progress.quiz_score,
            "notes": progress.notes or "",
            "quiz_attempts": _safe_json(progress.quiz_attempts, []),
        } if progress else {
            "status": "not_started",
            "progress_pct": 0,
            "quiz_score": None,
            "notes": "",
            "quiz_attempts": [],
        },
    }


@router.post("/{book_id}/chapters/{chapter_id}/progress", summary="保存章节学习与测验")
def update_chapter_progress(
    book_id: int,
    chapter_id: int,
    req: ChapterProgressReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    book = _ensure_book(db, book_id, current_user.id)
    chapter = db.get(LearningBookChapter, chapter_id)
    if not chapter or chapter.book_id != book.id:
        raise HTTPException(status_code=404, detail="章节不存在")
    progress = db.execute(
        select(LearningBookProgress).where(
            LearningBookProgress.user_id == current_user.id,
            LearningBookProgress.chapter_id == chapter.id,
        )
    ).scalar_one_or_none()
    if not progress:
        progress = LearningBookProgress(
            user_id=current_user.id,
            book_id=book.id,
            chapter_id=chapter.id,
        )
        db.add(progress)
        db.flush()

    response: dict = {"ok": True}
    if req.action in {"start", "read"}:
        if progress.status == "not_started":
            progress.status = "in_progress"
            progress.started_at = iso_now()
        progress.progress_pct = max(
            progress.progress_pct,
            min(95, max(5, req.progress_pct or 15)),
        )
        book.current_chapter_id = chapter.id
    elif req.action == "note":
        progress.notes = (req.notes or "")[:20_000]
    elif req.action == "quiz":
        questions = _safe_json(chapter.quiz_json, [])
        answers = req.answers or []
        items = []
        correct = 0
        for index, question in enumerate(questions):
            user_answer = str(answers[index] if index < len(answers) else "")
            correct_answer = str(question.get("answer", ""))
            is_correct = (
                user_answer.strip().replace(" ", "").upper()
                == correct_answer.strip().replace(" ", "").upper()
            )
            correct += int(is_correct)
            items.append({
                "index": index,
                "stem": question.get("stem", ""),
                "user_answer": user_answer,
                "correct_answer": correct_answer,
                "is_correct": is_correct,
                "analysis": question.get("analysis", ""),
            })
        score = round(correct / max(len(questions), 1) * 100)
        attempts = _safe_json(progress.quiz_attempts, [])
        attempts.append({"at": iso_now(), "score": score, "items": items})
        progress.quiz_attempts = json.dumps(attempts[-20:], ensure_ascii=False)
        progress.quiz_score = score
        progress.status = "in_progress"
        progress.progress_pct = max(progress.progress_pct, 80)
        response["review"] = {"score": score, "items": items}
    elif req.action == "complete":
        progress.status = "completed"
        progress.progress_pct = 100
        progress.completed_at = iso_now()
    else:
        raise HTTPException(status_code=400, detail="不支持的学习动作")

    db.commit()
    recalculate_book_progress(db, book, current_user.id)
    response["progress"] = {
        "status": progress.status,
        "progress_pct": progress.progress_pct,
        "quiz_score": progress.quiz_score,
        "notes": progress.notes or "",
    }
    response["book_progress_pct"] = book.progress_pct
    return response
