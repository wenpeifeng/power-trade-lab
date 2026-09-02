# 学习闭环修复 设计（P0-P4）

> 日期：2026-08-10
> 目标：把断裂的学习闭环接通——从「读概念→练题→看错题→补弱项→再学」走通，知识库不再是孤岛。
> 范围：基于全局 gap 分析的 P0-P4 全部修复。

## 已确认的 schema 事实（免返工）
- `questions` 表已有：`source`、`source_type`、`is_ai_generated`、`source_url`、`exam_level`、`difficulty`、`knowledge_point_id`、`stem_hash`。**P1b/c 入库无需改 schema**，用 `source_type='guided'/'book'` + `source` 标识来源。
- `questions` 表**无 `tier` 列**（P3b 诊断分级问题根因）；有 `difficulty`（1-5）与 `exam_level`（中/高级）可替代做分级。
- `knowledge_points`：8 个，code 为 `industry/wholesale/retail/mid_long_term/spot/ancillary/green/settlement`，有 `parent_id`/`level`。
- `curriculum.js` 概念 code（`111`/`321`…）与 KP code（`spot`…）是两套命名空间，需映射表。
- 现状：87 docs / 7 挂 KP / 20 questions / 8 KP / 5 wrong_answers / 1 book。

## 默认决定（可否决）
1. **嵌入模型**：不装 sentence-transformers（大下载、重依赖）。保留 TF-IDF 兜底，但把 UI「语义」标签改诚实（标"关键词增强"，并注明检索为词频匹配），代码结构留好真实 embedder 的注入位。→ P3a
2. **题量增长**：不手写数百题。靠 P1b（导学题入库）+ P1c（book 章节题入库）扩充题池，预期从 20 → 数百。→ P2b
3. **KP 前置网络**：新增轻量 join 表 `knowledge_point_prerequisites(kp_id, prereq_kp_id)`，不强行复用 `parent_id`（语义不同）。→ P3c

---

## P0 — 知识库概念接通学/练/原文/仿真（最高杠杆）

### P0.1 概念→KP 映射
- `curriculum.js` 每个概念加 `kp` 字段（knowledge_points.code，可空）+ `scenario` 字段（仿真场景 key，可空）。
- 68 概念逐个映射到 8 个 KP（多数概念能对上；少数通用概念 kp 留空）。
- 仿真场景对齐 `Terminal.vue` 的 marketMeta：`mid_long_term`/`day_ahead`/`realtime`/`green`/`freq`。

### P0.2 KnowledgeBook 出站按钮
- `KnowledgeBook.vue` 概念正文底部加三按钮（按字段有无显示）：
  - 「练本节」→ `router.push({path:'/learn/quiz', query:{kp:<kp_id>}})`（需 kp→id 解析，前端建 `kpCodeToId` map，启动时从 `learnApi.knowledgeTree()` 取 id）。
  - 「看真实原文」→ `router.push({path:'/knowledge', query:{tab:'feed', kp:<kp_code>}})`，`Browse.vue` 读 `?kp=` 预选分类/筛选。
  - 「去仿真」→ `router.push({path:'/trade', query:{market:<scenario>}})`（或 `/trade/lab?scenario=...`）。
- `Browse.vue` 支持 `?kp=<code>` 入参 → 选中对应分类并按 KP 筛文档（需 KP code→category code 映射，或直接按 `knowledge_point_id` 筛 docs）。

## P1 — 闭合三处断裂铰链

### P1a 考试弱项→针对性练（一行级）
- `ExamResult.vue:102 goStudyWeak()`：`router.push('/learn/quiz')` → `router.push({path:'/learn/quiz', query:{kp:w.knowledge_point_id}})`。
- `Quiz.vue` 读 `route.query.kp` 预填 KP 筛选并锁定。

### P1b 导学题入库 + 回流
- 把 `guided.py` 8 节的内联检查题物化为 `questions` 行（`source_type='guided'`、`source=<unit_code>`、`knowledge_point_id` 按 unit 对应 KP、`is_active=1`），写一个 seeding 脚本 `backend/scripts/seed_guided_questions.py` 幂等执行（按 `stem_hash` 去重）。
- `guided.py` 的检查改为从 `questions` 按 `source=<unit_code>` 查询渲染（保留原有题面，数据源换 DB）；作答写 `wrong_answers` + 更新 KP 掌握度，复用现有 `learnApi.answer` 路径或新增轻量 `study/guided/answer` 端点写 wrong_answers。

