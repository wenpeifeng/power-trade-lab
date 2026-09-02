# 电力知识库 Tab 切换 + 系统化教学内容 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复「数据资产」按钮失效、给知识库页加 Tab（系统化知识 vs 爬取资讯）、撰写面向小白的 13 章电力市场知识体系。

**Architecture:** 后端拆 `/asset` router 级 admin guard → 端点级（读放开、写留 admin）；前端 `/knowledge` 加 Tab，新组件 `KnowledgeBook.vue` 渲染静态结构化课程 `curriculum.js`，与现有爬取浏览 `Browse.vue` 物理隔离；markdown 解析抽到共用 `utils/markdown.js`。

**Tech Stack:** Vue 3（Composition API, `<script setup>`，无 TS）、Vue Router 4、Element Plus、lucide-vue-next、Vite 8；后端 FastAPI + SQLAlchemy，pytest。

## Global Constraints

- 项目**非 git 仓库**：本计划里所有 `git commit` 步骤改为"保存文件并记录到 `docs/superpowers/plans/CHANGELOG.md`"（追加一行 `YYYY-MM-DD TaskN: 摘要`）。仍可用 `git` 仅当用户先初始化仓库。
- 前端无单测框架（package.json 无 vitest/jest）：前端任务以"启动 dev server 人工/浏览器验证"为验收，不写单测。
- 写作原则（面向小白，硬性，见 spec §2.1）：每个概念 `tldr`/`analogy` 零术语、带生活类比；首现术语先大白话再术语；缩写必展开；每章 3 句白话导语 `intro`；每个概念有 `prereq`。
- 不动 `Browse.vue`、不动爬虫、不动 `knowledge_docs` 数据。
- 复用现有 UI 变量与风格（`var(--accent)` 等），与知识库页现有雷达/卡片视觉一致。

## File Structure

新增：
- `frontend/src/utils/markdown.js` — 共用轻量 markdown 解析（`parseMarkdown`、`inlineHtml`、`escapeHtml`），单一职责工具。
- `frontend/src/knowledge/curriculum.js` — 课程数据：`CURRICULUM`（13 章→节→概念）+ `LEARNING_PATH`（推荐阅读顺序）。纯数据，无逻辑。
- `frontend/src/views/knowledge/KnowledgeBook.vue` — 教材式阅读组件（左栏章节树 + 右栏正文 + 学习路线卡）。

修改：
- `backend/app/knowledge/admin_router.py` — router 级 guard 拆到端点级。
- `frontend/src/router/index.js` — `/asset` 去 `requiresAdmin`。
- `frontend/src/views/knowledge/Layout.vue` — 顶部加 Tab，按 `?tab=` 切换渲染 `KnowledgeBook` / `Browse`。
- `frontend/src/views/learn/BookReader.vue` — 改用 `utils/markdown.js`，删除本地 `parseMarkdown`/`inlineHtml` 副本。

---

## Task 1: 后端拆 `/asset` admin guard（读放开、写留 admin）

**Files:**
- Modify: `backend/app/knowledge/admin_router.py`
- Test: `backend/tests/test_asset_guard.py`（新建）

**Interfaces:**
- Consumes: `app.common.auth.get_current_user`（已存在）、`app.common.auth.require_admin`（已存在）
- Produces: `/asset/*` 读端点接受任意登录用户；写/审核端点仍要求 admin。

**当前端点清单与处置**（核对自 admin_router.py 实际行号）：
- 读端点 → 改 `current_user=Depends(get_current_user)`：
  - `GET /asset/crawler/status` (L399)
  - `GET /asset/connectors/qweather/status` (L409)
  - `GET /asset/connectors/qweather/locations` (L440)
  - `GET /asset/timeline` (L454)
  - `GET /asset/stats` (L565)
  - `GET /asset/quality` (L598)
  - `GET /asset/refs/{doc_id}` (L705)
- 写/审核端点 → 已有或补 `current_user=Depends(require_admin)`：
  - `POST /asset/ingest/*`（L81/103/134/156/200/249/275/304，**已都有**）
  - `POST /asset/crawler/run` (L355) — **补**
  - `POST /asset/connectors/qweather/test` (L430) — **补**
  - `POST /asset/track-ref` (L689) — **补**
  - `POST /asset/review` (L736) — **补**
  - `POST /asset/review/batch` (L752) — **补**
  - `POST /asset/doc/update` (L774) — **补**
  - `GET /asset/review/pending` (L794) — 审核队列，**补 `require_admin`**（读但属审核工作）

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_asset_guard.py`：

```python
"""数据资产中心权限边界：读放开给登录用户，写/审核保留 admin。"""
import pytest

