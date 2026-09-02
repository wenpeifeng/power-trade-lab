"""自定义教材解析与章节化学习服务。

MinerU 作为独立文档解析服务接入；主应用只保存原文件、Markdown派生物、
章节和学习记录，避免把模型依赖与交易业务进程耦合。
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import (
    LearningBook,
    LearningBookChapter,
    LearningBookProgress,
)

logger = logging.getLogger("study.books")

SUPPORTED_EXTENSIONS = {"pdf", "doc", "docx"}
MAX_FILE_SIZE_MB = 300
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
UPLOAD_CHUNK_SIZE = 4 * 1024 * 1024
PARSER_VERSION = "learning-book-v1"

POWER_TERMS = {
    "电力市场": 8, "电力交易": 8, "现货市场": 7, "中长期交易": 7,
    "日前市场": 6, "实时市场": 6, "辅助服务": 6, "电能量": 5,
    "发电企业": 4, "售电公司": 4, "市场主体": 4, "电力用户": 3,
    "电网": 3, "调度": 4, "出清": 6, "申报": 5, "报价": 4,
    "节点电价": 6, "分区电价": 5, "偏差结算": 6, "结算": 4,
    "输电阻塞": 6, "阻塞电价": 6, "价格帽": 5, "容量市场": 5,
    "市场力": 5, "调峰": 5, "应急机制": 5, "技术支持系统": 5,
    "状态估计": 4, "电能量计量": 4, "SCUC": 5, "SCED": 5,
    "输配电价": 5, "绿电": 5, "绿证": 5, "需求响应": 5,
    "虚拟电厂": 5, "储能": 4, "新能源": 3, "负荷预测": 5,
    "电力系统": 4, "电力调度": 5, "电力监管": 4, "交易中心": 5,
}

CHAPTER_PATTERN = re.compile(
    r"^(#{1,3})\s+(.+?)\s*$",
    re.MULTILINE,
)
PAGE_MARKER_PATTERN = re.compile(r"<!--\s*page:\s*(\d+)\s*-->")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。！？!?；;])\s*|\n+")
DEFINITION_MARKERS = (
    "是指", "指的是", "定义为", "包括", "主要包括", "分为", "由此", "因此",
    "意味着", "作用是", "目的在于", "特点是", "区别在于", "需要", "应当",
)


def save_book_upload(
    db: Session,
    *,
    user_id: int,
    filename: str,
    content: bytes,
    title: Optional[str] = None,
) -> tuple[LearningBook, bool]:
    """保存原始文件并创建后台解析任务记录；同用户同文件只保留一份。"""
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError("仅支持 PDF、DOC、DOCX 教材")
    if not content:
        raise ValueError("上传文件为空")
    if len(content) > MAX_FILE_SIZE:
        raise ValueError(f"教材文件不能超过 {MAX_FILE_SIZE_MB}MB")

    digest = hashlib.sha256(content).hexdigest()
    existing = db.execute(
        select(LearningBook).where(
            LearningBook.user_id == user_id,
            LearningBook.raw_sha256 == digest,
        )
    ).scalar_one_or_none()
    if existing:
        return existing, True

    user_dir = settings.LEARNING_BOOK_DIR / str(user_id)
    raw_dir = user_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{digest[:16]}.{ext}"
    raw_path.write_bytes(content)

    book = LearningBook(
        user_id=user_id,
        title=(title or Path(filename).stem).strip()[:300],
        original_filename=filename[:300],
        file_type=ext,
        file_size=len(content),
        raw_sha256=digest,
        raw_path=str(raw_path),
        parser_status="processing",
        parser_message="文件已入库，正在进行版面解析和行业相关性检测",
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    return book, False


async def save_book_upload_stream(
    db: Session,
    *,
    user_id: int,
    filename: str,
    upload,
    title: Optional[str] = None,
) -> tuple[LearningBook, bool]:
    """分块接收大教材，避免把数百 MB 文件一次性复制进应用内存。"""
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError("仅支持 PDF、DOC、DOCX 教材")

    incoming_dir = settings.LEARNING_BOOK_DIR / "_incoming"
    incoming_dir.mkdir(parents=True, exist_ok=True)
    digest_builder = hashlib.sha256()
    file_size = 0
    staged_path: Optional[Path] = None

    try:
        with tempfile.NamedTemporaryFile(
            prefix="book-",
            suffix=f".{ext}.upload",
            dir=incoming_dir,
            delete=False,
        ) as staged:
            staged_path = Path(staged.name)
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    raise ValueError(f"教材文件不能超过 {MAX_FILE_SIZE_MB}MB")
                digest_builder.update(chunk)
                staged.write(chunk)

        if file_size == 0:
            raise ValueError("上传文件为空")

        digest = digest_builder.hexdigest()
        existing = db.execute(
            select(LearningBook).where(
                LearningBook.user_id == user_id,
                LearningBook.raw_sha256 == digest,
            )
        ).scalar_one_or_none()
        if existing:
            return existing, True

        user_dir = settings.LEARNING_BOOK_DIR / str(user_id)
        raw_dir = user_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"{digest[:16]}.{ext}"
        staged_path.replace(raw_path)
        staged_path = None

        book = LearningBook(
            user_id=user_id,
            title=(title or Path(filename).stem).strip()[:300],
            original_filename=filename[:300],
            file_type=ext,
            file_size=file_size,
            raw_sha256=digest,
            raw_path=str(raw_path),
            parser_status="processing",
            parser_message="文件已入库，正在进行版面解析和行业相关性检测",
        )
        db.add(book)
        db.commit()
        db.refresh(book)
        return book, False
    finally:
        if staged_path and staged_path.exists():
            staged_path.unlink()


def process_book_in_background(book_id: int) -> None:
    """BackgroundTasks 入口：使用独立 Session 完成耗时解析。"""
    db = SessionLocal()
    try:
        process_book(db, book_id)
    except Exception as exc:  # pragma: no cover - 最外层安全网
        logger.exception("教材解析失败 book_id=%s", book_id)
        book = db.get(LearningBook, book_id)
        if book:
            book.parser_status = "failed"
            book.parser_message = f"解析失败：{str(exc)[:500]}"
            db.commit()
    finally:
        db.close()


def process_book(db: Session, book_id: int) -> LearningBook:
    book = db.get(LearningBook, book_id)
    if not book:
        raise ValueError("教材不存在")

    raw_path = Path(book.raw_path)
    markdown, engine = parse_to_markdown(raw_path, book.file_type)
    markdown = normalize_markdown(markdown, book.title)
    if len(re.sub(r"\s+", "", markdown)) < 120:
        raise ValueError("解析文本过少，请检查是否为加密文件或启用 MinerU OCR")
    quality_score, quality_reason = assess_markdown_quality(markdown, engine)
    if quality_score < 0.62:
        raise ValueError(
            f"解析质量不足，未生成课程：{quality_reason}。请使用 MinerU 重新解析"
        )

    md_dir = settings.LEARNING_BOOK_DIR / str(book.user_id) / "markdown"
    md_dir.mkdir(parents=True, exist_ok=True)
    md_path = md_dir / f"{book.raw_sha256[:16]}.md"
    md_path.write_text(markdown, encoding="utf-8")

    relevance, reason, matched = evaluate_power_relevance(book.title, markdown)
    book.markdown_path = str(md_path)
    book.parser_engine = engine
    book.industry_relevance = relevance
    book.relevance_reason = reason
    book.word_count = len(re.sub(r"\s+", "", markdown))

    if relevance < 0.26:
        book.parser_status = "rejected"
        book.parser_message = (
            "已完成 Markdown 解析，但未达到电力行业教材准入阈值；"
            "文件保留在个人原始资产中，不生成课程。"
        )
        db.commit()
        return book

    chapter_count = replace_book_chapters(db, book, markdown, matched)
    book.parser_status = "ready"
    book.parser_message = (
        f"MinerU 解析质量通过（{round(quality_score * 100)}分），"
        f"生成 {chapter_count} 个章节学习单元"
    )
    db.commit()
    db.refresh(book)
    return book


def parse_to_markdown(path: Path, file_type: str) -> tuple[str, str]:
    """优先 MinerU API，其次本机 CLI，PDF 最后使用全文降级解析。"""
    api_url = (
        settings.MINERU_API_URL.strip().rstrip("/")
        if settings.MINERU_ENABLED
        else ""
    )
    errors: list[str] = []
    if api_url:
        try:
            backend = select_mineru_backend(path)
            return (
                parse_with_mineru_api(path, api_url, backend=backend),
                f"mineru-api-{backend}",
            )
        except Exception as exc:
            errors.append(f"MinerU API：{exc}")
            logger.warning("MinerU API 解析失败，尝试降级: %s", exc)

    mineru_cli = shutil.which("mineru")
    if mineru_cli:
        try:
            return parse_with_mineru_cli(path, mineru_cli), "mineru-cli"
        except Exception as exc:
            errors.append(f"MinerU CLI：{exc}")
            logger.warning("MinerU CLI 解析失败，尝试降级: %s", exc)

    if file_type == "pdf":
        if settings.MINERU_ENABLED and errors:
            raise RuntimeError(
                "MinerU 解析未完成，系统已阻止低质量全文降级："
                + "；".join(errors)
            )
        markdown = parse_pdf_fallback(path)
        engine = "pdfplumber-fulltext"
        if errors:
            markdown = (
                f"<!-- MinerU 暂不可用，已使用全文降级解析：{'；'.join(errors)} -->\n\n"
                + markdown
            )
        return markdown, engine

    raise RuntimeError(
        "DOC/DOCX 需要 MinerU 服务。请配置 MINERU_API_URL，"
        "或在本机安装并启动 mineru-api。"
    )


def select_mineru_backend(path: Path) -> str:
    """长教材优先 pipeline，避免 hybrid VLM 分窗推理超过同步接口超时。"""
    configured = settings.MINERU_BACKEND.strip() or "hybrid-engine"
    if configured == "hybrid-engine" and path.stat().st_size >= 80 * 1024 * 1024:
        return "pipeline"
    return configured


def parse_with_mineru_api(
    path: Path,
    api_url: str,
    *,
    backend: Optional[str] = None,
) -> str:
    """调用 MinerU 3.x 同步 `/file_parse` 接口并读取返回 ZIP 中的 Markdown。"""
    timeout = httpx.Timeout(
        connect=10.0,
        read=float(settings.MINERU_TIMEOUT_SEC),
        write=120.0,
        pool=10.0,
    )
    with path.open("rb") as handle, httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{api_url}/file_parse",
            files={"files": (path.name, handle, "application/octet-stream")},
            data={
                "backend": backend or settings.MINERU_BACKEND,
                "effort": settings.MINERU_EFFORT,
                "lang_list": "ch",
                "return_md": "true",
                "response_format_zip": "true",
                "return_original_file": "false",
            },
        )
    response.raise_for_status()
    return extract_markdown_from_response(response)


def extract_markdown_from_response(response: httpx.Response) -> str:
    content_type = response.headers.get("content-type", "").lower()
    if "zip" in content_type or response.content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            md_names = sorted(
                (name for name in archive.namelist() if name.lower().endswith(".md")),
                key=lambda name: (name.count("/"), len(name)),
            )
            if not md_names:
                raise RuntimeError("MinerU 返回包中没有 Markdown 文件")
            return archive.read(md_names[0]).decode("utf-8", errors="replace")

    payload = response.json()
    markdown = find_markdown_value(payload)
    if not markdown:
        raise RuntimeError(f"MinerU 返回结果缺少 Markdown：{str(payload)[:240]}")
    return markdown


def find_markdown_value(value) -> Optional[str]:
    if isinstance(value, dict):
        for key in ("md_content", "markdown", "full_md", "md"):
            item = value.get(key)
            if isinstance(item, str) and len(item) > 20:
                return item
        for item in value.values():
            found = find_markdown_value(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_markdown_value(item)
            if found:
                return found
    return None


def parse_with_mineru_cli(path: Path, executable: str) -> str:
    with tempfile.TemporaryDirectory(prefix="zcode-mineru-") as output_dir:
        proc = subprocess.run(
            [executable, "-p", str(path), "-o", output_dir, "-b", "pipeline"],
            capture_output=True,
            text=True,
            timeout=settings.MINERU_TIMEOUT_SEC,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout)[-500:])
        md_files = sorted(Path(output_dir).rglob("*.md"), key=lambda p: len(p.parts))
        if not md_files:
            raise RuntimeError("MinerU CLI 未生成 Markdown")
        return md_files[0].read_text(encoding="utf-8", errors="replace")


def parse_pdf_fallback(path: Path) -> str:
    """MinerU 未配置时读取全部 PDF 页面，不再截断为前 10 页。"""
    import pdfplumber

    blocks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if not text.strip():
                continue
            blocks.append(f"<!-- page: {page_no} -->")
            lines = []
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if re.match(r"^第[一二三四五六七八九十百\d]+[篇章节]\s*", line):
                    lines.append(f"# {line}")
                elif re.match(r"^\d+(?:\.\d+){0,2}\s+\S+", line):
                    depth = min(3, line.split()[0].count(".") + 1)
                    lines.append(f"{'#' * depth} {line}")
                else:
                    lines.append(line)
            blocks.append("\n\n".join(lines))
    return "\n\n".join(blocks)


def normalize_markdown(markdown: str, title: str) -> str:
    text = markdown.replace("\x00", "").replace("\r\n", "\n").strip()
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    if not re.match(r"^\s*#", text):
        text = f"# {title}\n\n{text}"
    return text


def assess_markdown_quality(markdown: str, engine: str) -> tuple[float, str]:
    """课程准入质量门禁，阻止大型扫描书的低质量字符流进入学习系统。"""
    compact = re.sub(r"\s+", "", markdown)
    if not compact:
        return 0.0, "没有可用文本"
    if engine == "pdfplumber-fulltext" and len(compact) > 80_000:
        return 0.38, "大型 PDF 使用了字符流降级，版面顺序和 OCR 可靠性无法保证"

    replacement_count = compact.count("�") + compact.count("\ufffd")
    control_count = len(re.findall(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", compact))
    suspicious_runs = len(re.findall(r"[′″‥∞□■◆◇]{2,}", compact))
    penalty = min(
        0.75,
        replacement_count / max(len(compact), 1) * 30
        + control_count / max(len(compact), 1) * 40
        + suspicious_runs / max(len(compact) / 2000, 1) * 0.08,
    )
    score = max(0.0, round(1.0 - penalty, 3))
    reason = (
        "文本结构与字符质量正常"
        if score >= 0.8
        else f"检测到替换字符 {replacement_count} 个、异常符号片段 {suspicious_runs} 处"
    )
    return score, reason


def evaluate_power_relevance(title: str, markdown: str) -> tuple[float, str, list[str]]:
    sample = (title + "\n" + markdown[:500_000]).lower()
    matched = [term for term in POWER_TERMS if term.lower() in sample]
    weighted = sum(POWER_TERMS[term] for term in matched)
    title_bonus = sum(
        POWER_TERMS[term] * 1.8 for term in matched if term.lower() in title.lower()
    )
    density_count = sum(sample.count(term.lower()) for term in matched)
    score = min(1.0, (weighted + title_bonus) / 65 + min(0.18, density_count / 500))
    score = round(score, 3)
    if score >= 0.26:
        reason = f"识别到 {len(matched)} 个电力行业核心概念：" + "、".join(matched[:8])
    else:
        reason = (
            "仅识别到少量或未识别到电力市场、交易、调度、结算等行业核心概念"
            + (f"（命中：{'、'.join(matched[:5])}）" if matched else "")
        )
    return score, reason, matched


def split_markdown_chapters(markdown: str, book_title: str) -> list[dict]:
    markdown = _repair_faq_headings(markdown)
    matches = list(CHAPTER_PATTERN.finditer(markdown))
    # 跳过仅有文档总标题的情况。
    useful = [
        m for m in matches
        if _is_reliable_heading(m.group(2), book_title)
    ]
    # “101问 / FAQ / 问答式教材”常把问题、答案小标题全部输出为同级 H2。
    # 当检测到连续编号问题时，只把编号问题作为课程边界，答案中的（1）（2）
    # 留在同一学习单元内，防止课程被切成大量只有标题的碎片。
    question_boundaries = [
        m for m in useful
        if re.match(r"^\s*(?:[1-9]\d{0,2})\s*[.、]\s*\S+", _clean_heading(m.group(2)))
    ]
    if len(question_boundaries) >= 8:
        useful = question_boundaries
    if len(useful) >= 2:
        # MinerU / 降级解析的页码标记通常位于章节标题之前。章节边界应
        # 从紧邻标题的页码标记开始，否则下一章页码会被错误计入上一章。
        starts: list[int] = []
        previous_heading_start = 0
        for match in useful:
            marker_candidates = list(
                PAGE_MARKER_PATTERN.finditer(markdown, previous_heading_start, match.start())
            )
            starts.append(marker_candidates[-1].start() if marker_candidates else match.start())
            previous_heading_start = match.start()
        chapters = []
        for index, match in enumerate(useful):
            start = starts[index]
            if index + 1 < len(starts):
                end = starts[index + 1]
            else:
                appendix = next(
                    (
                        heading for heading in matches
                        if heading.start() > match.start()
                        and re.match(
                            r"^\s*(?:附录|参考文献|后记)\b",
                            _clean_heading(heading.group(2)),
                        )
                    ),
                    None,
                )
                end = appendix.start() if appendix else len(markdown)
            content = markdown[start:end].strip()
            pages = [int(p) for p in PAGE_MARKER_PATTERN.findall(content)]
            chapters.append({
                "title": _clean_heading(match.group(2)),
                "content": content,
                "page_start": min(pages) if pages else None,
                "page_end": max(pages) if pages else None,
            })
        return chapters[:240]

    # 没有可靠目录时按页标记/字符窗口生成稳定学习单元。
    page_parts = re.split(r"(?=<!--\s*page:\s*\d+\s*-->)", markdown)
    page_parts = [part.strip() for part in page_parts if part.strip()]
    chunks: list[str] = []
    current = ""
    for part in page_parts or [markdown]:
        if current and len(current) + len(part) > 9000:
            chunks.append(current)
            current = part
        else:
            current = f"{current}\n\n{part}".strip()
    if current:
        chunks.append(current)
    return [{
        "title": f"学习单元 {index}",
        "content": f"## 学习单元 {index}\n\n{chunk}",
        "page_start": _page_range(chunk)[0],
        "page_end": _page_range(chunk)[1],
    } for index, chunk in enumerate(chunks[:240], 1)]


def _repair_faq_headings(markdown: str) -> str:
    """利用目录与正文上下文补回扫描书中被识别成普通文本/图片的问答标题。"""
    body_marker = re.search(r"(?m)^#\s+.+(?:基础|技术支持系统)\s*$", markdown)
    if not body_marker:
        return markdown
    toc_text = markdown[:body_marker.start()]
    toc_titles: dict[int, str] = {}
    for match in re.finditer(r"(?m)^\s*([1-9]\d{0,2})\.\s*(.+?)\s*$", toc_text):
        number = int(match.group(1))
        title = re.sub(r"[…·.\s]+(?:\d+)?\s*$", "", match.group(2)).strip()
        if len(title) >= 6:
            toc_titles[number] = f"{number}. {title}"
    if len(toc_titles) < 8:
        return markdown

    def numbered_headings(text: str) -> dict[int, re.Match]:
        result = {}
        for item in re.finditer(r"(?m)^#{1,3}\s+([1-9]\d{0,2})\.\s*\S+.*$", text):
            result[int(item.group(1))] = item
        return result

    for number in sorted(toc_titles):
        existing = numbered_headings(markdown)
        if number in existing:
            continue
        body_start = body_marker.start()
        plain = re.search(
            rf"(?m)^(?!#)\s*{number}\.\s*(\S.+?)\s*$",
            markdown[body_start:],
        )
        if plain:
            absolute = body_start + plain.start()
            markdown = markdown[:absolute] + "## " + markdown[absolute:]
            continue

        previous_numbers = [value for value in existing if value < number]
        next_numbers = [value for value in existing if value > number]
        if not previous_numbers or not next_numbers:
            continue
        left = existing[max(previous_numbers)].end()
        right = existing[min(next_numbers)].start()
        title = toc_titles[number]
        concepts = [
            term for term in POWER_TERMS
            if term in title and len(term) >= 2
        ]
        candidates = list(re.finditer(r"(?m)^##\s+.+$", markdown[left:right]))
        ranked = sorted(
            (
                (sum(3 for term in concepts if term in item.group(0)), item)
                for item in candidates
            ),
            key=lambda pair: (-pair[0], pair[1].start()),
        )
        if ranked and ranked[0][0] > 0:
            absolute = left + ranked[0][1].start()
            markdown = (
                markdown[:absolute]
                + f"## {title}\n\n"
                + markdown[absolute:]
            )
    return markdown


def replace_book_chapters(
    db: Session,
    book: LearningBook,
    markdown: str,
    matched_terms: list[str],
    *,
    use_llm: bool = True,
) -> int:
    """以通过质量门禁的 Markdown 原子替换课程章节与派生学习资产。"""
    runtime_config = None
    if use_llm:
        try:
            from app.ai.credentials import get_user_runtime_config
            runtime_config = get_user_runtime_config(db, book.user_id)
        except RuntimeError:
            logger.warning("教材 AI 配置无法解密，已使用规则模式 book_id=%s", book.id)
    chapters = split_markdown_chapters(markdown, book.title)
    if not chapters:
        raise ValueError("未识别到可靠章节结构，请检查 MinerU Markdown 标题层级")
    db.execute(
        delete(LearningBookProgress).where(LearningBookProgress.book_id == book.id)
    )
    db.execute(delete(LearningBookChapter).where(LearningBookChapter.book_id == book.id))
    db.flush()
    for index, chapter in enumerate(chapters, 1):
        summary, learning_assets, quiz = build_chapter_learning_assets(
            chapter["title"],
            chapter["content"],
            matched_terms,
            use_llm=bool(runtime_config) and index <= 20,
            runtime_config=runtime_config,
        )
        db.add(LearningBookChapter(
            book_id=book.id,
            chapter_order=index,
            title=chapter["title"][:300],
            markdown_content=chapter["content"],
            summary=summary,
            key_points=json.dumps(learning_assets, ensure_ascii=False),
            quiz_json=json.dumps(quiz, ensure_ascii=False),
            word_count=len(re.sub(r"\s+", "", chapter["content"])),
            source_page_start=chapter.get("page_start"),
            source_page_end=chapter.get("page_end"),
        ))
    book.chapter_count = len(chapters)
    return len(chapters)


def _clean_heading(value: str) -> str:
    title = re.sub(r"<[^>]+>", "", value)
    title = re.sub(r"!\[[^\]]*]\([^)]*\)", "", title)
    title = re.sub(r"\s+", " ", title).strip(" \t#*_-—|")
    title = re.sub(r"^[·•●○]+\s*", "", title)
    return title[:300]


def _is_reliable_heading(value: str, book_title: str) -> bool:
    title = _clean_heading(value)
    if not title or title == book_title.strip() or len(title) < 4 or len(title) > 180:
        return False
    if re.fullmatch(r"(?:第?\s*\d+\s*页?|page\s*\d+|\d+)", title, re.I):
        return False
    if re.search(r"[′″‥∞□■◆◇〕〗〙〛]", title):
        return False
    if re.fullmatch(r"\d{1,3}\s+[\u4e00-\u9fff]{1,4}", title):
        return False
    visible = re.sub(r"[\w\u4e00-\u9fff，。！？、：；（）《》“”‘’·\s.-]", "", title)
    if len(visible) / max(len(title), 1) > 0.18:
        return False
    return True


def _page_range(content: str) -> tuple[Optional[int], Optional[int]]:
    pages = [int(p) for p in PAGE_MARKER_PATTERN.findall(content)]
    return (min(pages), max(pages)) if pages else (None, None)


def build_chapter_learning_assets(
    title: str,
    content: str,
    book_terms: list[str],
    *,
    use_llm: bool = True,
    runtime_config=None,
) -> tuple[str, dict, list[dict]]:
    plain = _plain_chapter_text(content)
    clean_title = _clean_heading(title)
    if plain.startswith(clean_title):
        plain = plain[len(clean_title):].lstrip(" ：:。")
    sentences = _meaningful_sentences(plain)
    concepts = [
        *[term for term in POWER_TERMS if term in title],
        *[term for term in POWER_TERMS if term in content and term not in title],
    ][:6]
    if not concepts:
        concepts = book_terms[:4]
    ranked = sorted(
        enumerate(sentences),
        key=lambda item: (-_sentence_learning_score(item[1], concepts), item[0]),
    )
    selected = sorted(ranked[:4], key=lambda item: item[0])
    evidence_takeaways = [sentence for _, sentence in selected[:3]]
    takeaways = [
        _plain_takeaway(sentence, concepts, index)
        for index, sentence in enumerate(evidence_takeaways)
    ]
    golden_sentences = [
        sentence for _, sentence in ranked
        if 24 <= len(sentence) <= 150
    ][:3]
    summary = _plain_chapter_summary(clean_title, takeaways, concepts)
    learning_assets = {
        "concepts": concepts,
        "takeaways": takeaways,
        "golden_sentences": golden_sentences,
        "enrichment_mode": "rules",
    }

    prompt = f"""请把以下电力行业教材小节整理为学习资产，所有结论必须来自原文。
