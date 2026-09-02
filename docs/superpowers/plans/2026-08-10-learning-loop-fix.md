# 学习闭环修复 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** 接通断裂的学习闭环——知识库概念可跳练题/原文/仿真；考试弱项带 kp；导学题+book 题入库扩充题池；文档回填 KP；嵌入诚实化；诊断分级用 difficulty；KP 前置网络；仿真结算回流。

**Architecture:** 前端出站链接 + 入参预填；后端用 `questions.source_type` 区分题来源（guided/book/core），新增 `KnowledgePointPrerequisite` join 表；seeding 脚本幂等（stem_hash 去重）。

**Tech Stack:** Vue 3 SFC, FastAPI+SQLAlchemy, pytest, sqlite3。

## Global Constraints
- 项目非 git：无 commit，每任务追加 `docs/superpowers/plans/CHANGELOG.md` 一行 `2026-08-10 TaskN: <summary>`。
- 前端无单测：`vite build` + 必要时 puppeteer 冒烟为验收。
- `questions` 表已有 `source/source_type/is_ai_generated/source_url/exam_level/difficulty/knowledge_point_id/stem_hash`，**入库不改 schema**。
- 写作面向小白（沿用 curriculum 已有风格）：手写题题面要通俗、analysis 要解释清楚。
- 幂等：所有 seeding 脚本按 `stem_hash` 去重，可重复跑。
- 复用现有 `classifier.auto_classify`、`knowledge_doc_order_by`、`learnApi`/`studyApi`/`knowledgeApi`。

## Tasks
1. curriculum.js 概念加 kp+scenario 字段（68 概念映射 8 KP + 仿真 key）
2. KnowledgeBook.vue 出站三按钮 + kpCodeToId 解析
3. Browse.vue 支持 ?kp= 入参预选/筛选
4. ExamResult 弱项带 kp + Quiz 读 ?kp= 预填锁定
5. 嵌入诚实化（UI 标签 + dense fallback 显式）
6. 诊断分级改用 difficulty 派生 tier
7. KP 前置网络（模型+表+seeding+knowledge_network 返回 prerequisites）
8. 导学题入库 + guided.py 改读 questions
9. book 章节题入库（先确认表名/quiz_json 结构）
10. 文档回填 KP（classifier.auto_classify 批量）
11. 手写核心题批次（每 KP ~10 题，通俗题面+解析）
12. 仿真结算回流入口（Terminal/SimulationLab 加链接到错题本/最近考试）
13. 闭环回归测试 test_learning_loop.py + 全量验收

（详细每任务步骤见 SDD 派发 prompt；本计划为骨架。）