BASE = "/asset"


def test_stats_requires_login(client, db_session):
    r = client.get(f"{BASE}/stats")
    assert r.status_code in (401, 403)


def test_stats_ok_for_normal_user(auth_client_normal):
    r = auth_client_normal.get(f"{BASE}/stats")
    assert r.status_code == 200


def test_timeline_ok_for_normal_user(auth_client_normal):
    r = auth_client_normal.get(f"{BASE}/timeline")
    assert r.status_code == 200


def test_review_forbidden_for_normal_user(auth_client_normal):
    r = auth_client_normal.post(f"{BASE}/review", json={"doc_id": 1, "action": "approve"})
    assert r.status_code == 403


def test_crawler_run_forbidden_for_normal_user(auth_client_normal):
    r = auth_client_normal.post(f"{BASE}/crawler/run", json={"kind": "policy"})
    assert r.status_code == 403


def test_review_ok_for_admin(auth_client_admin):
    r = auth_client_admin.post(f"{BASE}/review", json={"doc_id": 1, "action": "approve"})
    assert r.status_code in (200, 400, 404)  # 非 403 即通过权限
```

> 说明：fixtures `client`/`auth_client_normal`/`auth_client_admin` 若 tests/ 已有则复用；若无，参考已有 `backend/tests/conftest.py` 风格补 3 个 fixture（普通用户 client 带 Cookie、admin client 带 Cookie、未登录 client）。先 `grep -n "def client\|def auth\|fixture" backend/tests/conftest.py` 确认。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_asset_guard.py -v`
Expected: FAIL（读端点对普通用户 403，因为 router 级 guard 仍闸着）。

- [ ] **Step 3: 拆 guard**

编辑 `backend/app/knowledge/admin_router.py`：

(a) 顶部 import 增加 `get_current_user`：

```python
from app.common.auth import get_current_user, require_admin
```

(b) 移除 router 级依赖（L35-39）：

```python
router = APIRouter(
    prefix="/asset",
    tags=["数据资产中心"],
)
```

(c) 给上述"补"清单里每个端点的函数签名加 `current_user=Depends(require_admin)`。例：

```python
@router.post("/crawler/run", summary="按类型触发爬虫(异步)")
def crawler_run(kind: str, current_user=Depends(require_admin), db: Session = Depends(get_db)):
    ...
```

(d) 给每个读端点的函数签名加 `current_user=Depends(get_current_user)`（参数名 `_user` 也可，只要触发鉴权）。例：

```python
@router.get("/stats", summary="数据资产总览统计")
def asset_stats(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    ...
```

> 实操：逐个端点打开看签名，按 (c)/(d) 处置，务必 7 个读端点全部加 `get_current_user`、7 个写端点（crawler/run、qweather/test、track-ref、review、review/batch、doc/update、review/pending）全部加 `require_admin`。ingest 系列 8 个已有，不动。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_asset_guard.py -v`
Expected: PASS。

- [ ] **Step 5: 跑全量回归**

Run: `cd backend && python -m pytest -q`
Expected: 无新增失败（已有失败若与本改动无关则记录，不阻断）。

- [ ] **Step 6: 记录**

追加到 `docs/superpowers/plans/CHANGELOG.md`：`2026-08-07 Task1: 拆 /asset admin guard，读放开登录用户、写留 admin`

---

## Task 2: 前端 `/asset` 路由去 admin 限制

**Files:**
- Modify: `frontend/src/router/index.js:67`

**Interfaces:**
- Produces: 任意登录用户可进入 `/asset`（写权限仍由后端 Task1 保证）。

- [ ] **Step 1: 改路由 meta**

`frontend/src/router/index.js` 第 64-68 行，删 `requiresAdmin: true`：

```js
{
  path: '/asset',
  name: 'asset-center',
  component: () => import('../views/admin/AssetCenter.vue'),
  meta: { theme: 'asset', title: '数据资产中心' },
},
```

- [ ] **Step 2: 启动前后端验证**

Run backend: `cd backend && bash ../start.sh` 或按 `docs/系统启动指南.md` 起服务。
Run frontend: `cd frontend && npm run dev`

用**非 admin 账号**登录 → 首页点「数据资产」→ 预期：进入 `/asset` 页面、统计与时间线正常加载（不再静默跳回首页）。点 ingest/curl 提交 → 预期：后端返回 403（前端原有错误提示即可）。

- [ ] **Step 3: 记录**

追加 `CHANGELOG.md`：`2026-08-07 Task2: /asset 前端路由去 requiresAdmin`

---

## Task 3: 抽取共用 markdown 工具

**Files:**
- Create: `frontend/src/utils/markdown.js`
- Modify: `frontend/src/views/learn/BookReader.vue`（L303、L407、L412 附近）

**Interfaces:**
- Produces: `parseMarkdown(md: string) -> Block[]`、`inlineHtml(text: string) -> string`、`escapeHtml(text: string) -> string`，行为与 BookReader 内原实现完全一致。

- [ ] **Step 1: 读原实现**

Run: `grep -n "function parseMarkdown\|const inlineHtml\|function escapeHtml\|escapeHtml" frontend/src/views/learn/BookReader.vue`
记录 `parseMarkdown`、`inlineHtml`、`escapeHtml` 的完整函数体（约 L407-460）。

- [ ] **Step 2: 新建 `frontend/src/utils/markdown.js`**

把三个函数原样搬入并 `export`：

```js
// 轻量 markdown 解析：仅支持 h1-h3 / blockquote / ul-list / 段落。
// 与 BookReader 原内联实现完全等价，零依赖。
export function escapeHtml(text) {
  /* 原 BookReader 实现 */
}

