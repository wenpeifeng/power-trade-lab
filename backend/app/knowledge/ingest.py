"""数据资产接入服务 —— 多源统一入口。

核心能力（你强调的"数据资产基座"）：
1. cURL快速抓取：粘贴curl命令 → 解析 → 下载 → 提取正文 → AI总结 → 归档
2. 文件上传：PDF/Word/Excel → 解析 → 入库
3. 手动录入：标题+正文 → 直接入库
4. 飞书导入：批量从飞书知识库拉取文档
5. AI自动总结：摘要/关键词/分类/知识点关联

所有接入的内容统一归档到 KnowledgeDoc，按省份+类型+时间线组织。
"""
import hashlib
import json
import logging
import os
import re
import shlex
from datetime import date
from typing import Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.common.input_security import (
    UnsafeInputError,
    read_upload_limited,
    safe_filename,
    safe_http_request,
    sanitize_outbound_headers,
    validate_file_extension,
    validate_file_signature,
)
from app.db.models import AssetAttachment, KnowledgeDoc, KnowledgePoint

logger = logging.getLogger("ingest")


# ============ cURL 快速抓取（你强调的核心功能）============

def ingest_curl(db: Session, curl_cmd: str, doc_type: str = "industry_news",
                province: Optional[str] = None, tags: Optional[list] = None,
                llm_user_id: Optional[int] = None) -> dict:
    """解析curl命令 → 抓取URL → 提取正文 → AI总结 → 归档到知识库。

    你可以直接粘贴一个curl命令，系统自动完成：抓取→解析→沉淀。
    支持返回HTML（提取正文）或PDF/文件（下载为附件）。
    """
    parsed = _parse_curl(curl_cmd)
    if not parsed or not parsed.get("url"):
        return {"ok": False, "error": "无法从curl命令中解析出URL"}

    url = parsed["url"]
    headers = parsed.get("headers", {})
    method = parsed.get("method", "GET")

    try:
        resp = safe_http_request(
            method,
            url,
            headers=headers,
            data=parsed.get("data"),
            timeout=30,
        )
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")

        # 判断是HTML还是文件
        if "text/html" in content_type or "text/plain" in content_type:
            return _ingest_html(
                db, resp, url, doc_type, province, tags, headers, llm_user_id
            )
        elif "application/pdf" in content_type:
            return _ingest_file(db, resp.content, url, "pdf", doc_type, province, tags)
        elif "word" in content_type or "msword" in content_type:
            return _ingest_file(db, resp.content, url, "doc", doc_type, province, tags)
        else:
            # 尝试当文件处理
            ext = _guess_ext(content_type, url)
            return _ingest_file(db, resp.content, url, ext, doc_type, province, tags)
    except Exception as e:
        logger.error(f"cURL抓取失败 {url}: {e}")
        return {"ok": False, "error": str(e)}


def _parse_curl(curl_cmd: str) -> dict:
    """解析curl命令，提取url/method/headers/data。"""
    result = {"method": "GET", "headers": {}}
    cmd = curl_cmd.strip().replace("\\\n", " ").replace("^&", "&")
    # 去掉开头的 curl
    if cmd.lower().startswith("curl"):
        cmd = cmd[4:].strip()

    try:
        tokens = shlex.split(cmd)
    except ValueError:
        tokens = cmd.split()

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("-X", "--request"):
            result["method"] = tokens[i + 1] if i + 1 < len(tokens) else "GET"
            i += 2
        elif tok in ("-H", "--header"):
            if i + 1 < len(tokens):
                h = tokens[i + 1]
                if ":" in h:
                    k, v = h.split(":", 1)
                    result["headers"][k.strip()] = v.strip()
            i += 2
        elif tok in ("-d", "--data", "--data-raw"):
            if i + 1 < len(tokens):
                result["data"] = tokens[i + 1]
                if result["method"] == "GET":
                    result["method"] = "POST"
            i += 2
        elif tok in ("--compressed", "-s", "-S", "--silent", "--show-error", "-L", "--location", "-k", "--insecure"):
            i += 1
        elif tok.startswith("http"):
            result["url"] = tok.strip("'\"")
            i += 1
        elif tok.startswith("'http") or tok.startswith('"http'):
            result["url"] = tok.strip("'\"")
            i += 1
        else:
            i += 1
    return result