### P1c book 章节题入库
- 先确认 `learning_books_chapters` 真实表名与 `quiz_json` 结构。
- 写 `backend/scripts/seed_book_questions.py`：扫所有 book chapter 的 `quiz_json`，每题入 `questions`（`source_type='book'`、`source=<book_id:chapter_id>`、`knowledge_point_id` 按 chapter 标题分类用 `classifier.auto_classify` 推断或留空待标、`is_ai_generated=1`），幂等（`stem_hash` 去重）。
- BookReader 的章节检查仍读 `quiz_json`（不变），但题已同时在全局题池可见 → WrongBook/Quiz 可练。

## P2 — 数据深度

### P2a 文档回填 KP
- `backend/scripts/backfill_doc_kp.py`：对 `knowledge_point_id IS NULL` 的 docs 跑 `classifier.auto_classify(title+content)` 推断 KP，写回；打印覆盖前后对比。
- 目标：87 → ≤10 未挂。

### P2b 题量
- 由 P1b/P1c 自然扩充，不另手写。验收：题池从 20 → ≥100。

## P3 — 检索与路由质量

### P3a 嵌入诚实化
- `Browse.vue` mode-tab：`语义` → `关键词增强`，加 `<small>` 注"当前为词频检索"。
- `embedding.py`：保留 TF-IDF 兜底，把 `retrieve(mode='dense')` 在无真实 embedder 时显式 fallback 到 sparse 并记日志（已是事实，确保 UI 与后端一致）。
- 留 `EMBEDDING_PROVIDER` 配置位（settings），未来注入 sentence-transformer/API 时不改调用方。

### P3b 诊断分级修
- 查 `diagnosis.py` 实际用什么字段做 3 档（基础/进阶/高阶）。改用 `difficulty`（1-2 基础/3-4 进阶/5 高阶）抽样；`Diagnosis.vue` 的 `currentQ.tier` 改读后端返回的 `tier`（后端按 difficulty 派生返回），不依赖 `questions.tier`。
- 验收：Diagnosis 8 题能稳定抽到三档。

### P3c KP 前置网络
- 新表 `knowledge_point_prerequisites(id, kp_id, prereq_kp_id, created_at)`，建 migration/`create_all`。
- seeding：8 个 KP 的前置关系（如 spot 的前置是 mid_long_term；ancillary 前置 spot；settlement 前置 mid_long_term+spot）。
- `knowledge_network` 端点扩展返回 `prerequisites: [KP]`；前端知识网络/弱项页可"补前置"跳转。

## P4 — 仿真→学习回流
- `Terminal.vue` / `SimulationLab.vue` 结算复盘区加「回到薄弱点」入口：调 `learnApi.wrongAnswersPaged` 或 exam 结果，链回 `/learn/wrong` 或 `/learn/exam/result/:last`。
- 最小实现：结算页加一个静态链接到错题本 + 最近考试结果（不做了的弱项归因先不建，留 P4.2）。

## 文件清单（预期）

新增：
- `backend/scripts/seed_guided_questions.py`
- `backend/scripts/seed_book_questions.py`
- `backend/scripts/backfill_doc_kp.py`
- `backend/app/knowledge/prereqs.py`（KP 前置数据 + 查询）
- `backend/tests/test_learning_loop.py`（闭环回归）

修改：
- `frontend/src/knowledge/curriculum.js`（每个概念加 kp/scenario）
- `frontend/src/views/knowledge/KnowledgeBook.vue`（出站按钮 + kpCodeToId）
- `frontend/src/views/knowledge/Browse.vue`（?kp= 入参）
- `frontend/src/views/learn/ExamResult.vue`（goStudyWeak 带 kp）
- `frontend/src/views/learn/Quiz.vue`（读 ?kp= 预填锁定）
- `backend/app/study/guided.py`（检查题改读 questions）
- `backend/app/study/diagnosis.py`（tier 改用 difficulty 派生）
- `backend/app/knowledge/router.py`（knowledge_network 返回 prerequisites）
- `backend/app/knowledge/embedding.py`（dense fallback 显式 + 配置位）
- `backend/app/db/models.py`（新增 KnowledgePointPrerequisite 模型）
- `frontend/src/views/trade/Terminal.vue` 或 `SimulationLab.vue`（结算回流入口）

## 不在本次范围
- 不装 sentence-transformers / 不接外部 embedding API（P3a 仅诚实化 + 留注入位）。
- 不手写大量新题（靠入库扩充）。
- 不做仿真弱项自动归因（P4 仅加回流入口）。
- 不补爬取内容空分类（数据运营，另做）。

## 验收
- 闭环可走通：读概念 321 双边协商 → 点「练本节」→ Quiz 仅出中长期题 → 答错 → WrongBook 出现 → 关联文档可看 → 回 KnowledgeBook 补前置。
- 考试结果弱项 → 针对性 Quiz 带 kp。
- 题池 ≥100；文档挂 KP ≥90%。
- Diagnosis 三档稳定；KP 前置可查；结算页有回流入口。
- 全量 pytest + vite build 绿。