export function inlineHtml(text) {
  /* 原 BookReader 实现（含 escapeHtml 调用） */
}

export function parseMarkdown(markdown) {
  /* 原 BookReader 实现，返回 Block[] */
}
```

- [ ] **Step 3: 改 BookReader 引用**

`frontend/src/views/learn/BookReader.vue` `<script setup>` 顶部加：

```js
import { parseMarkdown, inlineHtml } from '../../utils/markdown'
```

删除文件内本地 `parseMarkdown`、`inlineHtml`、`escapeHtml` 定义。确认模板里 `markdownBlocks`（L303）仍调用 `parseMarkdown(...)`、模板里 `inlineHtml(...)` 调用不变。

- [ ] **Step 4: 验证 BookReader 不回归**

Run: `cd frontend && npm run dev`，进入学习中心 → 任一本书 → 任一章。
Expected：标题/列表/引用/段落渲染与改造前一致。

- [ ] **Step 5: 记录**

`CHANGELOG.md`：`2026-08-07 Task3: 抽 markdown 工具到 utils/markdown.js`

---

## Task 4: 课程数据骨架 + 学习路线 + 第 1-2 章

**Files:**
- Create: `frontend/src/knowledge/curriculum.js`

**Interfaces:**
- Produces: `CURRICULUM: Chapter[]`、`LEARNING_PATH: string[]`（概念 code 推荐阅读顺序）。Chapter/Section/Concept 结构见 spec §3.4。

**数据结构（curriculum.js 顶部注释固化）：**

```js
// Chapter: { code, title, intro, sections: Section[] }
// Section: { code, title, concepts: Concept[] }
// Concept: {
//   code, title, prereq: string[],       // 前置概念/章 code
//   tldr,                                 // 一句话懂了（零术语）
//   analogy,                              // 生活类比
//   definition,                           // 大白话→术语
//   keyPoints: string[],
//   compare?: [{ dim, a, b }],            // 对比/易混
//   link2sim,                             // 对应交易终端的什么
//   related: string[],                    // 概念 code 交叉引用
// }
export const CURRICULUM = [...]
export const LEARNING_PATH = ['1','21','311','312','313','411','412', ...]
```

- [ ] **Step 1: 写骨架与第 1 章**

新建 `frontend/src/knowledge/curriculum.js`，导出 `CURRICULUM` 数组，先写第 1 章「电力市场全景」，节与概念：

- 1-1 电力市场全景 → 概念：11 为什么要有电力市场（prereq:[]，tldr:"电以前是国家定价、统购统销，现在让买卖双方自己谈，就像从计划经济走到菜市场"）、12 中国电改历程（5号文/9号文，大白话："两次大改革文件，9号文是这次市场化的起点"）、13 电力商品的物理特性（实时平衡/难存储/网络约束，类比："电不能像苹果囤仓库，发多少必须同时用多少"）、14 市场体系层次（中长期→现货→辅助服务→容量→绿电，类比："批发→当日零售→急救队→容量保险→绿色标牌"）、15 参与者总览（指向第 2 章）

每个概念填齐 `tldr/analogy/definition/keyPoints/link2sim/related`，`prereq` 按依赖填。

- [ ] **Step 2: 写第 2 章「市场主体」**

节：21 发电企业（火/水/核/风/光/生物质，类比"不同种类的电工厂"）、22 电网企业（输配调三分离，类比"快递公司只管送、不管造"）、23 售电公司（类比"电的中间商/团购团长"）、24 电力用户（大用户 vs 一般用户）、25 新型经营主体（储能/虚拟电厂/负荷聚合商/微电网，类比"新型玩家"）、26 运营机构（交易中心=撮合市场、调度中心=交警、监管=裁判）。每节 1-3 个概念，填齐字段。

- [ ] **Step 3: 写 LEARNING_PATH**

按 spec §3.4 给推荐顺序：`['1','21','311','312','313','411','412','511','611','811']` 等，覆盖核心主线。

- [ ] **Step 4: 验证数据可加载**

Run: `cd frontend && node -e "import('./src/knowledge/curriculum.js').then(m=>console.log('chapters:',m.CURRICULUM.length,'path:',m.LEARNING_PATH.length))"`
Expected: `chapters: 2 path: 10`（至少 2 章已写、路径非空）。

- [ ] **Step 5: 记录**

`CHANGELOG.md`：`2026-08-07 Task4: curriculum.js 骨架 + LEARNING_PATH + 第1-2章`

---

## Task 5: 第 3 章 中长期交易 + 第 4 章 现货市场

**Files:**
- Modify: `frontend/src/knowledge/curriculum.js`（追加第 3、4 章）

**Interfaces:**
- Consumes: `CURRICULUM`（Task4 已建）。本章概念 `related` 引用第 1-2 章 code。

- [ ] **Step 1: 第 3 章「中长期交易」（用户点名核心）**

节与概念：
- 31 总览：311 中长期交易总览（prereq:['1','14']，tldr:"中长期 = 批发，提前好几个月甚至一年就把大部分电量和价格谈好，是市场压舱石"，analogy:"超市提前签好一年的进货合同"）、312 与现货的关系（曲线分解，类比"批发合同里写好每天送多少"）
- 32 交易方式：321 双边协商（prereq:['311']，tldr:"买卖双方一对一谈量价期"，analogy:"菜市场两家当面议价"）、322 集中竞价（tldr:"大家集中报买价卖价，系统撮合出清"，analogy:"拍卖/股票集合竞价"）、323 挂牌交易（tldr:"一方挂出卖单/买单，对方点接受成交"，analogy:"二手房挂牌"）
- 33 周期与合同：331 年度/月度/月内/周（类比"按交货期分的批发档"）、332 合同与发电权转让（tldr:"已签的合同可以转给别人"，analogy:"把批发合同转让给隔壁店"）
- 34 价格形成：341 协商价/出清价/政府指导价

每个概念必填 `compare`（321/322/323 三者对比表尤其重要：dim 用"像什么/谁定价格/什么时候谈/灵活性"）。

- [ ] **Step 2: 第 4 章「现货市场」**

节与概念：
- 41 总览：411 现货市场总览（prereq:['1','311']，tldr:"现货 = 当天的零售电，今天用多少当天买卖，价随供需跳"，analogy:"当日菜价，下雨天就贵"）、412 为什么要有现货（中长期覆盖不到的余缺靠它补）
- 42 时序：421 日前市场（tldr:"提前一天报第二天每小时的电"，analogy:"提前一天订明天的菜"）、422 实时/平衡市场（tldr:"实时补差额"，analogy:"当天临时加菜")
- 43 出清与电价：431 集中竞价出清（tldr:"报价从低到高排，贵的不要，到刚好够用为止的那口价就是成交价"，analogy:"拍卖里最后一个成交价"）、432 节点边际电价 LMP（tldr:"不同地点这一刻电价不同，堵的地方贵"，analogy:"市中心 vs 郊区的菜价"）、433 统一出清
- 44 与中长期衔接：441 中长期+现货双轨

每个概念填齐字段；411/421/422/431/432 都给 `compare` 或 `analogy`。

- [ ] **Step 3: 验证**

Run: `cd frontend && node -e "import('./src/knowledge/curriculum.js').then(m=>console.log(m.CURRICULUM.length))"`
Expected: `4`

- [ ] **Step 4: 记录**

`CHANGELOG.md`：`2026-08-07 Task5: 第3章中长期 + 第4章现货`

---

## Task 6: 第 5 章 辅助服务 + 第 6 章 绿色权益与碳

**Files:**
- Modify: `frontend/src/knowledge/curriculum.js`

- [ ] **Step 1: 第 5 章「辅助服务」**

节：51 总览（tldr:"辅助服务 = 电网的急救队，专门兜底保电网不垮"，analogy:"消防员/急救车"）、52 一次调频（tldr:"频率一抖机组自动秒调"，类比"踩油门稳速"）、53 AGC二次调频（自动发电控制）、54 调峰（tldr:"用电低谷把多余的电挪到高峰"，类比"错峰物流"）、55 冷/热备用（类比"待命的替补队员"）、56 黑启动（tldr:"大面积停电后自己能点亮电网"，类比"打火机"）、57 无功与电压支撑、58 "两个细则"与市场化新机制。

每概念填字段；54/55 给 `compare`。

- [ ] **Step 2: 第 6 章「绿色权益与碳」**

节：61 绿色电力交易（tldr:"专门买卖绿电，能证明你用的是新能源"，analogy"带有机蔬菜标的菜"）、62 绿证 GEC（tldr:"一张证 = 1 兆瓦时绿电的身份证"，类比"有机认证标签"）、63 碳排放权交易（tldr"排碳配额不够就买别人的"，类比"碳的额度交易"）、64 CCER（tldr"自愿减排项目产生的碳信用"）、65 绿电 vs 绿证关系（compare 表）。

- [ ] **Step 3: 验证 + 记录**

Run: `node -e "...import...console.log(m.CURRICULUM.length)"` → Expected `6`。
`CHANGELOG.md`：`2026-08-07 Task6: 第5章辅助服务 + 第6章绿色权益`

---

## Task 7: 第 7 章 容量与输电权 + 第 8 章 电价与结算

**Files:**
- Modify: `frontend/src/knowledge/curriculum.js`

- [ ] **Step 1: 第 7 章「容量与输电权」**

节：71 容量市场/容量补偿机制（tldr:"给电厂一笔钱保证它愿意建机组、随时能开"，analogy"养着备胎"）、72 输电权 FTR（tldr:"锁住跨省送电的过路费风险"，类比"预付过路费对冲堵车涨价"，注明国内试点现状）。

- [ ] **Step 2: 第 8 章「电价与结算」**

节：81 输配电价（tldr"电网过路费，政府按准许收入核定"，analogy"高速过路费"）、82 上网电价（标杆→市场，类比"出厂价"）、83 销售电价（目录→市场化，类比"零售价"）、84 容量电价与两部制（tldr"一部分按容量收、一部分按电量收"）、85 结算规则（中长期结算/现货结算/偏差结算，tldr"实际用多了/少了和中长期合同的差怎么算钱"，analogy"批发合同+当日零售月底一起结账"）、86 交叉补贴与政府性基金及附加。

85 给 `compare`（中长期结算 vs 现货结算 vs 偏差结算）。

- [ ] **Step 3: 验证 + 记录**

Run: `node -e "...console.log(m.CURRICULUM.length)"` → Expected `8`。
`CHANGELOG.md`：`2026-08-07 Task7: 第7章容量输电权 + 第8章电价结算`

---

## Task 8: 第 9-13 章（需求响应/新兴主体/跨省跨区/电力金融/监管信用）

**Files:**
- Modify: `frontend/src/knowledge/curriculum.js`

- [ ] **Step 1: 第 9 章「需求响应」**

节：91 需求响应 IL/DR（tldr"用电方在紧张时主动少用、换奖励"，analogy"错峰用电打折"）、92 可中断负荷（tldr"签了约、紧急时能被切掉的用户"，类比"自愿停电换电费优惠"）、93 聚合参与现货+辅助服务。

- [ ] **Step 2: 第 10 章「新兴主体与机制」**

节：101 储能（独立/共享，tldr"电的蓄水池，低价存高价放"）、102 虚拟电厂 VPP（tldr"把一堆分散小电源/负荷打包成一个电厂来调度"，analogy"云仓"）、103 负荷聚合商、104 隔墙售电/分布式交易（tldr"楼下屋顶光伏直接卖给隔壁楼"，analogy"邻里直接交易"）、105 综合能源服务。

- [ ] **Step 3: 第 11 章「跨省跨区与区域市场」**

节：111 省间市场、112 区域市场、113 跨省跨区交易（tldr"把富余省份的电送到缺电省份"，analogy"跨省调货"）。

- [ ] **Step 4: 第 12 章「电力金融与风险管理」**

节：121 电力期货/期权（tldr"提前锁住未来电价、对冲涨跌风险"，analogy"价格保险"）、122 合同风险与对冲。

- [ ] **Step 5: 第 13 章「市场监管与信用」**

节：131 监管体系（能源局/发改委，tldr"市场的裁判和规则制定者"）、132 市场力监测（tldr"盯着有没有人操纵价格"）、133 信用体系（履约保函/违约处理，tldr"交押金保证你说话算数"）。

- [ ] **Step 6: 验证 + 记录**

Run: `node -e "...console.log(m.CURRICULUM.length)"` → Expected `13`。
抽查：`console.log(m.CURRICULUM.filter(c=>!c.intro).map(c=>c.code))` → Expected: 空数组（每章都有 intro）。
`CHANGELOG.md`：`2026-08-07 Task8: 第9-13章 完成 13 章体系`

---

## Task 9: `KnowledgeBook.vue` 阅读组件

**Files:**
- Create: `frontend/src/views/knowledge/KnowledgeBook.vue`

**Interfaces:**
- Consumes: `CURRICULUM`、`LEARNING_PATH`（Task4-8 已建）、`parseMarkdown`/`inlineHtml`（Task3 已建）、`useRoute`/`useRouter`。
- Produces: 默认导出 Vue SFC，渲染左栏章节树 + 右栏正文 + 顶部学习路线卡；支持 `?c=<conceptCode>` 定位概念。

- [ ] **Step 1: 写组件骨架**

`frontend/src/views/knowledge/KnowledgeBook.vue` `<template>` 三区：

```html
<div class="kb-book">
  <aside class="kb-tree">
    <div class="kb-tree-head"><FolderTree :size="14"/> 章节导航</div>
    <el-input v-model="filter" placeholder="搜索章节/概念…" size="small" clearable/>
    <div class="kb-tree-list">
      <template v-for="ch in CURRICULUM" :key="ch.code">
        <div class="kb-ch" @click="toggleCh(ch.code)">{{ ch.title }}</div>
        <div v-show="openChs.has(ch.code)" class="kb-sec-list">
          <div v-for="sec in ch.sections" :key="sec.code" class="kb-sec">
            <div class="kb-sec-title">{{ sec.title }}</div>
            <div v-for="c in sec.concepts" :key="c.code"
                 class="kb-concept" :class="{active: current===c.code}"
                 @click="select(c.code)">{{ c.title }}</div>
          </div>
        </div>
      </template>
    </div>
  </aside>

  <main class="kb-reader">
    <!-- 学习路线卡（仅当无选中概念时首屏） -->
    <section v-if="!current" class="kb-path-card">
      <div class="kpc-head"><Sparkles :size="14"/> 入门学习路线</div>
      <p class="kpc-sub">完全不懂？按这个顺序看，循序渐进：</p>
      <div class="kpc-steps">
        <button v-for="(code,i) in LEARNING_PATH" :key="code"
                class="kpc-step" @click="select(code)">
          <span class="kpc-idx">{{ i+1 }}</span>
          <span>{{ conceptTitle(code) }}</span>
        </button>
      </div>
    </section>

    <!-- 概念正文 -->
    <article v-else class="kb-article">
      <div class="kb-bc">{{ conceptPath(current) }}</div>
      <h2>{{ cur.title }}</h2>
      <div class="kb-tldr"><b>一句话懂了：</b>{{ cur.tldr }}</div>
      <div v-if="cur.analogy" class="kb-analogy"><b>生活类比：</b>{{ cur.analogy }}</div>
      <div v-if="cur.prereq?.length" class="kb-prereq"><b>先懂这些：</b>
        <span v-for="p in cur.prereq" :key="p" class="kb-chip" @click="select(p)">{{ conceptTitle(p) }}</span>
      </div>
      <div class="kb-def" v-html="inlineHtml(cur.definition)"></div>
      <ul v-if="cur.keyPoints?.length" class="kb-kp">
        <li v-for="k in cur.keyPoints" :key="k" v-html="inlineHtml(k)"></li>
      </ul>
      <table v-if="cur.compare?.length" class="kb-cmp">
        <thead><tr><th>对比</th><th>{{ cmpA(cur) }}</th><th>{{ cmpB(cur) }}</th></tr></thead>
        <tbody>
          <tr v-for="(row,i) in cur.compare" :key="i">
            <td>{{ row.dim }}</td><td v-html="inlineHtml(row.a)"></td><td v-html="inlineHtml(row.b)"></td>
          </tr>
        </tbody>
      </table>
      <div v-if="cur.link2sim" class="kb-sim"><b>对应仿真：</b>{{ cur.link2sim }}</div>
      <div v-if="cur.related?.length" class="kb-rel"><b>相关概念：</b>
        <span v-for="r in cur.related" :key="r" class="kb-chip" @click="select(r)">{{ conceptTitle(r) }}</span>
      </div>
      <div class="kb-nav">
        <button @click="prev">← 上一节</button>
        <button @click="next">下一节 →</button>
      </div>
    </article>
  </main>
