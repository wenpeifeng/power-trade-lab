# 学习闭环二期完善设计（N1-N5）

> 日期：2026-08-10
> 目标：把课程从被动变主动（自检）、补齐缺失的间隔复习闭环、记阅读进度、修 mastery 计算（解锁 L1-L3 路径）、错题可溯到概念。

## 关键发现（免返工）
- `user_profiles.mastery`（JSON `{kp_code: pct}`）**只读不写**：`content.py:44` 读它做 L1→L2→L3 解锁判断（`mastery.get(kp)>=60`），但代码库无任何地方写入它 → 永远 `{}` → 学习路径永久锁死。N5 必须先实现计算。
- `WrongAnswer` 现有字段：user_id/question_id/user_answer/is_correct/reviewed/...（无 next_review_at）。需加间隔复习字段。
- `learnApi.quiz` 按 KP 出题已可用（N1 复用）。
- `learnApi.wrongAnswersPaged`/`markReviewed` 已有（N2 在其上加 due）。
- curriculum 概念已有 `kp` 字段（一期 L1）。

## 默认决定（可否决）
1. **N1 自检答题也写 wrong_answers**：错答进错题本（喂 N2 间隔复习），复用 `submit_answer` 去重路径。低门槛但有闭环价值。
2. **N5 mastery 计算**：新增 `answer_log` 表记每次答题（user_id/kp_id/is_correct/answered_at），`mastery[kp] = correct/total*100`，每次 submit_answer 后增量更新 `UserProfile.mastery`。不追溯历史（旧错题无 answer_log，从现在开始记）。
3. **N3 错题→概念**：不做逐题 concept_code 标注（391 题回标太重）。改最小路径：错题行加「学概念」链 → `/knowledge?kp=<code>`，KnowledgeBook 支持 `?kp=` 过滤章节树只显该 KP 概念 + 自动选首个。
4. **N4 阅读进度**：新表 `concept_reading(user_id, concept_code, status, read_at, updated_at)`，unique(user_id,concept_code)。KnowledgeBook 进概念页 debounce POST mark-read；「我懂了」按钮 mark-understood；章节进度条=已读/总数。

## N1 — 概念页内嵌自检
- 后端：新增 `GET /learn/check?kp=<id>&count=1` 返回 1 道随机题（hide_answer）。复用 `_question_to_out`。
- 前端 KnowledgeBook：概念正文末（动作按钮上方）加「自检：本节掌握了吗？」区块，onMounted 按 `cur.kp` 拉 1 题；渲染题干+选项；提交调 `learnApi.submitAnswer`（写 wrong_answers + answer_log，触发 N5）；显示对错+解析；「换一道」「去完整刷题」。
- kp 为 null 的概念不显示自检。

## N2 — 间隔复习
- 后端：`WrongAnswer` 加 `next_review_at`(DateTime, nullable)、`review_interval`(int days, default 1)。
- 提交答案错→设 next_review_at=now+interval（首次 1 天）；markReviewed 正确→interval 翻倍（1→2→4→7→14→30 封顶），next=now+new_interval；markReviewed 错误→interval 重置 1，next=now+1d。
- 新端点 `GET /learn/wrong-answers/due` 返回 next_review_at<=now 的错题（分页）。
- 前端 WrongBook：加「今日复习」筛选 tab（due）；每条加「复习」按钮重做题（复用 quiz 题面或跳 quiz?kp）；复习后调 markReviewed 带 correctness。
- README 承诺的"间隔复习"补齐。

## N3 — 错题→概念链接
- 前端 WrongBook 错题行加「学概念」按钮 → `/knowledge?kp=<kp_code>`（需 kp id→code，已有 knowledgeTree）。
- 前端 KnowledgeBook 支持 `?kp=<code>`：过滤章节树只显 `concept.kp===code` 的概念（保留所属章标题），自动 select 第一个。

## N4 — 阅读进度
- 新表 `concept_reading`（上述）。
- 后端 `POST /study/reading/{concept_code}` body `{status:'read'|'understood'}`；`GET /study/reading` 返回该用户全部 {code, status}。
- 前端 KnowledgeBook：进概念 debounce(500ms) POST read；「我懂了」按钮 POST understood；章节进度条；概念树已读打勾。

## N5 — mastery 计算与露出
- 新表 `answer_log(id, user_id, question_id, kp_id, is_correct, answered_at)`。
- `submit_answer`（learn）+ 导学题答（study）+ 自检答（N1）统一调 `_record_answer(db, user_id, question_id, is_correct)` 写 answer_log + 增量更新 `UserProfile.mastery[kp]`。
- 新端点 `GET /study/mastery` 返回每 KP 的 mastery pct + 题数 + 已掌握题数。
- 前端 StudyHome：KP 网格/仪表盘显示 mastery 条；解锁 L1→L2→L3（content.py L79 现在能达标）。
- KnowledgeBook 章节树每概念小 mastery 点（按 kp 聚合到概念）。

## 文件清单（预期）
新增脚本/表/模型：
- `answer_log` 表 + `concept_reading` 表（models.py + create_all）
- `backend/app/study/mastery.py`（计算 + record_answer）
- `backend/tests/test_active_learning.py`

修改后端：
- `app/learn/router.py`（check 端点、due 端点、submit_answer 调 record_answer、wrong-answers markReviewed 带间隔逻辑）
- `app/study/router.py`（reading 端点、mastery 端点、guided 答题调 record_answer）
- `app/study/content.py`（mastery 已读，无需改）
- `app/db/models.py`（WrongAnswer 加 next_review_at/interval；新 2 表）

修改前端：
- `views/knowledge/KnowledgeBook.vue`（自检区块、?kp= 过滤、阅读进度标记、mastery 点）
- `views/learn/WrongBook.vue`（今日复习 tab、复习按钮、学概念按钮）
- `views/learn/StudyHome.vue`（mastery 条露出）

## 不在本次范围
- 不回标 391 题的 concept_code（N3 走 KP 级链接）。
- 不追溯历史 answer_log（从现在起记）。
- 不做新题（题池已 391）。

## 验收
- 概念页自检可答、错答进错题本+answer_log、mastery 更新。
- WrongBook「今日复习」列出 due 错题；复习正确间隔翻倍。
- 错题「学概念」跳 KnowledgeBook 过滤到该 KP 概念。
- 概念读后标记、章节进度条、树打勾。
- StudyHome 显示 mastery 条；L1→L2 在 mastery≥60 时解锁（content.py L79 生效）。
- pytest + vite build 绿。
