"""飞书交易知识库 → 批量导入脚本。

递归遍历「交易知识库」的 3 个顶层菜单，DFS 收集所有文档，
读取 markdown 正文，清洗后自动分类录入 KnowledgeDoc + 向量化。

用法：
    cd backend && source venv/bin/activate
    python scripts/import_feishu_wiki.py          # 全量导入
    python scripts/import_feishu_wiki.py --dry     # 只扫描不导入，看清单
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

# 确保能 import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SPACE_ID = "7564653266303385619"
# 3 个顶层菜单（第三个是旧版过渡期，可选导入）
TOP_NODES = [
    {"node": "JQaFwl9Qfic3oRkkjNscMzUfnyc", "title": "全国（区域）政策、规则、信息", "scope": "national"},
    {"node": "MsR4wmBfPiAy7rkzfj9cqnbvnnc", "title": "省级（市场）政策、规则、信息", "scope": "province"},
    # {"node": "KcAHw4FSvio9jokIRqRcSbzPnyh", "title": "旧版政策文件页面", "scope": "legacy"},
]


def lark_json(cmd: list[str]) -> dict:
    """执行 lark-cli 命令，返回 JSON dict。"""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        return {"error": result.stderr[:200]}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": f"非JSON: {result.stdout[:200]}"}


def list_children(space_id: str, parent_node: str = "") -> list[dict]:
    """列出子节点。parent_node 为空时列顶层。"""
    params = {"space_id": space_id}
    if parent_node:
        params["parent_node_token"] = parent_node
    data = lark_json([
        "lark-cli", "wiki", "nodes", "list",
        "--params", json.dumps(params), "--as", "user",
    ])
    return data.get("data", {}).get("items", [])


def fetch_doc_content(obj_token: str) -> str:
    """读取文档 markdown 正文。"""
    data = lark_json([
        "lark-cli", "docs", "+fetch",
        "--doc", obj_token, "--doc-format", "markdown", "--as", "user",
    ])
    return data.get("data", {}).get("document", {}).get("content", "")


def clean_markdown(md: str) -> str:
    """清洗 markdown：去掉 source 标签、多余空行。"""
    # 去掉 <source .../> 附件标签（保留文字部分已够用）
    md = re.sub(r'<source[^/]*/>', '[附件]', md)
    # 去掉 HTML 标签残留
    md = re.sub(r'</?[^>]+>', '', md)
    # 压缩连续空行
    md = re.sub(r'\n{3,}', '\n\n', md)
    return md.strip()


def dfs_collect(space_id: str, parent_node: str, path: list[str]) -> list[dict]:
    """DFS 递归收集所有文档节点。"""
    items = list_children(space_id, parent_node)
    docs = []
    for it in items:
        title = it.get("title", "").strip()
        obj_token = it.get("obj_token", "")
        obj_type = it.get("obj_type", "")
        node_token = it.get("node_token", "")
        has_child = it.get("has_child", False)
        current_path = path + [title]

        # 只处理 docx 类型（文档），跳过 sheet/bitable 等
        if obj_type == "docx" and obj_token:
            docs.append({
                "title": title,
                "obj_token": obj_token,
                "node_token": node_token,
                "path": current_path,
                "has_child": has_child,
            })
        # 递归子节点（无论当前节点是不是 docx，都看有没有子节点）
        if has_child:
            docs.extend(dfs_collect(space_id, node_token, current_path))
    return docs


def main():
    dry = "--dry" in sys.argv

    print("=" * 60)
    print("飞书交易知识库 → 批量导入")
    print("=" * 60)

    # ① 收集所有文档
    all_docs = []
    for top in TOP_NODES:
        print(f"\n📂 扫描菜单: {top['title']}")
        # 顶层节点本身也是文档，先加自己
        content_preview = ""
        try:
            raw = fetch_doc_content(top["node"])
            content_preview = f"{len(raw)}字" if raw else "空"
        except Exception:
            content_preview = "读取失败"
        print(f"   顶层文档: {content_preview}")

        docs = dfs_collect(SPACE_ID, top["node"], [top["title"]])
        # 给每个文档标注 scope
        for d in docs:
            d["scope"] = top["scope"]
        all_docs.extend(docs)
        print(f"   递归发现 {len(docs)} 个子文档")

    print(f"\n共收集 {len(all_docs)} 个文档")

    if dry:
        print("\n--- 文档清单（dry run，不导入）---")
        for i, d in enumerate(all_docs, 1):
            print(f"  {i:3}. [{'→'.join(d['path'][-2:])}] {d['title'][:50]}")
        return

    # ② 逐个导入
    from app.db.database import SessionLocal, init_db
    from app.db.models import KnowledgeDoc
    from app.knowledge.classifier import auto_classify
    from app.knowledge.embedding import vectorize_document
    import hashlib

    init_db()
    db = SessionLocal()

    imported, skipped, failed = 0, 0, 0
    for i, d in enumerate(all_docs, 1):
        title = d["title"] or f"飞书文档_{d['obj_token'][:8]}"
        path_str = " / ".join(d["path"])
        print(f"\n[{i}/{len(all_docs)}] {title[:40]}")
        print(f"  路径: {path_str}")

        # 去重
        dedup = hashlib.md5(f"feishu|{d['obj_token']}".encode()).hexdigest()[:16]
        if db.query(KnowledgeDoc).filter(KnowledgeDoc.dedup_key == dedup).first():
            print(f"  ⏭ 已存在，跳过")
            skipped += 1
            continue

        # 读取内容
        try:
            raw_md = fetch_doc_content(d["obj_token"])
        except Exception as e:
            print(f"  ✗ 读取失败: {e}")
            failed += 1
            continue
        if not raw_md or len(raw_md) < 20:
            print(f"  ⏭ 内容过短({len(raw_md)}字)，跳过")
            skipped += 1
            continue

        content = clean_markdown(raw_md)
        print(f"  内容: {len(content)}字")

        # 自动分类
        classify = auto_classify(title, content[:500])
        doc_type = _infer_doc_type(title, content, d["scope"])
        print(f"  分类: type={doc_type} cat={classify.get('category_code')}")

        # 录入
        doc = KnowledgeDoc(
            title=title,
            doc_type=doc_type,
            category_code=classify.get("category_code"),
            facet_tags=json.dumps(classify.get("facet_tags", {}), ensure_ascii=False),
            source="飞书交易知识库",
            source_url=f"https://lumin-ai.feishu.cn/wiki/{d['node_token']}",
            content=content,
            ingest_type="feishu",
            source_meta=json.dumps({"wiki_path": d["path"], "obj_token": d["obj_token"]}, ensure_ascii=False),
            dedup_key=dedup,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        # 向量化
        try:
            r = vectorize_document(db, doc.id)
            print(f"  ✅ 入库 id={doc.id} 向量化={r.get('chunks',0)}块")
        except Exception as e:
            print(f"  ✅ 入库 id={doc.id} 但向量化失败: {e}")
        imported += 1

        # 限速，避免飞书 API 压力
        time.sleep(0.3)

    db.close()

    print("\n" + "=" * 60)
    print(f"导入完成: 新增 {imported} 篇, 跳过 {skipped} 篇, 失败 {failed} 篇")
    print("=" * 60)


def _infer_doc_type(title: str, content: str, scope: str) -> str:
    """推断文档类型。"""
    text = title + content[:500]
    if scope == "province":
        if any(k in text for k in ["交易中心", "出清", "成交", "申报", "公告", "月度", "日前"]):
            return "exchange_info"
        return "regulation"
    if scope == "national":
        if any(k in text for k in ["发改委", "能源局", "国务院", "国办发", "顶层设计", "规划"]):
            return "national_policy"
        if any(k in text for k in ["监管局", "监管"]):
            return "regulation"
        return "national_policy"
    return "industry_news"


if __name__ == "__main__":
    main()