</div>
```

> `cmpA`/`cmpB` 取 `cur.compare[0]` 的 a/b 列头（实际数据里 a/b 固定为两个对象名，对比行多维；若多对象则简化为 a vs b 两列，按 spec 数据约定）。如实现时发现 compare 需多对象，回看 curriculum.js 第 3 章 321/322/323 数据形态再定表格列数，保持与数据一致。

- [ ] **Step 2: 写 `<script setup>`**

```js
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { FolderTree, Sparkles } from 'lucide-vue-next'
import { CURRICULUM, LEARNING_PATH } from '../../knowledge/curriculum'
import { inlineHtml } from '../../utils/markdown'

const route = useRoute()
const router = useRouter()
const filter = ref('')
const openChs = ref(new Set([CURRICULUM[0]?.code]))
const current = ref(route.query.c || '')

// 扁平概念索引
const CONCEPTS = new Map()
for (const ch of CURRICULUM) for (const sec of ch.sections) for (const c of sec.concepts) CONCEPTS.set(c.code, c)
const cur = computed(() => CONCEPTS.get(current.value))
const conceptTitle = (code) => CONCEPTS.get(code)?.title || code
const conceptPath = (code) => { /* 找到所属章/节，拼 "第3章 / 32 交易方式 / 双边协商" */ }