def _ingest_html(
    db: Session, resp, url, doc_type, province, tags, headers, llm_user_id=None
) -> dict:
    """处理HTML响应：提取标题和正文。"""
    from bs4 import BeautifulSoup

    resp.encoding = resp.charset_encoding or "utf-8"
    soup = BeautifulSoup(resp.text, "lxml")

    # 提取标题
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)
    # 优先用og:title
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"]
    if not title:
        title = url.split("/")[-1][:50] or "未命名文档"

    # 提取正文（去掉script/style/nav）
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    # 尝试找正文容器
    article = soup.find("article") or soup.find("div", class_=re.compile("content|article|main"))
    body = article or soup.body or soup
    content = body.get_text(separator="\n", strip=True)[:5000]  # 截断防过大

    # 提取发布日期
    publish_date = _extract_date(soup)

    # AI总结
    ai_summary, ai_keywords = _ai_summarize(db, title, content, llm_user_id)

    # 自动归类
    auto_type = _auto_classify(title, content, doc_type)

    return _save_doc(db, {
        "title": title, "doc_type": auto_type, "province": province,
        "publish_date": publish_date, "source": _domain_name(url),
        "source_url": url, "content": content, "ai_summary": ai_summary,
        "ai_keywords": ai_keywords, "ingest_type": "curl", "tags": tags,
        "source_meta": json.dumps({"original_curl": True}, ensure_ascii=False),
    })


def _ingest_file(db: Session, content_bytes: bytes, url: str, file_type: str,
                 doc_type: str, province: Optional[str], tags: Optional[list]) -> dict:
    """下载文件并归档（PDF/Word等作为附件）。"""
    filename = safe_filename(url.split("/")[-1].split("?")[0], f"download.{file_type}")
    if not os.path.splitext(filename)[1]:
        filename = f"{filename}.{file_type}"
    file_type = validate_file_extension(
        filename,
        {"pdf", "doc", "docx", "xls", "xlsx", "csv", "txt", "md", "json", "xml"},
    )
    validate_file_signature(filename, content_bytes)
    title = os.path.splitext(filename)[0]

    # 保存到本地
    safe_name = hashlib.sha256(url.encode()).hexdigest()[:12] + "_" + filename
    local_path = settings.ATTACHMENT_DIR / safe_name
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(content_bytes)

    ai_summary = f"从 {url} 下载的{file_type}文件，已归档到知识库。"
    result = _save_doc(db, {
        "title": title, "doc_type": doc_type, "province": province,
        "publish_date": date.today().isoformat(), "source": _domain_name(url),
        "source_url": url, "content": ai_summary, "ai_summary": ai_summary,
        "ingest_type": "curl", "tags": tags,
    })

    # 保存附件记录
    if result.get("id"):
        db.add(AssetAttachment(
            doc_id=result["id"], filename=filename, file_type=file_type,
            file_url=url, local_path=str(local_path), file_size=len(content_bytes),
        ))
        db.commit()
    return result


# ============ 文件上传 ============

async def ingest_upload(db: Session, file: UploadFile, doc_type: str = "industry_news",
                        province: Optional[str] = None, title: Optional[str] = None,
                        llm_user_id: Optional[int] = None) -> dict:
    """上传文件 → 解析 → 归档。"""
    max_bytes = max(1, settings.ASSET_UPLOAD_MAX_MB) * 1024 * 1024
    content_bytes = await read_upload_limited(file, max_bytes)
    filename = safe_filename(file.filename, "upload")
    ext = validate_file_extension(
        filename,
        {"pdf", "doc", "docx", "xls", "xlsx", "csv", "txt", "md", "json"},
    )
    validate_file_signature(filename, content_bytes)
    doc_title = title or os.path.splitext(filename)[0]

    # 保存文件
    safe_name = hashlib.sha256(content_bytes).hexdigest()[:12] + "_" + filename
    local_path = settings.ATTACHMENT_DIR / safe_name
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(content_bytes)

    # 提取文本（PDF/Word）
    text_content = _extract_file_text(content_bytes, ext)

    ai_summary, ai_keywords = _ai_summarize(
        db, doc_title, text_content or f"上传文件 {filename}", llm_user_id
    )

    result = _save_doc(db, {
        "title": doc_title, "doc_type": doc_type, "province": province,
        "publish_date": date.today().isoformat(), "source": "用户上传",
        "source_url": None, "content": text_content or "", "ai_summary": ai_summary,
        "ai_keywords": ai_keywords, "ingest_type": "upload",
        "source_meta": json.dumps({"filename": filename, "size": len(content_bytes)}, ensure_ascii=False),
    })

    if result.get("id"):
        db.add(AssetAttachment(
            doc_id=result["id"], filename=filename, file_type=ext,
            local_path=str(local_path), file_size=len(content_bytes),
        ))
        db.commit()
    return result


