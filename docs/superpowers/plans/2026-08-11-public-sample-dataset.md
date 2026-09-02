# 公共样本数据集（脱敏发布）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供一套 `backend/scripts/sample_data.py` 工具，让维护者从本地库精选脱敏样本导出到 `data/sample/`（随仓库发布），让下载者 `--load` 后得到非空系统，且绝不泄露个人数据、版权内容、受 ToS 约束的数据。

**Architecture:** 纯函数核心（硬排除 + 脱敏 + 清单加载）+ 三个 CLI 子命令（`--export` / `--load` / `--check`）。导出以只读连接打开本库，按 `manifest.yaml` 白名单取行，应用硬排除与脱敏后写 JSON。灌入按 `dedup_key`/`stem_hash` 幂等。`--check` 对产物做被禁标记 + PII 正则扫描。

**Tech Stack:** Python 3.11/3.12、SQLAlchemy/SQLite（只读导出）、PyYAML、pytest（含 conftest 隔离库约定）。

## Global Constraints

- Python 3.11 或 3.12；依赖走 `backend/requirements.txt`（PyYAML 已是间接依赖，需确认/补加）。
- **白名单优先**：`--export` 只导出 `manifest.yaml` 显式列出的项；未列一律不导出。
- **硬排除优先于 manifest**：即便误写进 manifest，命中排除类仍跳过并告警。
  - qweather：`public_data.source == '和风天气开发者服务'` 或 `data_type IN ('weather_forecast_hourly','weather_observation')`。
  - 真题：`questions.is_real_exam == True` 或 `source`/`source_type` 含"真题"。
  - 教材：`learning_books` 与 `learning_book_chapters` 永不导出（manifest 不支持这两类）。
  - 用户数据：`users`/`user_profiles`/`user_llm_configs`/`answer_logs`/`wrong_answers`/`exam_sessions`/`ai_chat_history`/`trade_*` 永不导出。
- **只读连接**：`--export` 以 `read_only=True` 打开本库，本库零修改。
- **存疑即拒**：导出/检查任一字段无法确认来源/署名或疑似 PII 时，整次失败、退出非零、不输出半成品。
- **PII 扫描**：`--check` 扫描邮箱、手机号、身份证号、`/Users/`、`/home/`、教材书名等。
- **人工复核为强制门槛**：`--check` 通过 ≠ 可发布。
- **最小化优先**：宁缺毋滥。
- 许可证：MIT。

## File Structure

- **Create** `backend/scripts/sample_data.py` — 全部逻辑与 CLI（单文件，职责内聚：硬排除/脱敏/清单/导出/灌入/检查）。
- **Create** `backend/tests/test_sample_data.py` — 单元 + 集成测试，遵循 `tests/conftest.py` 的隔离 SQLite 约定。
- **Create** `data/sample/README.md` — 样本说明 + 每项来源/署名 + 人工复核提示。
- **Create** `data/sample/manifest.yaml.example` — 清单模板（带注释说明，不强制绑定真实 ID）。
- **Modify** `.gitignore` — 显式 `!data/sample/` 守护，确保样本目录不被忽略。
- **Modify** `scripts/open_source_check.py` — 新增 `data/sample/` 被禁标记检查规则。
- **Modify** `README.md` / `docs/系统启动指南.md` — 文档更新（见 Task 8）。

`sample_data.py` 内部函数边界（后续任务 Produces/Consumes 依据）：
- `is_qweather_public_data(row: dict) -> bool`
- `is_excluded_question(row: dict) -> bool`
- `sanitize_policy(row: dict) -> dict`
- `sanitize_question(row: dict) -> dict`
- `sanitize_public_data(row: dict) -> dict`
- `load_manifest(path: Path) -> dict`
- `export(manifest: dict, db_path: Path, out_dir: Path) -> dict`
- `load(sample_dir: Path, db_path: Path) -> dict`
- `check(sample_dir: Path) -> int`
- `main(argv: list[str]) -> int`

---

### Task 1: 硬排除判定函数

**Files:**
- Create: `backend/scripts/sample_data.py`
- Test: `backend/tests/test_sample_data.py`

**Interfaces:**
- Produces: `is_qweather_public_data(row)`, `is_excluded_question(row)`（后续 Task 4 `export` 消费）。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_sample_data.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from sample_data import is_qweather_public_data, is_excluded_question


def test_qweather_detected_by_source():
    row = {"source": "和风天气开发者服务", "data_type": "load"}
    assert is_qweather_public_data(row) is True

def test_qweather_detected_by_data_type():
    row = {"source": "x", "data_type": "weather_forecast_hourly"}
    assert is_qweather_public_data(row) is True
    row2 = {"source": "x", "data_type": "weather_observation"}
    assert is_qweather_public_data(row2) is True

def test_non_qweather_passes():
    row = {"source": "国家能源局", "data_type": "load"}
    assert is_qweather_public_data(row) is False

def test_real_exam_excluded_by_flag():
    row = {"is_real_exam": True, "source": "x", "source_type": ""}
    assert is_excluded_question(row) is True

def test_real_exam_excluded_by_keyword():
    row = {"is_real_exam": False, "source": "2024年真题", "source_type": ""}
    assert is_excluded_question(row) is True
    row2 = {"is_real_exam": False, "source": "x", "source_type": "真题集"}
    assert is_excluded_question(row2) is True