function toggleCh(code){ const s=new Set(openChs.value); s.has(code)?s.delete(code):s.add(code); openChs.value=s }
function select(code){ current.value=code; router.replace({query:{...route.query, c:code}}) }
function flatList(){ /* 返回按 CURRICULUM 顺序的全部概念 code */ }
function prev(){ const l=flatList(); const i=l.indexOf(current.value); if(i>0) select(l[i-1]) }
function next(){ const l=flatList(); const i=l.indexOf(current.value); if(i<l.length-1) select(l[i+1]) }

watch(current, () => { /* 滚动到顶 + 自动展开所属章 */ })
```

- [ ] **Step 3: 写 `<style scoped>`**

复用 `Browse.vue` 的左栏/卡片视觉语言：左栏 `var(--bg-card)`、当前概念 `#4168dc` 高亮、卡片圆角阴影同 `.doc-card`。学习路线卡用 `.knowledge-radar` 同款渐变。移动端 `<900px` 左栏变抽屉（`el-drawer` 或简单 `position:fixed` toggle）。

- [ ] **Step 4: 接到路由验证**

此时 `KnowledgeBook` 还未在 Layout 显示（Task10 接）。临时验证：在 `router/index.js` 的 `/knowledge` children 临时加一条 `{ path:'book', component: KnowledgeBook }` → 跑 `npm run dev` → 访问 `/knowledge/book?c=321` → 看双边协商正文渲染正常后**撤掉临时路由**。