def _extract_file_text(content_bytes: bytes, ext: str) -> Optional[str]:
    """从PDF/Word提取文本。"""
    import io
    if ext == "pdf":
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(content_bytes)) as pdf:
                return "\n".join((p.extract_text() or "") for p in pdf.pages[:10])
        except Exception as e:
            logger.warning(f"PDF解析失败: {e}")
    return None


# ============ 手动录入 ============

def ingest_manual(db: Session, title: str, content: str, doc_type: str = "industry_news",
                  province: Optional[str] = None, publish_date: Optional[str] = None,
                  source: str = "手动录入", tags: Optional[list] = None,
                  llm_user_id: Optional[int] = None) -> dict:
    """手动录入文章 → AI总结 → 归档。"""
    ai_summary, ai_keywords = _ai_summarize(db, title, content, llm_user_id)
    return _save_doc(db, {
        "title": title, "doc_type": doc_type, "province": province,
        "publish_date": publish_date or date.today().isoformat(),
        "source": source, "source_url": None, "content": content,
        "ai_summary": ai_summary, "ai_keywords": ai_keywords,
        "ingest_type": "manual", "tags": tags,
    })


# ============ AI自动总结归档 ============

def _ai_summarize(
    db: Session,
    title: str,
    content: str,
    llm_user_id: Optional[int] = None,
) -> tuple[Optional[str], Optional[list]]:
    """AI总结：摘要+关键词。无LLM时用规则提取。"""
    from app.ai.question_generator import call_llm

    if not content or len(content) < 20:
        return None, None

    # 尝试LLM总结
    prompt = f"""请用一句话总结以下内容的核心要点（不超过80字），并提取3-5个关键词。
标题：{title}
内容：{content[:1500]}
输出JSON：{{"summary":"...","keywords":["..."]}}"""

    result = call_llm(
        prompt,
        system="你是电力行业内容分析专家，擅长提炼政策要点",
        db=db,
        user_id=llm_user_id,
    )
    if result:
        try:
            import re
            m = re.search(r'\{.*\}', result, re.DOTALL)
            if m:
                data = json.loads(m.group())
                return data.get("summary"), data.get("keywords")
        except (json.JSONDecodeError, Exception):
            pass

    # 降级：规则提取（取前80字做摘要，提取高频词）
    summary = content[:80].replace("\n", " ").strip() + "..."
    keywords = _extract_keywords_rule(title, content)
    return summary, keywords


def _extract_keywords_rule(title: str, content: str) -> list:
    """规则提取关键词。"""
    keywords_pool = ["电力", "市场", "交易", "现货", "中长期", "辅助服务", "绿电", "绿证",
                     "储能", "新能源", "电价", "结算", "偏差", "出清", "政策", "规则",
                     "售电", "发电", "负荷", "调频", "现货", "分布式", "虚拟电厂"]
    found = []
    text = title + content
    for kw in keywords_pool:
        if kw in text and kw not in found:
            found.append(kw)
        if len(found) >= 5:
            break
    return found


def _auto_classify(title: str, content: str, default_type: str) -> str:
    """基于标题内容自动判断文档类型。"""
    text = title + content
    if any(k in text for k in ["发改委", "能源局", "国务院", "国办发"]):
        return "national_policy"
    if any(k in text for k in ["监管局", "监管", "区域"]):
        return "regulation"
    if any(k in text for k in ["交易中心", "出清", "成交", "申报", "公告"]):
        return "exchange_info"
    if any(k in text for k in ["考试", "报名", "鉴定", "培训"]):
        return "exam_info"
    return default_type


# ============ 归档入库 ============