章节：{title}
原文：{plain[:6000]}
输出JSON：
{{
  "summary":"不超过90个汉字的大白话导读，直接告诉小白本节解决什么问题",
  "concepts":["4—6个核心概念"],
  "takeaways":[
    {{"title":"不超过12字的一句话结论","explanation":"不超过80字的大白话解释，少用名词堆砌","evidence":"支撑该结论的原文句子"}}
  ],
  "golden_sentences":["2—3条从原文逐字摘录的关键依据"],
  "questions":[
    {{"type":"single或judge","stem":"考查概念、机制、因果或区别的题干","options":[{{"key":"A","text":"..."}},{{"key":"B","text":"..."}},{{"key":"C","text":"..."}},{{"key":"D","text":"..."}}],"answer":"A","analysis":"解释答案并引用原文依据"}}
  ]
}}
要求：
1. 面向第一次接触电力交易的学习者，先讲人话，再保留术语；
2. summary 和 takeaways 不能直接复制整段原文，不能使用“本章围绕……”等空话；
3. evidence 和 golden_sentences 必须能在原文中找到；
4. takeaways 固定生成3条；生成3道题，禁止出现“最合适的复习动作是什么”这类通用学习方法题。"""
    if use_llm:
        from app.ai.question_generator import call_llm
        raw = call_llm(
            prompt,
            system="你是严谨的电力交易教材助教，只能依据给定原文提炼和出题",
            json_mode=True,
            runtime_config=runtime_config,
        )
        if raw:
            try:
                payload = json.loads(raw)
                questions = payload.get("questions") or []
                if questions and payload.get("summary"):
                    ai_takeaways = _normalize_ai_takeaways(
                        payload.get("takeaways"), evidence_takeaways, concepts
                    )
                    ai_takeaways = _ensure_traceable_takeaways(
                        ai_takeaways, sentences, evidence_takeaways
                    )
                    ai_golden = _ensure_traceable_quotes(
                        payload.get("golden_sentences"), sentences, golden_sentences
                    )
                    llm_assets = {
                        "concepts": (payload.get("concepts") or concepts)[:6],
                        "takeaways": ai_takeaways[:3] or takeaways,
                        "golden_sentences": ai_golden[:3],
                        "enrichment_mode": "ai",
                        "enrichment_model": runtime_config.model,
                    }
                    return str(payload["summary"])[:600], llm_assets, questions[:3]
            except (json.JSONDecodeError, TypeError):
                pass

    return summary, learning_assets, _build_source_grounded_quiz(
        title, concepts, evidence_takeaways or sentences
    )


def _plain_chapter_summary(
    title: str,
    takeaways: list[dict],
    concepts: list[str],
) -> str:
    """无模型时也给出短导读，避免把长段原文伪装成摘要。"""
    question = re.sub(r"^\s*\d{1,3}\s*[.、]\s*", "", title).strip(" ？?")
    focus = "、".join(concepts[:3]) or "本节核心机制"
    lead = f"这一节要弄清：{question[:52]}。"
    if takeaways:
        explanation = str(takeaways[0].get("explanation") or "").strip()
        if explanation:
            return _clip_learning_text(f"{lead}{explanation}", 120)
    return _clip_learning_text(f"{lead}先抓住{focus}之间的关系，再回到原文看规则和条件。", 120)


def _plain_takeaway(sentence: str, concepts: list[str], index: int) -> dict:
    """把证据句压缩成“结论 + 解释”，证据仍保留为原文。"""
    evidence = re.sub(r"\s+", " ", sentence).strip()
    explanation = re.sub(r"^\s*[（(]?\d+[）).、]\s*", "", evidence)
    explanation = explanation.replace("应当", "要").replace("需要进行", "要")
    explanation = explanation.replace("进行", "")
    explanation = _clip_learning_text(explanation, 96)
    if any(marker in evidence for marker in ("是指", "定义为", "称为")):
        label = "先弄懂它是什么"
    elif any(marker in evidence for marker in ("包括", "分为", "主要有")):
        label = "记住组成和分类"
    elif any(marker in evidence for marker in ("需要", "必须", "应当", "不能", "缺一不可")):
        label = "注意成立条件"
    elif any(marker in evidence for marker in ("因此", "有利于", "作用", "目的", "确保")):
        label = "理解为什么重要"
    else:
        focus = next((term for term in concepts if term in evidence), "")
        label = f"抓住{focus}的作用" if focus else f"核心结论 {index + 1}"
    return {
        "title": label[:14],
        "explanation": explanation,
        "evidence": evidence,
    }


def _normalize_ai_takeaways(
    value,
    evidence_fallback: list[str],
    concepts: list[str],
) -> list[dict]:
    normalized: list[dict] = []
    if not isinstance(value, list):
        value = []
    for index, item in enumerate(value[:4]):
        if isinstance(item, dict):
            title = str(item.get("title") or "").strip()
            explanation = str(item.get("explanation") or "").strip()
            evidence = str(item.get("evidence") or "").strip()
            if explanation:
                normalized.append({
                    "title": (title or f"核心结论 {index + 1}")[:18],
                    "explanation": _clip_learning_text(explanation, 120),
                    "evidence": evidence,
                })
        elif isinstance(item, str) and item.strip():
            normalized.append(_plain_takeaway(item, concepts, index))
    if normalized:
        return normalized
    return [
        _plain_takeaway(sentence, concepts, index)
        for index, sentence in enumerate(evidence_fallback[:3])
    ]


def _normalized_source_text(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", value or "")


def _source_contains(source: str, evidence: str) -> bool:
    normalized_source = _normalized_source_text(source)
    normalized_evidence = _normalized_source_text(evidence)
    return len(normalized_evidence) >= 16 and normalized_evidence in normalized_source


def _matches_source_sentence(evidence: str, sentences: list[str]) -> bool:
    normalized_evidence = _normalized_source_text(evidence)
    return len(normalized_evidence) >= 16 and any(
        normalized_evidence in _normalized_source_text(sentence)
        for sentence in sentences
    )


def _best_source_evidence(target: str, sentences: list[str]) -> str:
    normalized_target = _normalized_source_text(target)
    if not sentences:
        return ""
    ranked = sorted(
        sentences,
        key=lambda sentence: SequenceMatcher(
            None,
            normalized_target,
            _normalized_source_text(sentence),
        ).ratio(),
        reverse=True,
    )
    return ranked[0]


def _ensure_traceable_takeaways(
    takeaways: list[dict],
    sentences: list[str],
    fallback: list[str],
) -> list[dict]:
    repaired: list[dict] = []
    for index, item in enumerate(takeaways[:3]):
        evidence = str(item.get("evidence") or "").strip()
        if not _matches_source_sentence(evidence, sentences):
            target = " ".join((
                str(item.get("title") or ""),
                str(item.get("explanation") or ""),
            ))
            evidence = _best_source_evidence(target, sentences)
            if not evidence and index < len(fallback):
                evidence = fallback[index]
        repaired.append({**item, "evidence": evidence})
    return repaired


def _ensure_traceable_quotes(
    value,
    sentences: list[str],
    fallback: list[str],
) -> list[str]:
    candidates = value if isinstance(value, list) else []
    result = [
        str(sentence).strip()
        for sentence in candidates
        if isinstance(sentence, str) and _matches_source_sentence(sentence, sentences)
    ]
    for sentence in fallback:
        if sentence not in result:
            result.append(sentence)
    return result[:3]


def _plain_chapter_text(content: str) -> str:
    plain = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    plain = re.sub(r"!\[[^\]]*]\([^)]*\)", " ", plain)
    plain = re.sub(r"<[^>]+>", " ", plain)
    plain = re.sub(r"^[#>*_`|\-]+\s*", "", plain, flags=re.MULTILINE)
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain


def _meaningful_sentences(plain: str) -> list[str]:
    sentences: list[str] = []
    for raw in SENTENCE_SPLIT_PATTERN.split(plain):
        sentence = re.sub(r"\s+", " ", raw).strip(" ，、;；")
        if not 18 <= len(sentence) <= 240:
            continue
        if re.search(r"(ISBN|责任编辑|出版发行|版权所有|目录)", sentence, re.I):
            continue
        if re.search(r"[′″‥∞□■◆◇]{2,}", sentence):
            continue
        if sentence not in sentences:
            sentences.append(sentence)
    return sentences[:80]


def _sentence_learning_score(sentence: str, concepts: list[str]) -> float:
    score = sum(2.0 for marker in DEFINITION_MARKERS if marker in sentence)
    score += sum(1.2 for concept in concepts if concept in sentence)
    if 35 <= len(sentence) <= 130:
        score += 2.0
    if sentence.endswith(("。", "！", "？")):
        score += 0.5
    if sentence.endswith(("？", "?")):
        score -= 1.5
    return score


def _build_source_grounded_quiz(
    title: str,
    concepts: list[str],
    facts: list[str],
) -> list[dict]:
    focus = concepts[0] if concepts else _clean_heading(title)
    lesson_focus = re.sub(r"^\s*\d{1,3}\s*[.、]\s*", "", _clean_heading(title))
    fact_one = _clip_learning_text(
        facts[0] if facts else f"本节围绕{focus}展开说明。"
    )
    fact_two = _clip_learning_text(facts[1] if len(facts) > 1 else fact_one)
    false_one = _counterfactual(fact_one, focus)
    false_two = f"本节认为“{focus}”与电力市场规则、运行约束和交易结果均无关。"
    false_three = f"本节只要求记忆“{focus}”这一名词，不涉及其机制、条件或影响。"
    return [
        {
            "type": "single",
            "stem": f"关于“{lesson_focus[:70]}”，下列哪项最符合本节原文？",
            "options": [
                {"key": "A", "text": fact_one},
                {"key": "B", "text": false_one},
                {"key": "C", "text": false_two},
                {"key": "D", "text": false_three},
            ],
            "answer": "A",
            "analysis": f"原文依据：{fact_one}",
        },
        {
            "type": "single",
            "stem": f"结合本节对“{focus}”的说明，下列哪项有直接原文依据？",
            "options": [
                {"key": "A", "text": fact_two},
                {"key": "B", "text": _counterfactual(fact_two, focus)},
                {"key": "C", "text": false_three},
                {"key": "D", "text": f"原文明确要求忽略“{focus}”对应的适用条件。"},
            ],
            "answer": "A",
            "analysis": f"原文依据：{fact_two}",
        },
        {
            "type": "judge",
            "stem": fact_two,
            "options": [{"key": "对", "text": "对"}, {"key": "错", "text": "错"}],
            "answer": "对",
            "analysis": f"该表述直接来自本节原文：{fact_two}",
        },
    ]


def _counterfactual(sentence: str, focus: str) -> str:
    replacements = (
        ("主要包括", "完全不包括"),
        ("包括", "不包括"),
        ("可以", "不可以"),
        ("需要", "不需要"),
        ("应当", "不应当"),
        ("分为", "不存在任何分类"),
        ("有利于", "不利于"),
        ("提高", "降低"),
    )
    for source, target in replacements:
        if source in sentence:
            return sentence.replace(source, target, 1)
    return f"原文否定“{focus}”具有本节所述的功能、条件或市场影响。"


def _clip_learning_text(value: str, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= limit:
        return text
    clipped = text[:limit]
    punctuation = max(clipped.rfind("。"), clipped.rfind("；"), clipped.rfind("，"))
    if punctuation >= 90:
        return clipped[:punctuation + 1]
    return clipped.rstrip("，；、 ") + "…"


def recalculate_book_progress(db: Session, book: LearningBook, user_id: int) -> None:
    total = max(book.chapter_count, 1)
    completed = db.scalar(
        select(func.count())
        .select_from(LearningBookProgress)
        .where(
            LearningBookProgress.book_id == book.id,
            LearningBookProgress.user_id == user_id,
            LearningBookProgress.status == "completed",
        )
    ) or 0
    book.progress_pct = round(completed / total * 100)
    db.commit()


def iso_now() -> str:
    return datetime.now().astimezone().isoformat()