- [ ] **Step 5: 记录**

`CHANGELOG.md`：`2026-08-07 Task9: KnowledgeBook.vue 阅读组件`

---

## Task 10: `Layout.vue` Tab 切换 + 接线

**Files:**
- Modify: `frontend/src/views/knowledge/Layout.vue`
- Modify: `frontend/src/router/index.js`（如需把 `?tab=` 逻辑加到路由，可选）

**Interfaces:**
- Consumes: `KnowledgeBook`（Task9）、`Browse`（已有）。
- Produces: `/knowledge` 顶部 Tab `📚 知识库` / `📰 资讯·爬取`，按 `?tab=book|feed` 切换；默认 `book`。

- [ ] **Step 1: 改 Layout 模板**

`frontend/src/views/knowledge/Layout.vue` `<header>` 内加 Tab 条，`<main>` 改为按 tab 渲染：

```html
<nav class="kb-tabs">
  <button :class="{active: tab==='book'}" @click="setTab('book')"><BookOpen :size="14"/> 知识库</button>
  <button :class="{active: tab==='feed'}" @click="setTab('feed')"><Newspaper :size="14"/> 资讯·爬取</button>
</nav>
<main class="kb-body">
  <KnowledgeBook v-if="tab==='book'"/>
  <Browse v-else :total-docs-handler="setTotalDocs"/>
</main>
```