def _save_doc(db: Session, data: dict) -> dict:
    """统一归档入库（去重）。"""
    dedup = hashlib.md5(f"{data['title']}|{data.get('publish_date','')}".encode()).hexdigest()[:16]
    exists = db.query(KnowledgeDoc).filter(KnowledgeDoc.dedup_key == dedup).first()
    if exists:
        return {"ok": True, "dedup": True, "id": exists.id, "title": exists.title}

    # 自动关联知识点
    kp_id = _link_knowledge_point(db, data.get("title", ""), data.get("content", ""))

    # 自动归类（主分类树 + 多维标签）
    from app.knowledge.classifier import auto_classify
    classification = auto_classify(data.get("title", ""), data.get("content", ""))
    category_code = classification.get("category_code")
    facet_tags = classification.get("facet_tags", {})

    doc = KnowledgeDoc(
        title=data["title"], doc_type=data["doc_type"], province=data.get("province"),
        region=data.get("region"), grid=data.get("grid"),
        publish_date=data.get("publish_date"), doc_number=data.get("doc_number"),
        source=data.get("source", ""), source_url=data.get("source_url"),
        content=data.get("content"), ai_summary=data.get("ai_summary"),
        ai_keywords=json.dumps(data["ai_keywords"], ensure_ascii=False) if data.get("ai_keywords") else None,
        ai_interpreted=bool(data.get("ai_summary")),
        knowledge_point_id=kp_id,
        tags=json.dumps(data["tags"], ensure_ascii=False) if data.get("tags") else None,
        category_code=category_code,
        facet_tags=json.dumps(facet_tags, ensure_ascii=False) if facet_tags else None,
        ingest_type=data.get("ingest_type", "manual"),
        source_meta=data.get("source_meta"),
        dedup_key=dedup,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    logger.info(f"归档: [{doc.ingest_type}] {doc.title[:30]} (id={doc.id})")

    # 自动向量化（分块+建索引），支撑语义检索召回
    chunk_count = 0
    try:
        from app.knowledge.embedding import vectorize_document
        vresult = vectorize_document(db, doc.id)
        chunk_count = vresult.get("chunks", 0) if vresult.get("ok") else 0
        if chunk_count:
            logger.info(f"自动向量化: {chunk_count}块")
    except Exception as e:
        logger.warning(f"自动向量化失败(不影响入库): {e}")

    return {"ok": True, "dedup": False, "id": doc.id, "title": doc.title,
            "ai_summary": doc.ai_summary, "ai_keywords": data.get("ai_keywords"),
            "vectorized_chunks": chunk_count}


def _link_knowledge_point(db: Session, title: str, content: str) -> Optional[int]:
    """自动关联知识点（关键词匹配）。"""
    text = title + (content or "")
    points = db.query(KnowledgePoint).filter(KnowledgePoint.code.isnot(None)).all()
    best_match = None
    best_score = 0
    kp_keywords = {
        "industry": ["行业", "认知", "市场", "主体", "发电", "电网", "用户"],
        "wholesale": ["批发", "发电企业", "售电公司"],
        "retail": ["零售", "售电", "终端用户"],
        "mid_long_term": ["中长期", "年度", "月度", "双边协商", "集中竞价"],
        "spot": ["现货", "日前", "实时", "LMP", "节点电价", "出清"],
        "ancillary": ["辅助服务", "调频", "备用", "黑启动"],
        "green": ["绿电", "绿证", "可再生能源", "绿色电力"],
        "settlement": ["结算", "偏差", "电费", "信用"],
    }
    for kp in points:
        kws = kp_keywords.get(kp.code, [])
        score = sum(1 for kw in kws if kw in text)
        if score > best_score:
            best_score = score
            best_match = kp
    return best_match.id if best_match and best_score > 0 else None


# ============ 工具 ============

def _extract_date(soup) -> str:
    """从HTML提取发布日期。"""
    text = soup.get_text()
    m = re.search(r"(20\d{2}[-/年]\d{1,2}[-/月]\d{1,2})", text)
    if m:
        return m.group(1).replace("/", "-").replace("年", "-").replace("月", "-").replace("日", "")
    return date.today().isoformat()


def _domain_name(url: str) -> str:
    """提取域名作为来源名。"""
    m = re.search(r"https?://([^/]+)", url)
    return m.group(1) if m else url[:30]


def _guess_ext(content_type: str, url: str) -> str:
    ct_map = {"pdf": "pdf", "msword": "doc", "spreadsheet": "xlsx",
              "excel": "xlsx", "zip": "zip", "json": "json"}
    for k, v in ct_map.items():
        if k in content_type:
            return v
    ext = os.path.splitext(url.split("?")[0])[1].lstrip(".")
    return ext or "bin"


# ============================================================
# 扩展接入通道（通道6-9）
# ============================================================

# ============ 通道6: Excel/CSV 批量导入 ============

def ingest_spreadsheet(db: Session, content_bytes: bytes, filename: str,
                      target: str = "doc", doc_type: str = "industry_news",
                      province: Optional[str] = None,
                      llm_user_id: Optional[int] = None) -> dict:
    """Excel/CSV 批量导入 → 逐行解析 → 归档。

    target:
    - "doc": 每行作为一篇 KnowledgeDoc（标题+正文列）
    - "question": 每行作为一道 Question（题型/题干/选项/答案列）
    - "policy": 每行作为一篇政策文档（标题/文号/日期/正文列）

    自动识别列名（中英文兼容），跳过空行。
    """
    import io

    ext = os.path.splitext(filename)[1].lstrip(".").lower()
    rows = []

    if ext == "csv":
        # CSV: 尝试常见编码
        text = None
        for enc in ("utf-8", "gbk", "gb2312"):
            try:
                text = content_bytes.decode(enc)
                break
            except (UnicodeDecodeError, Exception):
                continue
        if text is None:
            text = content_bytes.decode("utf-8", errors="ignore")
        import csv
        reader = csv.DictReader(text.splitlines())
        rows = list(reader)
    else:
        # Excel
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content_bytes), read_only=True)
            ws = wb.active
            headers = [str(c.value or "").strip() for c in next(ws.iter_rows(max_row=1))]
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not any(v for v in row):
                    continue
                rows.append({headers[i]: (str(row[i]) if row[i] is not None else "") for i in range(len(headers))})
        except ImportError:
            return {"ok": False, "error": "Excel解析需要openpyxl库"}

    if not rows:
        return {"ok": False, "error": "未解析到数据行"}

    # 列名兼容映射
    col_map = {
        "title": ["title", "标题", "题干", "名称", "政策标题"],
        "content": ["content", "正文", "内容", "政策内容", "详情", "解析"],
        "type": ["type", "题型", "类型"],
        "options": ["options", "选项", "备选"],
        "answer": ["answer", "答案", "正确答案"],
        "doc_number": ["doc_number", "文号", "编号"],
        "publish_date": ["publish_date", "日期", "发布日期", "发文日期"],
        "province": ["province", "省份", "地区"],
        "source": ["source", "来源", "出处"],
    }

    def get_col(row, key):
        for alias in col_map.get(key, [key]):
            for k, v in row.items():
                if k and alias.lower() in k.lower():
                    return v
        return ""

    if target == "question":
        return _import_questions(db, rows, get_col)
    elif target == "policy":
        return _import_policies(db, rows, get_col, doc_type, province, llm_user_id)
    else:
        return _import_docs(db, rows, get_col, doc_type, province, llm_user_id)


