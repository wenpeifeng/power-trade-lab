# 主动学习二期 实现计划（A 基础设施 + B 内容增厚 + C 打磨）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** 把知识库从被动只读升级为主动学习（自检+间隔复习+阅读进度+mastery+概念溯源），并增厚内容、通俗化、全局打磨。

**Architecture:** 后端加 answer_log/concept_reading 表 + mastery 计算 + 间隔复习字段；前端 KnowledgeBook 内嵌自检/进度/mastery，WrongBook 加今日复习+学概念，StudyHome 露 mastery；内容给概念加 example/pitfalls/faq/walkthrough + 补薄章节。

**Tech Stack:** Vue 3, FastAPI+SQLAlchemy, pytest, puppeteer(系统Chrome)。

## Global Constraints
- 非 git：每任务追加 `docs/superpowers/plans/CHANGELOG.md` 一行 `2026-08-10 <T>: <summary>`。
- 写作面向小白：通俗、生活类比、术语首现展开。
- 幂等 seeding（stem_hash/去重）。
- 复用 learnApi/studyApi/knowledgeApi、classifier、_question_to_out。
- 系统 Chrome 路径 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` 用于 puppeteer。

## Tasks
1. 后端基础设施：answer_log + concept_reading 表/模型 + mastery.py（_record_answer + recompute + GET /study/mastery）+ WrongAnswer 加 next_review_at/review_interval + GET /learn/check + GET /learn/wrong-answers/due + POST /study/reading + markReviewed 间隔翻倍/重置 + submit_answer/guided 调 _record_answer
2. KnowledgeBook 前端：内嵌自检区块 + ?kp= 过滤 + 阅读进度（read/understood 标记+章节进度条+树打勾）+ mastery 点
3. WrongBook 前端：今日复习 tab + 复习按钮 + 学概念链接
4. StudyHome 前端：mastery 条露出
5. 内容增厚 batch1：~16 个核心/用户点名概念加 example/pitfalls/faq/walkthrough + definition/keyPoints 通俗扩写
6. 内容增厚 batch2：补薄章节（ch7 容量/ch11 跨省/ch12 金融/ch13 监管 各+2-3 概念）+ 其余概念加 example 字段
7. 全局打磨 sweep：跑应用找死链/空状态/标签/交互粗糙处并修
8. 回归 test_active_learning.py + e2e puppeteer 闭环走查（自检答错→今日复习→mastery 更新→学概念）

详细步骤见各 SDD 派发 prompt；本计划为骨架。