- [ ] **Step 2: 改 Layout script**

```js
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BookOpen, House, Newspaper } from 'lucide-vue-next'
import KnowledgeBook from './KnowledgeBook.vue'
import Browse from './Browse.vue'

const route = useRoute(); const router = useRouter()
const tab = ref(route.query.tab === 'feed' ? 'feed' : 'book')
const setTab = (t) => { tab.value = t; router.replace({ query: { ...route.query, tab: t } }) }
```

> 注：原 Layout 用 `<router-view :total-docs-handler="setTotalDocs"/>`，现 Browse 直接作组件用，`/knowledge` 路由仍是单 `Browse` child？需把 router/index.js 的 `/knowledge` children 改为只渲染 Layout（不再需要 child route）或保留空 child。**实操**：`router/index.js` L76-82 的 `/knowledge` 改为无 children 的叶子路由，组件 `Layout.vue` 内部决定渲染谁。

- [ ] **Step 3: 改路由**

`frontend/src/router/index.js` L76-82：

```js
{
  path: '/knowledge',
  name: 'knowledge',
  component: () => import('../views/knowledge/Layout.vue'),
  meta: { theme: 'knowledge', title: '知识库' },
},
```

- [ ] **Step 4: 验证**

Run: `cd frontend && npm run dev`
- `/knowledge` → 默认 Tab1 知识库，显示学习路线卡。
- 点「资讯·爬取」→ Tab2，显示原分类树+文档列表，`?tab=feed` 同步。
- 刷新 `?tab=feed` 保持 Tab2。
- 点 Tab1 任一概念 → URL 加 `?c=321`，正文正常；上一节/下一节可循环。
- 移动端窄屏左栏可抽屉化。