def _import_docs(db, rows, get_col, doc_type, province, llm_user_id=None) -> dict:
    imported, skipped = 0, 0
    for row in rows:
        title = get_col(row, "title")
        content = get_col(row, "content")
        if not title:
            skipped += 1
            continue
        ai_summary, ai_keywords = _ai_summarize(db, title, content, llm_user_id)
        _save_doc(db, {
            "title": title, "doc_type": doc_type,
            "province": get_col(row, "province") or province,
            "publish_date": get_col(row, "publish_date") or None,
            "doc_number": get_col(row, "doc_number") or None,
            "source": get_col(row, "source") or "Excel批量导入",
            "content": content, "ai_summary": ai_summary,
            "ai_keywords": ai_keywords, "ingest_type": "spreadsheet",
            "source_meta": json.dumps({"imported_at": date.today().isoformat()}, ensure_ascii=False),
        })
        imported += 1
    return {"ok": True, "target": "doc", "imported": imported, "skipped": skipped}


def _import_questions(db, rows, get_col) -> dict:
    from app.db.models import Question
    imported, skipped = 0, 0
    for row in rows:
        stem = get_col(row, "title") or get_col(row, "content")
        if not stem or len(stem) < 5:
            skipped += 1
            continue
        # 去重
        stem_hash = hashlib.md5(stem.encode()).hexdigest()[:16]
        if db.query(Question).filter(Question.stem_hash == stem_hash).first():
            skipped += 1
            continue
        qtype_raw = get_col(row, "type") or "single"
        qtype = {"单选": "single", "多选": "multiple", "判断": "judge",
                 "single": "single", "multiple": "multiple", "judge": "judge"}.get(qtype_raw, "single")
        answer = get_col(row, "answer")
        options_str = get_col(row, "options")
        # 解析选项（支持 A.xxx|B.xxx 或换行分隔）
        options = _parse_options(options_str, answer)
        db.add(Question(
            type=qtype, stem=stem, options=json.dumps(options, ensure_ascii=False),
            answer=answer, analysis=get_col(row, "content"),
            difficulty=2, source="Excel批量导入", source_type="import",
            stem_hash=stem_hash,
        ))
        imported += 1
    db.commit()
    return {"ok": True, "target": "question", "imported": imported, "skipped": skipped}