def test_book_derived_excluded_by_source_type():
    # GLM 从《现货市场101问》各章生成的题，source_type='book'，是版权教材衍生
    row = {"is_real_exam": False, "source": "book:1:99", "source_type": "book"}
    assert is_excluded_question(row) is True

def test_book_derived_excluded_by_source_prefix():
    row = {"is_real_exam": False, "source": "book:1:5", "source_type": ""}
    assert is_excluded_question(row) is True

def test_self_authored_question_passes():
    row = {"is_real_exam": False, "source": "core", "source_type": "core"}
    assert is_excluded_question(row) is False
    row2 = {"is_real_exam": False, "source": "自编", "source_type": "manual"}
    assert is_excluded_question(row2) is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sample_data.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'sample_data'`）

- [ ] **Step 3: 写最小实现**

```python
# backend/scripts/sample_data.py
"""公共样本数据集工具 —— 精选脱敏导出 / 幂等灌入 / 发布前检查。

安全原则：白名单优先；硬排除优先于 manifest；只读导出；存疑即拒；人工复核为强制门槛。
"""
from __future__ import annotations

QWEATHER_SOURCES = {"和风天气开发者服务"}
QWEATHER_DATA_TYPES = {"weather_forecast_hourly", "weather_observation"}


def is_qweather_public_data(row: dict) -> bool:
    source = (row.get("source") or "").strip()
    data_type = (row.get("data_type") or "").strip()
    if source in QWEATHER_SOURCES:
        return True
    if data_type in QWEATHER_DATA_TYPES:
        return True
    return False


def is_excluded_question(row: dict) -> bool:
    if row.get("is_real_exam"):
        return True
    source = (row.get("source") or "").strip()
    source_type = (row.get("source_type") or "").strip()
    # 教材派生题：source_type='book' 或 source 以 'book:' 开头
    # （GLM 从《现货市场101问》章节 quiz_json 生成，是版权教材衍生，必须排除）
    if source_type == "book" or source.startswith("book:"):
        return True
    hay = f"{source} {source_type}"
    if "真题" in hay:
        return True
    return False
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sample_data.py -v`
Expected: PASS（6 项）

- [ ] **Step 5: 提交**

```bash
git add backend/scripts/sample_data.py backend/tests/test_sample_data.py
git commit -m "feat(sample): 硬排除判定函数（qweather/真题）"
```

---

### Task 2: 脱敏函数

**Files:**
- Modify: `backend/scripts/sample_data.py`
- Modify: `backend/tests/test_sample_data.py`

**Interfaces:**
- Consumes: Task 1 的排除函数（在 export 阶段调用，本任务函数本身不调，但产出供 Task 4 使用）。
- Produces: `sanitize_policy`、`sanitize_question`、`sanitize_public_data`。

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_sample_data.py`：

```python
import pytest
from sample_data import sanitize_policy, sanitize_question, sanitize_public_data


def test_sanitize_public_data_strips_raw_asset_path_and_keeps_provenance():
    row = {
        "id": 1, "data_type": "carbon", "province": None, "data_date": "2026-07-01",
        "metrics": '{"close":93.77}', "source": "上海环境能源交易所",
        "source_url": "https://overview.cneeex.com/x", "provenance_level": "observed_public",
        "disclosure_scope": "public", "fetched_at": "2026-07-01", "raw_asset_path":
        "/Users/example/.cache/carbon_market/x.json",
        "raw_sha256": "abc", "quality_status": "valid", "dedup_key": "k1",
    }
    out = sanitize_public_data(row)
    assert out["raw_asset_path"] in (None, "")
    assert out["provenance_level"] == "observed_public"
    assert out["source"] == "上海环境能源交易所"
    assert "/Users/" not in str(out)

def test_sanitize_public_data_refuses_missing_source():
    row = {"id": 2, "data_type": "carbon", "data_date": "x", "metrics": "{}",
           "source": "", "source_url": "", "provenance_level": "", "disclosure_scope": "",
           "fetched_at": "", "raw_asset_path": "", "raw_sha256": "", "quality_status": "",
           "dedup_key": ""}
    with pytest.raises(ValueError):
        sanitize_public_data(row)

def test_sanitize_question_drops_real_exam_flag():
    row = {"id": 3, "type": "single", "stem": "q", "options": "[]", "answer": "A",
           "analysis": "", "difficulty": 1, "knowledge_point_id": None, "province": "",
           "source": "自编", "source_type": "原创", "source_url": "", "is_ai_generated": False,
           "is_real_exam": False, "exam_year": None, "exam_level": "", "prediction_tags": "",
           "stem_hash": "h1"}
    out = sanitize_question(row)
    assert "is_real_exam" not in out or out["is_real_exam"] is False
    assert out["source"] == "自编"

def test_sanitize_policy_keeps_attribution():
    row = {"id": 4, "title": "t", "publish_date": "2026-07-01", "doc_number": "",
           "category": "national_policy", "province": "", "source": "国家能源局",
           "source_url": "https://www.nea.gov.cn/x", "content": "...", "ai_summary": "",
           "ai_analysis": "", "priority": 1, "dedup_key": "d1"}
    out = sanitize_policy(row)
    assert out["source"] == "国家能源局"
    assert "/Users/" not in str(out)

def test_sanitize_policy_refuses_missing_source():
    row = {"id": 5, "title": "t", "category": "x", "source": "", "source_url": "",
           "content": "", "priority": 1, "dedup_key": ""}
    with pytest.raises(ValueError):
        sanitize_policy(row)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sample_data.py -v`