- [ ] **Step 5: 记录**

`CHANGELOG.md`：`2026-08-07 Task10: Layout Tab 切换 + 路由调整`

---

## Task 11: 全量验收

**Files:** 无（验收 only）

- [ ] **Step 1: 数据资产按钮**

非 admin 登录 → 首页「数据资产」→ 进入页面、统计/时间线加载。ingest 提交 403 提示。admin 登录 → ingest/review 正常。

- [ ] **Step 2: 知识库 Tab 与内容**

`/knowledge` → Tab1 → 13 章可展开、概念可点开；用户点名的双边协商(321)/集中竞价(322)/挂牌交易(323)/中长期总览(311)/日前(421)/实时(422) 均有 `tldr+analogy+definition+keyPoints+compare+link2sim`；学习路线卡可见；交叉引用可跳转；Tab2 原爬取列表不变。

- [ ] **Step 3: BookReader 回归**

学习中心任一本书任一章 → markdown 渲染与改造前一致。

- [ ] **Step 4: 记录**

`CHANGELOG.md`：`2026-08-07 Task11: 全量验收通过`

---

## Self-Review（已执行）

1. **Spec 覆盖**：spec §3.1 后端 guard→Task1；§3.1 前端路由→Task2；§3.5 markdown 工具→Task3；§3.4 课程数据+§3.4 13 章→Task4-8；§3.3 KnowledgeBook→Task9；§3.2 Layout Tab→Task10；验收→Task11。全覆盖。
2. **占位符扫描**：无 TBD/TODO；每步含具体代码或具体命令；content 任务给了每概念的字段示例与类比文案，非空泛。
3. **类型一致性**：`CURRICULUM`/`LEARNING_PATH` 在 Task4 定义、Task5-8 追加、Task9 消费，字段名（`tldr/analogy/definition/keyPoints/compare/link2sim/related/prereq/intro`）全计划一致；`parseMarkdown/inlineHtml` 在 Task3 定义、Task9 消费一致。
4. **风险点**：Task1 的 fixtures 若 conftest 无现成需补；Task9 compare 表列数依数据而定（已在 Step1 标注回看数据）；Task10 路由改叶子需同步删 child route（已标注）。