def _parse_options(options_str: str, answer: str) -> list:
    """解析选项字符串为标准格式。"""
    if not options_str:
        return []
    import re
    # 按 A. B. 或 A、 B、 或换行分割
    parts = re.split(r'[;\n]|[A-Z][.、]\s*', options_str)
    parts = [p.strip() for p in parts if p.strip()]
    return [{"key": chr(65 + i), "text": p, "is_correct": chr(65 + i) in (answer or "")}
            for i, p in enumerate(parts)]


def _import_policies(db, rows, get_col, doc_type, province, llm_user_id=None) -> dict:
    imported = 0
    for row in rows:
        title = get_col(row, "title")
        content = get_col(row, "content")
        if not title:
            continue
        ai_summary, ai_keywords = _ai_summarize(db, title, content, llm_user_id)
        _save_doc(db, {
            "title": title, "doc_type": doc_type or "national_policy",
            "province": get_col(row, "province") or province,
            "publish_date": get_col(row, "publish_date") or None,
            "doc_number": get_col(row, "doc_number") or None,
            "source": get_col(row, "source") or "Excel批量导入",
            "content": content, "ai_summary": ai_summary,
            "ai_keywords": ai_keywords, "ingest_type": "spreadsheet",
        })
        imported += 1
    return {"ok": True, "target": "policy", "imported": imported}


# ============ 通道7: API 数据源直连 ============