Expected: FAIL（ImportError: cannot import name `sanitize_*`）

- [ ] **Step 3: 写最小实现**

追加到 `backend/scripts/sample_data.py`：

```python
import re

_PATH_LEAK = re.compile(r"/(?:Users|home)/")


def _assert_no_path_leak(value: object, field: str) -> None:
    if value and _PATH_LEAK.search(str(value)):
        raise ValueError(f"字段 {field} 含个人绝对路径，存疑即拒")


def _require(field: str, value) -> None:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"字段 {field} 缺失，来源/署名不明确，存疑即拒")


def sanitize_policy(row: dict) -> dict:
    _require("source", row.get("source"))
    _assert_no_path_leak(row.get("content"), "content")
    return {
        "id": row["id"], "title": row["title"], "publish_date": row.get("publish_date"),
        "doc_number": row.get("doc_number"), "category": row["category"],
        "province": row.get("province"), "source": row["source"],
        "source_url": row.get("source_url"), "content": row.get("content"),
        "ai_summary": row.get("ai_summary"), "ai_analysis": row.get("ai_analysis"),
        "priority": row["priority"], "dedup_key": row.get("dedup_key"),
    }


def sanitize_question(row: dict) -> dict:
    _require("source", row.get("source"))
    return {
        "id": row["id"], "type": row["type"], "stem": row["stem"], "options": row["options"],
        "answer": row["answer"], "analysis": row.get("analysis"), "difficulty": row["difficulty"],
        "knowledge_point_id": row.get("knowledge_point_id"), "province": row.get("province"),
        "source": row["source"], "source_type": row.get("source_type"),
        "source_url": row.get("source_url"), "is_ai_generated": row.get("is_ai_generated"),
        "is_real_exam": False, "exam_year": row.get("exam_year"),
        "exam_level": row.get("exam_level"), "prediction_tags": row.get("prediction_tags"),
        "stem_hash": row.get("stem_hash"),
    }


def sanitize_public_data(row: dict) -> dict:
    _require("source", row.get("source"))
    _require("provenance_level", row.get("provenance_level"))
    for f in ("metrics", "source", "source_url"):
        _assert_no_path_leak(row.get(f), f)
    return {
        "id": row["id"], "data_type": row["data_type"], "province": row.get("province"),
        "data_date": row["data_date"], "metrics": row["metrics"], "source": row["source"],
        "source_url": row.get("source_url"), "provenance_level": row["provenance_level"],
        "disclosure_scope": row.get("disclosure_scope"), "fetched_at": row.get("fetched_at"),
        "raw_sha256": row.get("raw_sha256"), "quality_status": row.get("quality_status"),
        "dedup_key": row.get("dedup_key"),
        # raw_asset_path 故意丢弃：含本机绝对路径
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sample_data.py -v`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add backend/scripts/sample_data.py backend/tests/test_sample_data.py
git commit -m "feat(sample): 脱敏函数（路径清洗/署名强制/存疑即拒）"
```

---

### Task 3: 清单加载器

**Files:**
- Modify: `backend/scripts/sample_data.py`
- Modify: `backend/tests/test_sample_data.py`

**Interfaces:**
- Produces: `load_manifest(path) -> dict`（Task 4 `export` 消费）。返回结构：
  `{"policies": {"ids": [...]}, "questions": {"ids": [...]}, "market_data": [{"data_type": str, "date_range": [str, str], "exclude_providers": [str]}]}`。

- [ ] **Step 1: 写失败测试**

追加：

```python
import tempfile
from sample_data import load_manifest

_MANIFEST = """
policies:
  ids: [12, 15]
questions:
  ids: [3, 7]
market_data:
  - data_type: carbon
    date_range: ["2026-07-01", "2026-07-31"]
    exclude_providers: [qweather]
"""

def test_load_manifest_parses_structure():
    import io
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(_MANIFEST); p = f.name
    m = load_manifest(Path(p))
    assert m["policies"]["ids"] == [12, 15]
    assert m["questions"]["ids"] == [3, 7]
    assert m["market_data"][0]["data_type"] == "carbon"
    assert m["market_data"][0]["date_range"] == ["2026-07-01", "2026-07-31"]

def test_load_manifest_rejects_unknown_top_keys():
    import pytest
    bad = "unknown_key: 1\npolicies:\n  ids: []\n"
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(bad); p = f.name
    with pytest.raises(ValueError):
        load_manifest(Path(p))

def test_load_manifest_rejects_book_section():
    import pytest
    bad = "learning_books:\n  ids: [1]\npolicies:\n  ids: []\n"
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(bad); p = f.name
    with pytest.raises(ValueError, match="教材"):
        load_manifest(Path(p))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sample_data.py -v`
Expected: FAIL（ImportError: cannot import name `load_manifest`）

- [ ] **Step 3: 写最小实现**

追加到 `backend/scripts/sample_data.py`：

```python
import yaml

_ALLOWED_TOP = {"policies", "questions", "market_data"}
_FORBIDDEN_TOP = {"learning_books", "learning_book_chapters", "users", "user_profiles",
                  "answer_logs", "wrong_answers", "exam_sessions", "ai_chat_history"}


def load_manifest(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("manifest 必须是顶层映射")
    forbidden = set(data) & _FORBIDDEN_TOP
    if forbidden:
        raise ValueError(f"manifest 不允许教材/用户数据节：{sorted(forbidden)}（教材受版权保护，永不导出）")
    unknown = set(data) - _ALLOWED_TOP
    if unknown:
        raise ValueError(f"manifest 出现未知顶层键：{sorted(unknown)}；仅允许 {sorted(_ALLOWED_TOP)}")
    data.setdefault("policies", {"ids": []})
    data.setdefault("questions", {"ids": []})
    data.setdefault("market_data", [])
    return data
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sample_data.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/scripts/sample_data.py backend/tests/test_sample_data.py
git commit -m "feat(sample): manifest 加载器（白名单节 + 教材/用户节硬拒）"
```

---

### Task 4: 导出（只读 + 白名单 + 硬排除）

**Files:**
- Modify: `backend/scripts/sample_data.py`
- Modify: `backend/tests/test_sample_data.py`

**Interfaces:**
- Consumes: Task 1/2/3 的 `is_qweather_public_data`、`is_excluded_question`、`sanitize_*`、`load_manifest`。
- Produces: `export(manifest, db_path, out_dir) -> dict`（返回 `{"policies": n, "questions": n, "market_data": n, "skipped": [...]}`）。Task 7 CLI 调用。

- [ ] **Step 1: 写失败测试**

追加（用临时 SQLite 建表插行，复用真实 schema 子集）：

```python
import sqlite3
from sample_data import export

def _build_fixture_db(path):
    db = sqlite3.connect(path); c = db.cursor()
    c.executescript("""
    CREATE TABLE policies(id INTEGER PRIMARY KEY, title TEXT, publish_date TEXT, doc_number TEXT,
      category TEXT, province TEXT, source TEXT, source_url TEXT, content TEXT, ai_summary TEXT,
      ai_analysis TEXT, priority INTEGER, dedup_key TEXT);
    CREATE TABLE questions(id INTEGER PRIMARY KEY, type TEXT, stem TEXT, options TEXT, answer TEXT,
      analysis TEXT, difficulty INTEGER, knowledge_point_id INTEGER, province TEXT, source TEXT,
      is_active INTEGER, source_type TEXT, source_url TEXT, is_ai_generated INTEGER,
      is_real_exam INTEGER, exam_year INTEGER, exam_level TEXT, prediction_tags TEXT, stem_hash TEXT);
    CREATE TABLE public_data(id INTEGER PRIMARY KEY, data_type TEXT, province TEXT, data_date TEXT,
      metrics TEXT, source TEXT, source_url TEXT, provenance_level TEXT, disclosure_scope TEXT,
      fetched_at TEXT, raw_asset_path TEXT, raw_sha256 TEXT, quality_status TEXT, dedup_key TEXT);
    """)
    # 一条政策（OK）
    c.execute("INSERT INTO policies VALUES(12,'t1','2026-07-01','','national_policy','','国家能源局','https://nea/x','c','', '',1,'d12')")
    # 一条自编题（OK）
    c.execute("INSERT INTO questions VALUES(3,'single','q','[]','A','',1,NULL,'','自编',1,'原创','',0,0,NULL,'','h3')")
    # 一条真题（应硬排除）
    c.execute("INSERT INTO questions VALUES(9,'single','q','[]','A','',1,NULL,'','2024真题',1,'','',0,1,2024,'','h9')")
    # 一条教材派生题（应硬排除）
    c.execute("INSERT INTO questions VALUES(10,'single','q','[]','A','',1,NULL,'','book:1:5',0,'book','',1,0,NULL,'','h10')")
    # 一条公开数值（OK）
    c.execute("INSERT INTO public_data VALUES(100,'carbon',NULL,'2026-07-01','{\"close\":93}','上海环境能源交易所','https://x','observed_public','public','2026-07-01','','sha','valid','k100')")
    # 一条和风数值（应硬排除）
    c.execute("INSERT INTO public_data VALUES(101,'weather_observation','山东','2026-07-01','{}','和风天气开发者服务','','observed_public','public','','/Users/example/x','','','k101')")
    db.commit(); db.close()

def test_export_whitelist_plus_hard_exclude(tmp_path):
    dbp = tmp_path / "f.db"; _build_fixture_db(str(dbp))
    mp = tmp_path / "m.yaml"
    mp.write_text("policies:\n  ids: [12]\nquestions:\n  ids: [3, 9, 10]\nmarket_data:\n  - data_type: carbon\n    date_range: ['2026-07-01','2026-07-01']\n    exclude_providers: [qweather]\n", encoding="utf-8")
    out = tmp_path / "sample"
    rep = export(load_manifest(mp), dbp, out)
    assert rep["policies"] == 1
    assert rep["questions"] == 1  # 9(真题) 与 10(教材派生) 均被硬排除
    assert rep["market_data"] == 1  # 101 被硬排除
    # 产物文件存在
    assert (out / "policies" / "12.json").is_file()
    assert (out / "questions" / "3.json").is_file()
    assert not (out / "questions" / "9.json").exists()
    assert not (out / "questions" / "10.json").exists()
    # 和风行绝不出现在产物
    import json, glob
    for f in glob.glob(str(out / "market_data" / "*.json")):
        assert "和风" not in Path(f).read_text(encoding="utf-8")
    # 跳过记录含原因
    assert any("真题" in s for s in rep["skipped"])
    assert any("qweather" in s for s in rep["skipped"])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sample_data.py::test_export_whitelist_plus_hard_exclude -v`
Expected: FAIL（ImportError: cannot import name `export`）

- [ ] **Step 3: 写最小实现**

追加到 `backend/scripts/sample_data.py`：

```python
import json
import sqlite3


def _rows(db_path: Path, sql: str, args: tuple) -> list[dict]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)  # 只读
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()