def ingest_api_source(
    db: Session, source_config: dict, llm_user_id: Optional[int] = None
) -> dict:
    """配置式 API 数据源直连。

    source_config:
    {
        "name": "中电联煤价",
        "url": "https://api.example.com/coal-price",
        "method": "GET",
        "headers": {...},
        "params": {...},
        "data_type": "coal",          # clearing/coal/carbon/load
        "province": null,             # 全国性为 null
        "extract": {                  # 从响应JSON提取数据的路径
            "date": "data.date",
            "price": "data.price",
            "unit": "data.unit"
        }
    }
    """
    url = source_config.get("url")
    if not url:
        return {"ok": False, "error": "缺少url"}

    method = source_config.get("method", "GET").upper()
    headers = sanitize_outbound_headers(source_config.get("headers", {}))
    params = source_config.get("params", {})

    try:
        r = safe_http_request(method, url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {"ok": False, "error": f"API请求失败: {e}"}

    # 提取数据
    extract = source_config.get("extract", {})
    data_type = source_config.get("data_type", "industry_news")
    province = source_config.get("province")

    def extract_field(obj, path):
        for p in path.split("."):
            if isinstance(obj, dict):
                obj = obj.get(p)
            elif isinstance(obj, list) and p.isdigit():
                obj = obj[int(p)]
            else:
                return None
        return obj

    # 结构化数值数据 → PublicData
    if data_type in ("clearing", "coal", "carbon", "load", "renewable"):
        return _ingest_api_publicdata(db, data, extract, data_type, province, source_config)

    # 文档型数据 → KnowledgeDoc
    return _ingest_api_docs(db, data, extract, source_config, llm_user_id)


def _ingest_api_publicdata(db, data, extract, data_type, province, config) -> dict:
    from app.db.models import PublicData
    # 支持单条和列表
    items = data if isinstance(data, list) else [data]
    new_count = 0
    for item in items:
        d = extract_field_v2(item, extract.get("date", ""))
        metrics = {}
        for k, path in extract.items():
            if k == "date":
                continue
            val = extract_field_v2(item, path)
            if val is not None:
                metrics[k] = val
        if not d or not metrics:
            continue
        dedup = hashlib.md5(f"{data_type}|{province or 'ALL'}|{d}".encode()).hexdigest()[:16]
        if db.query(PublicData).filter(PublicData.dedup_key == dedup).first():
            continue
        db.add(PublicData(
            data_type=data_type, province=province, data_date=str(d),
            metrics=json.dumps(metrics, ensure_ascii=False),
            source=config.get("name", "API"), dedup_key=dedup,
        ))
        new_count += 1
    db.commit()
    return {"ok": True, "target": "public_data", "data_type": data_type, "new": new_count}


def extract_field_v2(obj, path):
    if not path:
        return None
    for p in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(p)
        elif isinstance(obj, list) and p.isdigit():
            obj = obj[int(p)] if int(p) < len(obj) else None
        else:
            return None
    return obj


def _ingest_api_docs(db, data, extract, config, llm_user_id=None) -> dict:
    items = data if isinstance(data, list) else [data]
    title_key = extract.get("title", "title")
    content_key = extract.get("content", "content")
    imported = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get(title_key) or item.get("title")
        content = item.get(content_key) or item.get("content") or item.get("summary")
        if not title:
            continue
        ai_summary, ai_keywords = _ai_summarize(db, title, content, llm_user_id)
        _save_doc(db, {
            "title": str(title), "doc_type": config.get("doc_type", "industry_news"),
            "province": config.get("province"),
            "source": config.get("name", "API数据源"),
            "content": str(content or ""), "ai_summary": ai_summary,
            "ai_keywords": ai_keywords, "ingest_type": "api",
            "source_meta": json.dumps({"api_url": config.get("url")}, ensure_ascii=False),
        })
        imported += 1
    return {"ok": True, "target": "doc", "imported": imported}


# ============ 通道8: RSS 订阅监听 ============

def ingest_rss(db: Session, feed_url: str, doc_type: str = "industry_news",
               province: Optional[str] = None,
               llm_user_id: Optional[int] = None) -> dict:
    """RSS 订阅源监听 → 新文章自动入库。

    支持电力行业媒体（北极星电力、能源杂志、电力网等）的 RSS feed。
    """
    try:
        r = safe_http_request(
            "GET",
            feed_url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; PowerTradeBot/1.0)"},
        )
        r.raise_for_status()
        xml_text = r.text
    except Exception as e:
        return {"ok": False, "error": f"RSS获取失败: {e}"}

    # 解析 RSS/Atom
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return {"ok": False, "error": f"RSS解析失败: {e}"}

    # RSS 2.0: channel/item; Atom: feed/entry
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = root.findall(".//item") or root.findall(".//atom:entry", ns)

    imported, skipped = 0, 0
    source_name = _domain_name(feed_url)
    for item in items:
        # RSS 2.0
        title_el = item.find("title") or item.find("atom:title", ns)
        link_el = item.find("link") or item.find("atom:link", ns)
        desc_el = item.find("description") or item.find("atom:summary", ns)
        date_el = item.find("pubDate") or item.find("atom:published", ns)

        title = title_el.text if title_el is not None else ""
        link = ""
        if link_el is not None:
            link = link_el.text or link_el.get("href") or ""
        content = desc_el.text if desc_el is not None else ""
        pub_date = ""
        if date_el is not None and date_el.text:
            # 解析 RFC822 日期
            from email.utils import parsedate_to_datetime
            try:
                dt = parsedate_to_datetime(date_el.text)
                pub_date = dt.strftime("%Y-%m-%d")
            except Exception:
                pub_date = date.today().isoformat()

        if not title:
            skipped += 1
            continue

        # 去重（标题+日期）
        dedup = hashlib.md5(f"rss|{title}|{pub_date}".encode()).hexdigest()[:16]
        from app.db.models import KnowledgeDoc as KD
        if db.query(KD).filter(KD.dedup_key == dedup).first():
            skipped += 1
            continue

        ai_summary, ai_keywords = _ai_summarize(
            db, title, content[:1000], llm_user_id
        )
        _save_doc(db, {
            "title": title, "doc_type": doc_type, "province": province,
            "publish_date": pub_date, "source": source_name,
            "source_url": link, "content": content[:5000],
            "ai_summary": ai_summary, "ai_keywords": ai_keywords,
            "ingest_type": "rss", "source_meta": json.dumps({"feed": feed_url}, ensure_ascii=False),
        })
        imported += 1

    return {"ok": True, "feed": feed_url, "imported": imported, "skipped": skipped}