def _write(out_dir: Path, sub: str, row_id, obj: dict) -> None:
    d = out_dir / sub
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{row_id}.json").write_text(
        json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def export(manifest: dict, db_path: Path, out_dir: Path) -> dict:
    skipped: list[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)

    # policies
    p_ids = manifest["policies"]["ids"]
    rows = _rows(db_path, f"SELECT * FROM policies WHERE id IN ({','.join('?'*len(p_ids))})", tuple(p_ids)) if p_ids else []
    n_p = 0
    for r in rows:
        out = sanitize_policy(r)
        _write(out_dir, "policies", r["id"], out); n_p += 1

    # questions（白名单 + 硬排除）
    q_ids = manifest["questions"]["ids"]
    rows = _rows(db_path, f"SELECT * FROM questions WHERE id IN ({','.join('?'*len(q_ids))})", tuple(q_ids)) if q_ids else []
    n_q = 0
    for r in rows:
        if is_excluded_question(r):
            skipped.append(f"question {r['id']}: 真题/real_exam，硬排除")
            continue
        out = sanitize_question(r)
        _write(out_dir, "questions", r["id"], out); n_q += 1

    # public_data（按 data_type + 日期范围，排除 qweather）
    n_d = 0
    for spec in manifest["market_data"]:
        dt = spec["data_type"]
        lo, hi = spec["date_range"]
        rows = _rows(db_path,
            "SELECT * FROM public_data WHERE data_type=? AND data_date>=? AND data_date<=?",
            (dt, lo, hi))
        for r in rows:
            if is_qweather_public_data(r):
                skipped.append(f"public_data {r['id']}: qweather，硬排除")
                continue
            out = sanitize_public_data(r)
            _write(out_dir, "market_data", r["id"], out); n_d += 1

    return {"policies": n_p, "questions": n_q, "market_data": n_d, "skipped": skipped}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sample_data.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/scripts/sample_data.py backend/tests/test_sample_data.py
git commit -m "feat(sample): 导出（只读连接 + 白名单 + 硬排除）"
```

---

### Task 5: 灌入（幂等）

**Files:**
- Modify: `backend/scripts/sample_data.py`
- Modify: `backend/tests/test_sample_data.py`

**Interfaces:**
- Produces: `load(sample_dir, db_path) -> dict`（Task 7 CLI 调用）。按 `dedup_key`（policies/public_data）与 `stem_hash`（questions）幂等。

- [ ] **Step 1: 写失败测试**

追加：

```python
from sample_data import load as load_sample

def test_load_is_idempotent(tmp_path):
    dbp = tmp_path / "empty.db"
    # 建空库（同 schema 子集）
    db = sqlite3.connect(str(dbp)); c = db.cursor()
    c.executescript("""
    CREATE TABLE policies(id INTEGER PRIMARY KEY, title TEXT, publish_date TEXT, doc_number TEXT,
      category TEXT, province TEXT, source TEXT, source_url TEXT, content TEXT, ai_summary TEXT,
      ai_analysis TEXT, priority INTEGER, dedup_key TEXT);
    CREATE TABLE questions(id INTEGER PRIMARY KEY, type TEXT, stem TEXT, options TEXT, answer TEXT,
      analysis TEXT, difficulty INTEGER, knowledge_point_id INTEGER, province TEXT, source TEXT,
      is_active INTEGER, source_type TEXT, source_url TEXT, is_ai_generated INTEGER,
      is_real_exam INTEGER, exam_year INTEGER, exam_level TEXT, prediction_tags TEXT, stem_hash TEXT);
    CREATE TABLE public_data(id INTEGER PRIMARY KEY, data_type TEXT, province TEXT, data_date TEXT,
      metrics TEXT, source TEXT, source_url TEXT, provenance_level TEXT, disclosure_scope TEXT,
      fetched_at TEXT, raw_asset_path TEXT, raw_sha256 TEXT, quality_status TEXT, dedup_key TEXT);
    """); db.commit(); db.close()
    # 先导出一份样本到 sample/
    _build_fixture_db(str(tmp_path / "f.db"))
    mp = tmp_path / "m.yaml"
    mp.write_text("policies:\n  ids: [12]\nquestions:\n  ids: [3]\nmarket_data: []\n", encoding="utf-8")
    sample = tmp_path / "sample"
    export(load_manifest(mp), tmp_path / "f.db", sample)
    # 灌两次
    r1 = load_sample(sample, dbp)
    r2 = load_sample(sample, dbp)
    assert r1["policies"] == 1 and r2["policies"] == 0  # 第二次无新增
    # 库里确实有一条
    db = sqlite3.connect(str(dbp)); 
    assert db.execute("SELECT count(*) FROM policies").fetchone()[0] == 1
    db.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sample_data.py::test_load_is_idempotent -v`
Expected: FAIL（ImportError: cannot import name `load`）

- [ ] **Step 3: 写最小实现**

追加到 `backend/scripts/sample_data.py`：

```python
def _insert_if_absent(con, table: str, dedup_col: str, row: dict, cols: list[str]) -> bool:
    if dedup_col and row.get(dedup_col):
        exists = con.execute(
            f"SELECT 1 FROM {table} WHERE {dedup_col}=?", (row[dedup_col],)).fetchone()
        if exists:
            return False
    con.execute(
        f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
        tuple(row.get(col) for col in cols))
    return True


def load(sample_dir: Path, db_path: Path) -> dict:
    con = sqlite3.connect(str(db_path))
    n = {"policies": 0, "questions": 0, "market_data": 0}
    try:
        for f in sorted((sample_dir / "policies").glob("*.json")):
            row = json.loads(f.read_text(encoding="utf-8"))
            if _insert_if_absent(con, "policies", "dedup_key", row,
                ["id","title","publish_date","doc_number","category","province","source",
                 "source_url","content","ai_summary","ai_analysis","priority","dedup_key"]):
                n["policies"] += 1
        for f in sorted((sample_dir / "questions").glob("*.json")):
            row = json.loads(f.read_text(encoding="utf-8"))
            if _insert_if_absent(con, "questions", "stem_hash", row,
                ["id","type","stem","options","answer","analysis","difficulty","knowledge_point_id",
                 "province","source","is_active","source_type","source_url","is_ai_generated",
                 "is_real_exam","exam_year","exam_level","prediction_tags","stem_hash"]):
                n["questions"] += 1
        for f in sorted((sample_dir / "market_data").glob("*.json")):
            row = json.loads(f.read_text(encoding="utf-8"))
            if _insert_if_absent(con, "public_data", "dedup_key", row,
                ["id","data_type","province","data_date","metrics","source","source_url",
                 "provenance_level","disclosure_scope","fetched_at","raw_sha256",
                 "quality_status","dedup_key"]):
                n["market_data"] += 1
        con.commit()
    finally:
        con.close()
    return n
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sample_data.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/scripts/sample_data.py backend/tests/test_sample_data.py
git commit -m "feat(sample): 幂等灌入（按 dedup_key/stem_hash 去重）"
```

---

### Task 6: 发布前检查（被禁标记 + PII 扫描）

**Files:**
- Modify: `backend/scripts/sample_data.py`
- Modify: `backend/tests/test_sample_data.py`

**Interfaces:**
- Produces: `check(sample_dir) -> int`（0 通过，非零失败；Task 7 CLI 调用）。

- [ ] **Step 1: 写失败测试**

追加：

```python
from sample_data import check

def test_check_passes_clean_dir(tmp_path):
    (tmp_path / "policies").mkdir()
    (tmp_path / "policies" / "1.json").write_text(
        '{"source":"国家能源局","content":"正常政策文本"}', encoding="utf-8")
    assert check(tmp_path) == 0

def test_check_fails_on_qweather_marker(tmp_path):
    (tmp_path / "market_data").mkdir()
    (tmp_path / "market_data" / "1.json").write_text(
        '{"source":"和风天气开发者服务"}', encoding="utf-8")
    assert check(tmp_path) != 0

def test_check_fails_on_users_path(tmp_path):
    (tmp_path / "policies").mkdir()
    (tmp_path / "policies" / "1.json").write_text(
        '{"content":"/Users/example/x"}', encoding="utf-8")
    assert check(tmp_path) != 0

def test_check_fails_on_book_title(tmp_path):
    (tmp_path / "policies").mkdir()
    (tmp_path / "policies" / "1.json").write_text(
        '{"content":"现货市场101问 摘录"}', encoding="utf-8")
    assert check(tmp_path) != 0

def test_check_fails_on_phone(tmp_path):
    (tmp_path / "policies").mkdir()
    (tmp_path / "policies" / "1.json").write_text(
        '{"content":"联系 13800138000"}', encoding="utf-8")
    assert check(tmp_path) != 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sample_data.py -v`
Expected: FAIL（ImportError: cannot import name `check`）

- [ ] **Step 3: 写最小实现**

追加到 `backend/scripts/sample_data.py`：

```python
_BOOK_TITLE = "现货市场101问"
_BANNED_MARKERS = ["和风天气开发者服务", "weather_forecast_hourly", "weather_observation", _BOOK_TITLE]
_PATTERNS = [
    re.compile(r"/Users/"),
    re.compile(r"/home/"),
    re.compile(r"1[3-9]\d{9}"),                      # 手机号
    re.compile(r"\b\d{15}(?:\d{2})?\d?\b"),         # 身份证号粗匹配（15 或 18 位）
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),  # 邮箱
]