# ============ 通道9: 飞书 Base 表格同步 ============

def ingest_feishu_base(db: Session, app_token: str, table_id: str,
                      target: str = "question", field_mapping: Optional[dict] = None,
                      llm_user_id: Optional[int] = None) -> dict:
    """飞书多维表格(Base) 同步 → 结构化数据批量入库。

    通过 lark-cli 读取 Base 表格数据，按 field_mapping 映射后入库。
    target: question（题库）/ doc（文档）/ policy（政策）
    """
    import subprocess
    try:
        result = subprocess.run(
            ["lark-cli", "base", "records", "list",
             "--app-token", app_token, "--table-id", table_id,
             "--as", "user", "--page-all"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return {"ok": False, "error": f"Base读取失败: {result.stderr[:200]}"}
        data = json.loads(result.stdout)
        records = data.get("data", {}).get("items", [])
    except Exception as e:
        return {"ok": False, "error": f"Base读取异常: {e}"}

    if not records:
        return {"ok": True, "imported": 0, "msg": "表格无数据"}

    # 默认字段映射（飞书Base常见字段名）
    default_mapping = {
        "question": {"stem": ["题干", "题目", "stem"], "options": ["选项", "options"],
                     "answer": ["答案", "answer"], "type": ["题型", "type"],
                     "analysis": ["解析", "分析"]},
        "doc": {"title": ["标题", "title"], "content": ["正文", "内容", "content"],
                "province": ["省份", "province"]},
    }
    mapping = field_mapping or default_mapping.get(target, default_mapping["doc"])

    def get_field(record, keys):
        fields = record.get("fields", {})
        for k in keys:
            for fk, fv in fields.items():
                if k.lower() in fk.lower():
                    return _flatten_field_value(fv)
        return ""

    imported, skipped = 0, 0
    if target == "question":
        from app.db.models import Question
        for rec in records:
            stem = get_field(rec, mapping.get("stem", ["题干"]))
            if not stem or len(stem) < 5:
                skipped += 1
                continue
            stem_hash = hashlib.md5(stem.encode()).hexdigest()[:16]
            if db.query(Question).filter(Question.stem_hash == stem_hash).first():
                skipped += 1
                continue
            options_str = get_field(rec, mapping.get("options", ["选项"]))
            answer = get_field(rec, mapping.get("answer", ["答案"]))
            qtype_raw = get_field(rec, mapping.get("type", ["题型"])) or "单选"
            qtype = {"单选": "single", "多选": "multiple", "判断": "judge"}.get(qtype_raw, "single")
            options = _parse_options(options_str, answer)
            db.add(Question(
                type=qtype, stem=stem, options=json.dumps(options, ensure_ascii=False),
                answer=answer, analysis=get_field(rec, mapping.get("analysis", ["解析"])),
                difficulty=2, source="飞书Base同步", source_type="feishu_base",
                stem_hash=stem_hash,
            ))
            imported += 1
        db.commit()
    else:
        for rec in records:
            title = get_field(rec, mapping.get("title", ["标题"]))
            content = get_field(rec, mapping.get("content", ["正文"]))
            if not title:
                skipped += 1
                continue
            ai_summary, ai_keywords = _ai_summarize(db, title, content, llm_user_id)
            _save_doc(db, {
                "title": title, "doc_type": "industry_news",
                "province": get_field(rec, mapping.get("province", ["省份"])) or None,
                "source": "飞书Base同步", "content": content,
                "ai_summary": ai_summary, "ai_keywords": ai_keywords,
                "ingest_type": "feishu_base",
            })
            imported += 1

    return {"ok": True, "target": target, "imported": imported, "skipped": skipped}


def _flatten_field_value(val) -> str:
    """飞书Base字段值扁平化为字符串（可能是数组/对象）。"""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (list,)):
        parts = []
        for v in val:
            if isinstance(v, dict):
                parts.append(v.get("text") or v.get("name") or str(v))
            else:
                parts.append(str(v))
        return "\n".join(parts)
    if isinstance(val, dict):
        return val.get("text") or val.get("name") or str(val)
    return str(val)