def check(sample_dir: Path) -> int:
    failures: list[str] = []
    files = list(sample_dir.rglob("*.json"))
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in _BANNED_MARKERS:
            if m in text:
                failures.append(f"{f}: 含被禁标记 {m}")
        for pat in _PATTERNS:
            if pat.search(text):
                failures.append(f"{f}: 命中 PII/路径模式 {pat.pattern}")
    if failures:
        for line in failures[:20]:
            print(f"CHECK FAIL: {line}")
        return 1
    print(f"CHECK OK: {len(files)} 个文件通过被禁标记/PII 扫描（仍需人工逐文件复核）")
    return 0
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sample_data.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/scripts/sample_data.py backend/tests/test_sample_data.py
git commit -m "feat(sample): 发布前检查（被禁标记 + PII 扫描）"
```

---

### Task 7: CLI 主入口

**Files:**
- Modify: `backend/scripts/sample_data.py`

**Interfaces:**
- Consumes: Task 3/4/5/6 的 `load_manifest`/`export`/`load`/`check`。
- Produces: `main(argv) -> int`，可被 `python -m` 或直接 `python sample_data.py` 调用。

- [ ] **Step 1: 写失败测试**

追加：

```python
from sample_data import main

def test_cli_check_exit_code(tmp_path):
    (tmp_path / "policies").mkdir()
    (tmp_path / "policies" / "1.json").write_text('{"source":"国家能源局"}', encoding="utf-8")
    rc = main(["--check", str(tmp_path)])
    assert rc == 0

def test_cli_unknown_subcommand(tmp_path):
    rc = main(["--frobnicate"])
    assert rc != 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sample_data.py::test_cli_check_exit_code tests/test_sample_data.py::test_cli_unknown_subcommand -v`
Expected: FAIL（ImportError: cannot import name `main`）

- [ ] **Step 3: 写最小实现**

追加到 `backend/scripts/sample_data.py` 末尾：

```python
import argparse
from app.config import settings  # 复用项目配置（DATABASE_URL 等）

_DEFAULT_DB = Path(settings.DATABASE_URL.replace("sqlite:///", ""))
_DEFAULT_MANIFEST = Path(settings.PROJECT_ROOT) / "data" / "sample" / "manifest.yaml"
_DEFAULT_SAMPLE = Path(settings.PROJECT_ROOT) / "data" / "sample"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="公共样本数据集：导出/灌入/检查")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--export", action="store_true", help="从本库导出脱敏样本到 data/sample/")
    g.add_argument("--load", action="store_true", help="把 data/sample/ 灌入本库（幂等）")
    g.add_argument("--check", action="store_true", help="发布前检查 data/sample/")
    ap.add_argument("--manifest", default=str(_DEFAULT_MANIFEST))
    ap.add_argument("--db", default=str(_DEFAULT_DB))
    ap.add_argument("--out", default=str(_DEFAULT_SAMPLE))
    args = ap.parse_args(argv)

    if args.export:
        manifest = load_manifest(Path(args.manifest))
        rep = export(manifest, Path(args.db), Path(args.out))
        print(f"导出完成: {rep}")
        print("⚠ 仍需人工逐文件复核 data/sample/ 后方可提交。")
        return 0
    if args.load:
        rep = load(Path(args.out), Path(args.db))
        print(f"灌入完成（新增）: {rep}")
        return 0
    if args.check:
        return check(Path(args.out))
    return 2  # argparse 已保证互斥，兜底


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sample_data.py -v`
Expected: PASS（全部）

注：`main` 中 `from app.config import settings` 要求以 `backend/` 为 cwd 且 `app` 可导入；测试通过 `sys.path` 插入 `scripts/` 但 `app` 在 `backend/`。若 `import app.config` 失败，改为在函数内 try/except 回退到环境变量默认值——保持测试（`test_cli_check_exit_code` 只走 `--check` 分支，不触达 `settings` 导入）可通过。

- [ ] **Step 5: 提交**

```bash
git add backend/scripts/sample_data.py backend/tests/test_sample_data.py
git commit -m "feat(sample): CLI 主入口（--export/--load/--check）"
```

---

### Task 8: 集成到开源检查 + 文档 + 样例目录

**Files:**
- Modify: `.gitignore`
- Modify: `scripts/open_source_check.py`
- Create: `data/sample/README.md`
- Create: `data/sample/manifest.yaml.example`
- Modify: `README.md`
- Modify: `docs/系统启动指南.md`

**Interfaces:**
- 无新函数；落地配置与文档。

- [ ] **Step 1: 在 `.gitignore` 显式守护 `data/sample/`**

在 `.gitignore` 的 "# Private raw data and local databases" 段末尾追加：

```
# 公共样本数据集：随仓库发布，必须不被忽略
!data/sample/
!data/sample/**
```

- [ ] **Step 2: 给 `scripts/open_source_check.py` 增加样本目录被禁标记检查**

在 `REQUIRED_GITIGNORE_RULES` 集合中确认含 `data/sample/` 相关白名单项不强制（它是发布目录，非忽略），但新增一条对 `data/sample/` 内容的被禁标记扫描。在 `main()` 的扫描循环后追加：

```python
    sample_dir = ROOT / "data" / "sample"
    if sample_dir.is_dir():
        import re as _re
        _banned = ["和风天气开发者服务", "weather_forecast_hourly", "weather_observation",
                   "现货市场101问", "/Users/", "/home/"]
        for f in sample_dir.rglob("*.json"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            for m in _banned:
                if m in text:
                    findings.append(f"data/sample 含被禁标记 {m}: {f.relative_to(ROOT)}（值未输出）")
```

- [ ] **Step 3: 写 `data/sample/README.md`**

```markdown
# 公共样本数据集

本目录随仓库发布，供下载者可选灌入，使新部署非空可演示。

## 来源与署名
- 政策：来自国家能源局/发改委/国务院公开页，保留 `source`/`source_url`。
- 数值行情/统计：来自公开统计/交易中心行情，保留 `provenance_level`/`source`。
- 题目：维护者原创，`source` 标注。

## 不收录
- 教材 PDF 及其派生（版权）。
- 和风天气数据（ToS 禁止再分发）。
- 真题（考试机构条款）。
- 用户/账号/做题数据（隐私）。

## 维护者流程
1. 编辑 `manifest.yaml`（按本库内容 ID 精选）。
2. `python backend/scripts/sample_data.py --export`。
3. **逐个打开 JSON 人工复核**（自动化检查是地板，不是天花板）。
4. `python backend/scripts/sample_data.py --check`。
5. `git add data/sample/ && git commit`。

## 下载者灌入
`python backend/scripts/sample_data.py --load`（幂等，可重复运行）。
```

- [ ] **Step 4: 写 `data/sample/manifest.yaml.example`**

```yaml
# 公共样本数据集清单 —— 维护者按本库内容 ID 精选
# 安全约束：未列出的一律不导出；教材/用户数据节不允许出现。
# 维护者流程见 data/sample/README.md。
policies:
  ids: []            # 例：[12, 15]
questions:
  ids: []            # 例：[3, 7] —— 仅自编题；真题会被硬排除
market_data:
  - data_type: carbon
    date_range: ["2026-07-01", "2026-07-31"]
    exclude_providers: [qweather]
  # - data_type: clearing
  #   date_range: ["2026-07-01", "2026-07-07"]
```

- [ ] **Step 5: 更新 `README.md`**

在「配置入口：只需填一个文件」之后、「教材与 PDF 解析依赖什么」之前，插入：

```markdown
### 样本数据集（可选）

仓库自带一份精选脱敏样本 `data/sample/`（政策 + 公开数值 + 自编题，不含教材/天气/真题）。下载者可选灌入，使系统非空可演示：

```bash
backend/.venv/bin/python backend/scripts/sample_data.py --load
```

维护者更新样本见 [`data/sample/README.md`](data/sample/README.md)。本项目不收录任何受版权或 ToS 约束的内容。
```

- [ ] **Step 6: 更新 `docs/系统启动指南.md`**

在「本地启动」末尾「停止服务」之前，追加：

```markdown
（可选）灌入样本数据集，使系统非空可演示：

```bash
backend/.venv/bin/python backend/scripts/sample_data.py --load
```
```

- [ ] **Step 7: 跑全部测试 + 开源泄密检查**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_sample_data.py -v`
Expected: PASS（全部）

Run: `cd /path/to/power-trade-lab && python3 scripts/open_source_check.py`
Expected: 通过（`data/sample/` 为空目录时尚未被禁标记检查命中；若已放产物则需 `--check` 通过）。

- [ ] **Step 8: 提交**

```bash
git add .gitignore scripts/open_source_check.py data/sample/ README.md docs/系统启动指南.md
git commit -m "feat(sample): 集成到开源检查 + 文档 + 样例目录"
```

---

## Self-Review（写计划后自检）

1. **Spec 覆盖**：
   - 范围 in（政策/数值/自编题）→ Task 4 export + manifest（Task 3）。✓
   - 范围 out（教材/和风/真题/用户/整库/路径）→ Task 1 硬排除 + Task 3 manifest 拒教材节 + Task 2 路径清洗。✓
   - 机制 manifest + export/load/check → Task 3/4/5/6/7。✓
   - 脱敏规则 → Task 2。✓
   - 安全原则（白名单/只读/存疑即拒/PII/人工复核/最小化）→ Task 4（白名单+只读）+ Task 2（存疑即拒）+ Task 6（PII）+ Task 8 文档（人工复核）。✓
   - v1 规模 → 由 manifest 决定，文档（Task 8）说明。✓
   - 测试 → 各任务内 TDD + Task 8 集成。✓
   - 文档更新 → Task 8。✓
   - 不在本期范围 → spec 第 9 节，不在计划内。✓

2. **占位符扫描**：无 TBD/TODO；每步含真实代码。✓

3. **类型/签名一致**：`is_qweather_public_data`、`is_excluded_question`、`sanitize_policy/question/public_data`、`load_manifest`、`export`、`load`、`check`、`main` 在各任务中名称一致；`export` 返回 `dict` 含 `policies/questions/market_data/skipped` 键，Task 5/7 一致使用。✓

4. **修正**：spec 原写"doc_chunks 中 book_id 命中排除"，实际 schema 无 `book_id` 且 doc_type 无 book；计划已简化为"v1 不导出 chunks/knowledge_docs"，更安全。此简化已体现在 File Structure 与 Task 4。
